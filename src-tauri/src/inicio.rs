//! Lo que muestra Inicio (F2.2.2), con las secciones de la V1
//! (`VistaInicio.qml` y `ModeloEstadisticas.cargar`): las cifras de la biblioteca,
//! la canción para retomar, el álbum destacado del día, "Vuelve a tu música", el
//! top 10, los álbumes que vuelven a aparecer, los artistas que más suenan, los
//! últimos añadidos y las playlists destacadas.
//!
//! Todo en una sola petición y fuera del hilo de la ventana: la V1 hacía doce
//! consultas seguidas en el hilo de la interfaz y la congelaba al abrir.

use serde::Serialize;
use ts_rs::TS;

use crate::biblioteca::{self, AlbumResumen, ArtistaResumen, PistaResumen};
use crate::db::BaseDeDatos;
use crate::error::{NsError, NsResult};
use crate::playlists::{self, PlaylistResumen};

#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct Cifras {
    pub pistas: u32,
    pub artistas: u32,
    pub albumes: u32,
    pub duracion_seg: f64,
}

/// Una pista con cuántas veces ha sonado.
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct PistaEscuchada {
    pub pista: PistaResumen,
    pub reproducciones: u32,
}

#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct Inicio {
    pub cifras: Cifras,
    /// Lo último que sonó, para retomar; la primera es la de "Retomar".
    pub para_volver: Vec<PistaEscuchada>,
    pub album_destacado: Option<AlbumResumen>,
    pub top: Vec<PistaEscuchada>,
    pub albumes_que_gustan: Vec<AlbumResumen>,
    pub artistas_que_suenan: Vec<ArtistaResumen>,
    pub ultimos_anadidos: Vec<PistaResumen>,
    pub albumes_mas_escuchados: Vec<AlbumResumen>,
    pub playlists_destacadas: Vec<PlaylistResumen>,
}

fn ids(db: &BaseDeDatos, sql: &str, limite: u32) -> NsResult<Vec<(i64, u32)>> {
    let conn = db.conexion()?;
    let mut s = conn
        .prepare_cached(sql)
        .map_err(|_| NsError::StorageFailure)?;
    let filas = s
        .query_map([limite], |f| {
            Ok((f.get(0)?, f.get::<_, i64>(1)?.max(0) as u32))
        })
        .map_err(|_| NsError::StorageFailure)?
        .collect::<rusqlite::Result<Vec<_>>>()
        .map_err(|_| NsError::StorageFailure)?;
    Ok(filas)
}

fn escuchadas(db: &BaseDeDatos, filas: &[(i64, u32)]) -> NsResult<Vec<PistaEscuchada>> {
    let ids: Vec<i64> = filas.iter().map(|f| f.0).collect();
    let resumenes = biblioteca::resumenes(db, &ids)?;
    Ok(resumenes
        .into_iter()
        .map(|pista| {
            let reproducciones = filas.iter().find(|f| f.0 == pista.id).map_or(0, |f| f.1);
            PistaEscuchada {
                pista,
                reproducciones,
            }
        })
        .collect())
}

fn albumes(db: &BaseDeDatos, filas: &[(i64, u32)]) -> NsResult<Vec<AlbumResumen>> {
    filas
        .iter()
        .filter_map(|(id, _)| biblioteca::album(db, *id).transpose())
        .collect()
}

/// # Errors
///
/// [`NsError::StorageFailure`] si alguna consulta falla.
pub fn resumen(db: &BaseDeDatos) -> NsResult<Inicio> {
    let cifras = {
        let conn = db.conexion()?;
        conn.query_row(
            "SELECT count(*), count(DISTINCT artista_id), count(DISTINCT album_id),
                    total(duracion_seg)
             FROM pistas WHERE estado = 'biblioteca'",
            [],
            |f| {
                Ok(Cifras {
                    pistas: f.get::<_, i64>(0)? as u32,
                    artistas: f.get::<_, i64>(1)? as u32,
                    albumes: f.get::<_, i64>(2)? as u32,
                    duracion_seg: f.get(3)?,
                })
            },
        )
        .map_err(|_| NsError::StorageFailure)?
    };

    // Como `pistas_para_volver` de la V1: lo que sonó, de lo último a lo primero.
    let para_volver = escuchadas(
        db,
        &ids(
            db,
            "SELECT p.id, p.reproducciones FROM pistas p
             LEFT JOIN historial h ON h.pista_id = p.id
             WHERE p.estado = 'biblioteca'
               AND (h.id IS NOT NULL OR p.ultima_reproduccion IS NOT NULL OR p.reproducciones > 0)
             GROUP BY p.id
             ORDER BY max(coalesce(h.reproducida_en, p.ultima_reproduccion, '')) DESC,
                      p.reproducciones DESC, p.id
             LIMIT ?1",
            12,
        )?,
    )?;

    let top = escuchadas(
        db,
        &ids(
            db,
            "SELECT id, reproducciones FROM pistas
             WHERE estado = 'biblioteca' AND reproducciones > 0
             ORDER BY reproducciones DESC, titulo COLLATE NOCASE, id LIMIT ?1",
            10,
        )?,
    )?;

    // Discos con favoritas o escuchas: el destacado del día es el primero, como en
    // la V1, que lo sacaba de esta misma lista.
    let que_gustan = ids(
        db,
        "SELECT album_id, sum(favorita) * 10 + sum(reproducciones) AS peso FROM pistas
         WHERE estado = 'biblioteca' AND album_id IS NOT NULL
         GROUP BY album_id HAVING sum(favorita) > 0 OR sum(reproducciones) > 0
         ORDER BY peso DESC, album_id LIMIT ?1",
        10,
    )?;
    let mas_escuchados = ids(
        db,
        "SELECT album_id, sum(reproducciones) AS n FROM pistas
         WHERE estado = 'biblioteca' AND album_id IS NOT NULL
         GROUP BY album_id HAVING n > 0 ORDER BY n DESC, album_id LIMIT ?1",
        10,
    )?;
    let albumes_que_gustan = albumes(db, &que_gustan)?;
    let albumes_mas_escuchados = albumes(db, &mas_escuchados)?;
    let album_destacado = albumes_que_gustan
        .first()
        .or(albumes_mas_escuchados.first())
        .cloned();

    let artistas_que_suenan = ids(
        db,
        "SELECT artista_id, sum(reproducciones) AS n FROM pistas
         WHERE estado = 'biblioteca' AND artista_id IS NOT NULL
         GROUP BY artista_id HAVING n > 0 ORDER BY n DESC, artista_id LIMIT ?1",
        10,
    )?
    .iter()
    .filter_map(|(id, _)| biblioteca::artista(db, *id).transpose())
    .collect::<NsResult<Vec<_>>>()?;

    let recientes: Vec<i64> = ids(
        db,
        "SELECT id, 0 FROM pistas WHERE estado = 'biblioteca'
         ORDER BY creada_en DESC, id DESC LIMIT ?1",
        12,
    )?
    .into_iter()
    .map(|f| f.0)
    .collect();
    let ultimos_anadidos = biblioteca::resumenes(db, &recientes)?;

    // Las ancladas y las creadas por el usuario primero, como "Tus playlists
    // destacadas" de la V1.
    let mut playlists_destacadas = playlists::listar(
        db,
        &playlists::ConsultaPlaylists {
            texto: None,
            categoria: None,
            orden: playlists::OrdenPlaylists::MasCanciones,
        },
    )?;
    playlists_destacadas.retain(|p| p.num_pistas > 0);
    playlists_destacadas.sort_by_key(|p| (!p.anclada, p.categoria != playlists::Categoria::Creada));
    playlists_destacadas.truncate(8);

    Ok(Inicio {
        cifras,
        para_volver,
        album_destacado,
        top,
        albumes_que_gustan,
        artistas_que_suenan,
        ultimos_anadidos,
        albumes_mas_escuchados,
        playlists_destacadas,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn una_biblioteca_vacia_da_un_inicio_vacio() {
        let db = BaseDeDatos::en_memoria().unwrap();
        let i = resumen(&db).unwrap();
        assert_eq!(i.cifras.pistas, 0);
        assert!(i.para_volver.is_empty() && i.album_destacado.is_none() && i.top.is_empty());
    }

    #[test]
    fn las_secciones_salen_de_lo_escuchado_y_lo_marcado() {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO artistas (id, nombre, clave) VALUES (1, 'a', 'a'), (2, 'b', 'b');
                 INSERT INTO albumes (id, artista_id, titulo, clave) VALUES (10, 1, 'x', 'x'), (11, 2, 'y', 'y');
                 INSERT INTO pistas (id, album_id, artista_id, titulo, ruta, duracion_seg, reproducciones, favorita) VALUES
                     (1, 10, 1, 'uno', 'a', 100, 9, 0),
                     (2, 11, 2, 'dos', 'b', 200, 1, 1),
                     (3, 11, 2, 'tres', 'c', 300, 0, 0);
                 INSERT INTO historial (pista_id, reproducida_en) VALUES
                     (1, '2026-10-01T00:00:00Z'), (2, '2026-10-20T00:00:00Z');",
            )
            .unwrap();
        let i = resumen(&db).unwrap();
        assert_eq!(
            (i.cifras.pistas, i.cifras.artistas, i.cifras.albumes),
            (3, 2, 2)
        );
        assert_eq!(i.cifras.duracion_seg, 600.0);
        assert_eq!(
            i.para_volver.iter().map(|p| p.pista.id).collect::<Vec<_>>(),
            [2, 1],
            "lo último que sonó, primero"
        );
        assert_eq!(i.top[0].pista.id, 1);
        assert_eq!(i.top[0].reproducciones, 9);
        assert_eq!(
            i.album_destacado.map(|a| a.id),
            Some(11),
            "la favorita pesa más que las escuchas"
        );
        assert_eq!(i.artistas_que_suenan[0].id, 1);
        assert_eq!(i.ultimos_anadidos.len(), 3);
    }
}
