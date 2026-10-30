//! Consultas de la biblioteca para la interfaz.
//!
//! Solo lectura. Toda lista que devuelve tiene un tope, aunque hoy quepa entera
//! (`check-listas`): con 2.397 pistas no se nota y con 100.000 sí.

use serde::Serialize;
use ts_rs::TS;

use crate::db::BaseDeDatos;
use crate::error::{NsError, NsResult};

/// Lo que se pinta de una pista en la barra, la cola y las listas.
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
// Los `id` caben de sobra en un `number` de JavaScript: se tipan así y no como
// `bigint`, que obligaría a convertir en cada comparación.
pub struct PistaResumen {
    #[ts(type = "number")]
    pub id: i64,
    pub titulo: String,
    pub artista: String,
    pub album: String,
    #[ts(type = "number | null")]
    pub album_id: Option<i64>,
    #[ts(type = "number | null")]
    pub artista_id: Option<i64>,
    pub duracion_seg: f64,
    #[ts(type = "number | null")]
    pub anio: Option<i64>,
    pub favorita: bool,
    pub verificada: bool,
    pub tiene_portada: bool,
}

/// Tope de pistas por petición de resúmenes: una ventana de la lista virtual o una
/// cola. Una cola más larga se pide en tramos.
pub const MAX_RESUMENES: usize = 500;

/// Resúmenes de las pistas pedidas, en el mismo orden; las que no existen se
/// omiten.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn resumenes(db: &BaseDeDatos, ids: &[i64]) -> NsResult<Vec<PistaResumen>> {
    let ids = &ids[..ids.len().min(MAX_RESUMENES)];
    if ids.is_empty() {
        return Ok(Vec::new());
    }
    let conn = db.conexion()?;
    let json = serde_json::to_string(ids).map_err(|_| NsError::Internal)?;
    let mut s = conn
        .prepare_cached(
            "SELECT p.id, p.titulo, p.artista_nombre, p.album_titulo, p.album_id, p.artista_id,
                    coalesce(p.duracion_seg, 0), p.anio, p.favorita, p.verificada,
                    coalesce(p.portada_id, a.portada_id) IS NOT NULL
             FROM json_each(?1) j
             JOIN pistas p ON p.id = j.value
             LEFT JOIN albumes a ON a.id = p.album_id
             ORDER BY j.key",
        )
        .map_err(|_| NsError::StorageFailure)?;
    let filas = s
        .query_map([json], |f| {
            Ok(PistaResumen {
                id: f.get(0)?,
                titulo: f.get(1)?,
                artista: f.get(2)?,
                album: f.get(3)?,
                album_id: f.get(4)?,
                artista_id: f.get(5)?,
                duracion_seg: f.get(6)?,
                anio: f.get(7)?,
                favorita: f.get(8)?,
                verificada: f.get(9)?,
                tiene_portada: f.get(10)?,
            })
        })
        .map_err(|_| NsError::StorageFailure)?;
    filas
        .collect::<rusqlite::Result<_>>()
        .map_err(|_| NsError::StorageFailure)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn los_resumenes_salen_en_el_orden_pedido_y_sin_los_que_faltan() {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO artistas (id, nombre, clave) VALUES (1, 'a', 'a');
                 INSERT INTO pistas (id, artista_id, titulo, artista_nombre, ruta) VALUES
                     (1, 1, 'uno', 'a', 'x1'), (2, 1, 'dos', 'a', 'x2'), (3, 1, 'tres', 'a', 'x3');",
            )
            .unwrap();
        let r = resumenes(&db, &[3, 99, 1]).unwrap();
        assert_eq!(r.iter().map(|p| p.id).collect::<Vec<_>>(), [3, 1]);
        assert_eq!(r[0].titulo, "tres");
        assert!(!r[0].tiene_portada);
    }

    #[test]
    fn una_peticion_desmesurada_se_recorta_al_tope() {
        let db = BaseDeDatos::en_memoria().unwrap();
        let ids: Vec<i64> = (1..=10_000).collect();
        assert!(resumenes(&db, &ids).unwrap().is_empty());
    }
}

// --- La lista de canciones ---------------------------------------------------------

/// Los órdenes de la V1 (`VistaBiblioteca.qml`), en su orden.
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Deserialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub enum OrdenPistas {
    TituloAsc,
    TituloDesc,
    ArtistaAsc,
    ArtistaDesc,
    AlbumAsc,
    AlbumDesc,
    AnioDesc,
    AnioAsc,
    DuracionDesc,
    DuracionAsc,
    Recientes,
    Antiguas,
    MasReproducidas,
    MenosReproducidas,
}

impl OrdenPistas {
    /// La cláusula ORDER BY, siempre con el `id` al final para que el orden sea
    /// total y un bloque no repita ni salte filas al cambiar de página.
    fn sql(self) -> &'static str {
        match self {
            Self::TituloAsc => "p.titulo COLLATE NOCASE, p.id",
            Self::TituloDesc => "p.titulo COLLATE NOCASE DESC, p.id DESC",
            Self::ArtistaAsc => "p.artista_nombre COLLATE NOCASE, p.titulo COLLATE NOCASE, p.id",
            Self::ArtistaDesc => {
                "p.artista_nombre COLLATE NOCASE DESC, p.titulo COLLATE NOCASE, p.id"
            }
            Self::AlbumAsc => "p.album_titulo COLLATE NOCASE, p.disco, p.numero, p.id",
            Self::AlbumDesc => "p.album_titulo COLLATE NOCASE DESC, p.disco, p.numero, p.id",
            Self::AnioDesc => "p.anio IS NULL, p.anio DESC, p.titulo COLLATE NOCASE, p.id",
            Self::AnioAsc => "p.anio IS NULL, p.anio, p.titulo COLLATE NOCASE, p.id",
            Self::DuracionDesc => "p.duracion_seg DESC, p.id",
            Self::DuracionAsc => "p.duracion_seg, p.id",
            Self::Recientes => "p.creada_en DESC, p.id DESC",
            Self::Antiguas => "p.creada_en, p.id",
            Self::MasReproducidas => "p.reproducciones DESC, p.titulo COLLATE NOCASE, p.id",
            Self::MenosReproducidas => "p.reproducciones, p.titulo COLLATE NOCASE, p.id",
        }
    }
}

/// Qué canciones listar.
#[derive(Debug, Clone, serde::Deserialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct ConsultaPistas {
    /// Busca en título, artista, álbum y letra, sin tildes y por prefijo.
    pub texto: Option<String>,
    pub favoritas: bool,
    pub sin_verificar: bool,
    #[ts(type = "number | null")]
    pub album_id: Option<i64>,
    #[ts(type = "number | null")]
    pub artista_id: Option<i64>,
    pub orden: OrdenPistas,
}

/// Un tramo de la lista y el total, para la ventana virtual.
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct PaginaPistas {
    pub total: u32,
    pub pistas: Vec<PistaResumen>,
}

/// Tope de un tramo: un bloque de la ventana virtual es de 256.
pub const MAX_TRAMO: u32 = 500;
/// Tope de coincidencias de texto que se ordenan. Más allá, la búsqueda es tan
/// amplia que no ayuda, y ordenar cien mil coincidencias costaría más que buscar.
const MAX_COINCIDENCIAS: u32 = 5_000;

/// El WHERE de una consulta y sus parámetros, en el orden en que aparecen.
fn filtro(c: &ConsultaPistas) -> (String, Vec<rusqlite::types::Value>) {
    use rusqlite::types::Value;
    let mut sql = String::from("p.estado = 'biblioteca'");
    let mut params: Vec<Value> = Vec::new();
    if c.favoritas {
        sql.push_str(" AND p.favorita = 1");
    }
    if c.sin_verificar {
        sql.push_str(" AND p.verificada = 0");
    }
    if let Some(a) = c.album_id {
        sql.push_str(" AND p.album_id = ?");
        params.push(Value::Integer(a));
    }
    if let Some(a) = c.artista_id {
        sql.push_str(" AND p.artista_id = ?");
        params.push(Value::Integer(a));
    }
    if let Some(q) = c.texto.as_deref().and_then(crate::db::busqueda::consulta) {
        sql.push_str(" AND p.id IN (SELECT rowid FROM busqueda WHERE busqueda MATCH ? LIMIT ?)");
        params.push(Value::Text(q));
        params.push(Value::Integer(i64::from(MAX_COINCIDENCIAS)));
    }
    (sql, params)
}

const COLUMNAS_RESUMEN: &str = "p.id, p.titulo, p.artista_nombre, p.album_titulo, p.album_id,
    p.artista_id, coalesce(p.duracion_seg, 0), p.anio, p.favorita, p.verificada,
    coalesce(p.portada_id, a.portada_id) IS NOT NULL";

fn resumen_de(f: &rusqlite::Row<'_>) -> rusqlite::Result<PistaResumen> {
    Ok(PistaResumen {
        id: f.get(0)?,
        titulo: f.get(1)?,
        artista: f.get(2)?,
        album: f.get(3)?,
        album_id: f.get(4)?,
        artista_id: f.get(5)?,
        duracion_seg: f.get(6)?,
        anio: f.get(7)?,
        favorita: f.get(8)?,
        verificada: f.get(9)?,
        tiene_portada: f.get(10)?,
    })
}

/// Un tramo de canciones y el total que cumple la consulta.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn pistas(
    db: &BaseDeDatos,
    c: &ConsultaPistas,
    desde: u32,
    limite: u32,
) -> NsResult<PaginaPistas> {
    let conn = db.conexion()?;
    let (donde, params) = filtro(c);
    let total: i64 = conn
        .query_row(
            &format!("SELECT count(*) FROM pistas p WHERE {donde}"),
            rusqlite::params_from_iter(params.iter()),
            |f| f.get(0),
        )
        .map_err(|_| NsError::StorageFailure)?;
    let mut todos = params;
    todos.push(rusqlite::types::Value::Integer(i64::from(
        limite.min(MAX_TRAMO),
    )));
    todos.push(rusqlite::types::Value::Integer(i64::from(desde)));
    let sql = format!(
        "SELECT {COLUMNAS_RESUMEN} FROM pistas p LEFT JOIN albumes a ON a.id = p.album_id
         WHERE {donde} ORDER BY {} LIMIT ? OFFSET ?",
        c.orden.sql()
    );
    let mut s = conn
        .prepare_cached(&sql)
        .map_err(|_| NsError::StorageFailure)?;
    let pistas = s
        .query_map(rusqlite::params_from_iter(todos.iter()), resumen_de)
        .map_err(|_| NsError::StorageFailure)?
        .collect::<rusqlite::Result<Vec<_>>>()
        .map_err(|_| NsError::StorageFailure)?;
    Ok(PaginaPistas {
        total: total as u32,
        pistas,
    })
}

/// Tope de una cola que se arma desde una lista: la V1 metía la lista entera, y con
/// cien mil canciones eso es una cola que nadie recorre.
pub const MAX_COLA_DESDE_LISTA: u32 = 5_000;

/// Los `id` alrededor de la canción elegida para armar la cola, y en qué posición
/// queda ella. Con listas cortas, la lista entera.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn ids_para_cola(
    db: &BaseDeDatos,
    c: &ConsultaPistas,
    indice: u32,
) -> NsResult<(Vec<i64>, u32)> {
    let conn = db.conexion()?;
    let (donde, mut params) = filtro(c);
    let inicio = indice.saturating_sub(MAX_COLA_DESDE_LISTA / 5);
    params.push(rusqlite::types::Value::Integer(i64::from(
        MAX_COLA_DESDE_LISTA,
    )));
    params.push(rusqlite::types::Value::Integer(i64::from(inicio)));
    let sql = format!(
        "SELECT p.id FROM pistas p WHERE {donde} ORDER BY {} LIMIT ? OFFSET ?",
        c.orden.sql()
    );
    let mut s = conn
        .prepare_cached(&sql)
        .map_err(|_| NsError::StorageFailure)?;
    let ids = s
        .query_map(rusqlite::params_from_iter(params.iter()), |f| f.get(0))
        .map_err(|_| NsError::StorageFailure)?
        .collect::<rusqlite::Result<Vec<i64>>>()
        .map_err(|_| NsError::StorageFailure)?;
    Ok((ids, indice - inicio))
}

#[cfg(test)]
mod pruebas_lista {
    use super::*;

    fn base() -> BaseDeDatos {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO artistas (id, nombre, clave) VALUES (1, 'Maná', 'mana'), (2, 'Bad Bunny', 'bb');
                 INSERT INTO albumes (id, artista_id, titulo, clave, anio) VALUES (10, 1, 'Sueños líquidos', 's', 1997);
                 INSERT INTO pistas (id, album_id, artista_id, titulo, artista_nombre, album_titulo, ruta,
                                     duracion_seg, anio, favorita, verificada, reproducciones, numero) VALUES
                     (1, 10, 1, 'Clavado en un bar', 'Maná', 'Sueños líquidos', 'a', 300, 1997, 1, 1, 5, 2),
                     (2, 10, 1, 'Hechicera', 'Maná', 'Sueños líquidos', 'b', 280, 1997, 0, 1, 9, 1),
                     (3, NULL, 2, 'Tití me preguntó', 'Bad Bunny', 'Un verano sin ti', 'c', 240, 2022, 0, 0, 1, NULL);
                 INSERT INTO pistas (id, artista_id, titulo, ruta, estado) VALUES (4, 2, 'Duplicada', 'd', 'duplicado');",
            )
            .unwrap();
        db
    }

    fn consulta(orden: OrdenPistas) -> ConsultaPistas {
        ConsultaPistas {
            texto: None,
            favoritas: false,
            sin_verificar: false,
            album_id: None,
            artista_id: None,
            orden,
        }
    }

    fn ids(p: &PaginaPistas) -> Vec<i64> {
        p.pistas.iter().map(|p| p.id).collect()
    }

    #[test]
    fn cada_orden_de_la_v1_ordena_y_su_inverso_lo_invierte() {
        let db = base();
        let p = |o| ids(&pistas(&db, &consulta(o), 0, 50).unwrap());
        assert_eq!(p(OrdenPistas::TituloAsc), [1, 2, 3]);
        assert_eq!(p(OrdenPistas::TituloDesc), [3, 2, 1]);
        assert_eq!(p(OrdenPistas::ArtistaAsc), [3, 1, 2]);
        assert_eq!(
            p(OrdenPistas::AlbumAsc),
            [2, 1, 3],
            "dentro del álbum, por número"
        );
        assert_eq!(p(OrdenPistas::AnioDesc), [3, 1, 2]);
        assert_eq!(p(OrdenPistas::DuracionDesc), [1, 2, 3]);
        assert_eq!(p(OrdenPistas::MasReproducidas), [2, 1, 3]);
        assert_eq!(p(OrdenPistas::MenosReproducidas), [3, 1, 2]);
    }

    #[test]
    fn las_duplicadas_no_se_listan_ni_cuentan() {
        let db = base();
        assert_eq!(
            pistas(&db, &consulta(OrdenPistas::TituloAsc), 0, 50)
                .unwrap()
                .total,
            3
        );
    }

    #[test]
    fn los_filtros_se_combinan() {
        let db = base();
        let mut c = consulta(OrdenPistas::TituloAsc);
        c.favoritas = true;
        assert_eq!(ids(&pistas(&db, &c, 0, 50).unwrap()), [1]);
        let mut c = consulta(OrdenPistas::TituloAsc);
        c.sin_verificar = true;
        assert_eq!(ids(&pistas(&db, &c, 0, 50).unwrap()), [3]);
        let mut c = consulta(OrdenPistas::TituloAsc);
        c.album_id = Some(10);
        assert_eq!(pistas(&db, &c, 0, 50).unwrap().total, 2);
        let mut c = consulta(OrdenPistas::TituloAsc);
        c.texto = Some("mana sueños".into());
        assert_eq!(ids(&pistas(&db, &c, 0, 50).unwrap()), [1, 2]);
        c.texto = Some("titi".into());
        assert_eq!(ids(&pistas(&db, &c, 0, 50).unwrap()), [3], "sin tildes");
    }

    #[test]
    fn un_tramo_empieza_donde_se_pide_y_el_total_no_cambia() {
        let db = base();
        let p = pistas(&db, &consulta(OrdenPistas::TituloAsc), 1, 1).unwrap();
        assert_eq!(p.total, 3);
        assert_eq!(ids(&p), [2]);
    }

    #[test]
    fn la_cola_desde_una_lista_empieza_en_la_elegida() {
        let db = base();
        let (ids, desde) = ids_para_cola(&db, &consulta(OrdenPistas::TituloAsc), 2).unwrap();
        assert_eq!(ids, [1, 2, 3]);
        assert_eq!(desde, 2);
    }
}

// --- Álbumes y artistas ----------------------------------------------------------------

#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct AlbumResumen {
    #[ts(type = "number")]
    pub id: i64,
    pub titulo: String,
    pub artista: String,
    #[ts(type = "number")]
    pub artista_id: i64,
    #[ts(type = "number | null")]
    pub anio: Option<i64>,
    /// `Album` o `Single`, como los guardaba la V1.
    pub tipo: String,
    pub num_pistas: u32,
    pub duracion_seg: f64,
    pub tiene_portada: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Deserialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub enum OrdenAlbumes {
    TituloAsc,
    TituloDesc,
    ArtistaAsc,
    AnioDesc,
    AnioAsc,
    Recientes,
}

impl OrdenAlbumes {
    fn sql(self) -> &'static str {
        match self {
            Self::TituloAsc => "a.titulo COLLATE NOCASE, a.id",
            Self::TituloDesc => "a.titulo COLLATE NOCASE DESC, a.id DESC",
            Self::ArtistaAsc => "ar.nombre COLLATE NOCASE, a.anio, a.id",
            Self::AnioDesc => "a.anio IS NULL, a.anio DESC, a.titulo COLLATE NOCASE, a.id",
            Self::AnioAsc => "a.anio IS NULL, a.anio, a.titulo COLLATE NOCASE, a.id",
            Self::Recientes => "a.creado_en DESC, a.id DESC",
        }
    }
}

#[derive(Debug, Clone, serde::Deserialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct ConsultaAlbumes {
    pub texto: Option<String>,
    #[ts(type = "number | null")]
    pub artista_id: Option<i64>,
    pub orden: OrdenAlbumes,
}

#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct PaginaAlbumes {
    pub total: u32,
    pub albumes: Vec<AlbumResumen>,
}

/// Álbumes con alguna canción visible: la V1 ocultaba los vacíos.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn albumes(
    db: &BaseDeDatos,
    c: &ConsultaAlbumes,
    desde: u32,
    limite: u32,
) -> NsResult<PaginaAlbumes> {
    use rusqlite::types::Value;
    let conn = db.conexion()?;
    let mut donde = String::from("1 = 1");
    let mut params: Vec<Value> = Vec::new();
    if let Some(a) = c.artista_id {
        donde.push_str(" AND a.artista_id = ?");
        params.push(Value::Integer(a));
    }
    if let Some(q) = c.texto.as_deref().and_then(crate::db::busqueda::consulta) {
        // Por las canciones: el índice ya sabe de tildes y prefijos.
        donde.push_str(
            " AND a.id IN (SELECT p2.album_id FROM busqueda b JOIN pistas p2 ON p2.id = b.rowid
                           WHERE busqueda MATCH ? LIMIT ?)",
        );
        params.push(Value::Text(format!("{{album artista}} : ({q})")));
        params.push(Value::Integer(i64::from(MAX_COINCIDENCIAS)));
    }
    let base = format!(
        "FROM albumes a JOIN artistas ar ON ar.id = a.artista_id
         JOIN (SELECT album_id, count(*) AS n, total(duracion_seg) AS d FROM pistas
               WHERE estado = 'biblioteca' AND album_id IS NOT NULL GROUP BY album_id) s
           ON s.album_id = a.id
         WHERE {donde}"
    );
    let total: i64 = conn
        .query_row(
            &format!("SELECT count(*) {base}"),
            rusqlite::params_from_iter(params.iter()),
            |f| f.get(0),
        )
        .map_err(|_| NsError::StorageFailure)?;
    params.push(Value::Integer(i64::from(limite.min(MAX_TRAMO))));
    params.push(Value::Integer(i64::from(desde)));
    let sql = format!(
        "SELECT a.id, a.titulo, ar.nombre, a.artista_id, a.anio, a.tipo, s.n, s.d,
                a.portada_id IS NOT NULL
         {base} ORDER BY {} LIMIT ? OFFSET ?",
        c.orden.sql()
    );
    let mut s = conn
        .prepare_cached(&sql)
        .map_err(|_| NsError::StorageFailure)?;
    let albumes = s
        .query_map(rusqlite::params_from_iter(params.iter()), |f| {
            Ok(AlbumResumen {
                id: f.get(0)?,
                titulo: f.get(1)?,
                artista: f.get(2)?,
                artista_id: f.get(3)?,
                anio: f.get(4)?,
                tipo: f.get(5)?,
                num_pistas: f.get::<_, i64>(6)? as u32,
                duracion_seg: f.get(7)?,
                tiene_portada: f.get(8)?,
            })
        })
        .map_err(|_| NsError::StorageFailure)?
        .collect::<rusqlite::Result<Vec<_>>>()
        .map_err(|_| NsError::StorageFailure)?;
    Ok(PaginaAlbumes {
        total: total as u32,
        albumes,
    })
}

#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct ArtistaResumen {
    #[ts(type = "number")]
    pub id: i64,
    pub nombre: String,
    pub num_albumes: u32,
    pub num_pistas: u32,
    pub tiene_imagen: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Deserialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub enum OrdenArtistas {
    NombreAsc,
    NombreDesc,
    MasPistas,
}

#[derive(Debug, Clone, serde::Deserialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct ConsultaArtistas {
    pub texto: Option<String>,
    pub orden: OrdenArtistas,
}

#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct PaginaArtistas {
    pub total: u32,
    pub artistas: Vec<ArtistaResumen>,
}

/// Artistas con alguna canción visible.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn artistas(
    db: &BaseDeDatos,
    c: &ConsultaArtistas,
    desde: u32,
    limite: u32,
) -> NsResult<PaginaArtistas> {
    use rusqlite::types::Value;
    let conn = db.conexion()?;
    let mut donde = String::from("1 = 1");
    let mut params: Vec<Value> = Vec::new();
    if let Some(q) = c.texto.as_deref().and_then(crate::db::busqueda::consulta) {
        donde.push_str(
            " AND ar.id IN (SELECT p2.artista_id FROM busqueda b JOIN pistas p2 ON p2.id = b.rowid
                            WHERE busqueda MATCH ? LIMIT ?)",
        );
        params.push(Value::Text(format!("{{artista}} : ({q})")));
        params.push(Value::Integer(i64::from(MAX_COINCIDENCIAS)));
    }
    let base = format!(
        "FROM artistas ar
         JOIN (SELECT artista_id, count(*) AS n, count(DISTINCT album_id) AS a FROM pistas
               WHERE estado = 'biblioteca' AND artista_id IS NOT NULL GROUP BY artista_id) s
           ON s.artista_id = ar.id
         WHERE {donde}"
    );
    let orden = match c.orden {
        OrdenArtistas::NombreAsc => "ar.nombre COLLATE NOCASE, ar.id",
        OrdenArtistas::NombreDesc => "ar.nombre COLLATE NOCASE DESC, ar.id DESC",
        OrdenArtistas::MasPistas => "s.n DESC, ar.nombre COLLATE NOCASE, ar.id",
    };
    let total: i64 = conn
        .query_row(
            &format!("SELECT count(*) {base}"),
            rusqlite::params_from_iter(params.iter()),
            |f| f.get(0),
        )
        .map_err(|_| NsError::StorageFailure)?;
    params.push(Value::Integer(i64::from(limite.min(MAX_TRAMO))));
    params.push(Value::Integer(i64::from(desde)));
    let sql = format!(
        "SELECT ar.id, ar.nombre, s.a, s.n, ar.imagen_id IS NOT NULL {base}
         ORDER BY {orden} LIMIT ? OFFSET ?"
    );
    let mut s = conn
        .prepare_cached(&sql)
        .map_err(|_| NsError::StorageFailure)?;
    let artistas = s
        .query_map(rusqlite::params_from_iter(params.iter()), |f| {
            Ok(ArtistaResumen {
                id: f.get(0)?,
                nombre: f.get(1)?,
                num_albumes: f.get::<_, i64>(2)? as u32,
                num_pistas: f.get::<_, i64>(3)? as u32,
                tiene_imagen: f.get(4)?,
            })
        })
        .map_err(|_| NsError::StorageFailure)?
        .collect::<rusqlite::Result<Vec<_>>>()
        .map_err(|_| NsError::StorageFailure)?;
    Ok(PaginaArtistas {
        total: total as u32,
        artistas,
    })
}

/// Marca o desmarca una favorita. La marca de tiempo se guarda también al
/// desmarcar: el móvil resuelve los conflictos con ella.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si no se puede escribir.
pub fn fijar_favorita(db: &BaseDeDatos, pista_id: i64, favorita: bool) -> NsResult<()> {
    let mut conn = db.conexion()?;
    let tx = crate::db::transaccion_de_escritura(&mut conn)?;
    tx.execute(
        "UPDATE pistas SET favorita = ?2,
             favorita_actualizada_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
         WHERE id = ?1",
        rusqlite::params![pista_id, favorita],
    )
    .map_err(|_| NsError::StorageFailure)?;
    crate::playlists::reflejar_favorita(&tx, pista_id, favorita)?;
    tx.commit().map_err(|_| NsError::StorageFailure)
}

#[cfg(test)]
mod pruebas_albumes {
    use super::*;

    fn base() -> BaseDeDatos {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO artistas (id, nombre, clave) VALUES (1, 'Maná', 'mana'), (2, 'Bad Bunny', 'bb'), (3, 'Vacío', 'v');
                 INSERT INTO albumes (id, artista_id, titulo, clave, anio) VALUES
                     (10, 1, 'Sueños líquidos', 's', 1997), (11, 2, 'Un verano sin ti', 'u', 2022),
                     (12, 3, 'Sin canciones', 'x', 2000);
                 INSERT INTO pistas (id, album_id, artista_id, titulo, artista_nombre, album_titulo, ruta, duracion_seg) VALUES
                     (1, 10, 1, 'Clavado en un bar', 'Maná', 'Sueños líquidos', 'a', 300),
                     (2, 10, 1, 'Hechicera', 'Maná', 'Sueños líquidos', 'b', 280),
                     (3, 11, 2, 'Tití me preguntó', 'Bad Bunny', 'Un verano sin ti', 'c', 240);",
            )
            .unwrap();
        db
    }

    #[test]
    fn los_albumes_vacios_no_se_listan_y_cada_uno_trae_sus_cifras() {
        let db = base();
        let p = albumes(
            &db,
            &ConsultaAlbumes {
                texto: None,
                artista_id: None,
                orden: OrdenAlbumes::TituloAsc,
            },
            0,
            50,
        )
        .unwrap();
        assert_eq!(p.total, 2);
        assert_eq!(p.albumes[0].titulo, "Sueños líquidos");
        assert_eq!(p.albumes[0].num_pistas, 2);
        assert_eq!(p.albumes[0].duracion_seg, 580.0);
    }

    #[test]
    fn buscar_albumes_y_artistas_no_necesita_tildes() {
        let db = base();
        let a = albumes(
            &db,
            &ConsultaAlbumes {
                texto: Some("suenos".into()),
                artista_id: None,
                orden: OrdenAlbumes::TituloAsc,
            },
            0,
            50,
        )
        .unwrap();
        assert_eq!(a.albumes.iter().map(|a| a.id).collect::<Vec<_>>(), [10]);
        let r = artistas(
            &db,
            &ConsultaArtistas {
                texto: Some("mana".into()),
                orden: OrdenArtistas::NombreAsc,
            },
            0,
            50,
        )
        .unwrap();
        assert_eq!(r.artistas.iter().map(|a| a.id).collect::<Vec<_>>(), [1]);
        assert_eq!(r.artistas[0].num_pistas, 2);
    }

    #[test]
    fn los_artistas_sin_canciones_no_se_listan() {
        let db = base();
        let r = artistas(
            &db,
            &ConsultaArtistas {
                texto: None,
                orden: OrdenArtistas::MasPistas,
            },
            0,
            50,
        )
        .unwrap();
        assert_eq!(r.artistas.iter().map(|a| a.id).collect::<Vec<_>>(), [1, 2]);
    }

    #[test]
    fn desmarcar_una_favorita_tambien_guarda_la_hora_y_sube_la_version() {
        let db = base();
        let version = |db: &BaseDeDatos| -> i64 {
            db.conexion()
                .unwrap()
                .query_row("SELECT sync_version FROM pistas WHERE id = 1", [], |f| {
                    f.get(0)
                })
                .unwrap()
        };
        let antes = version(&db);
        fijar_favorita(&db, 1, true).unwrap();
        fijar_favorita(&db, 1, false).unwrap();
        let (fav, hora): (bool, Option<String>) = db
            .conexion()
            .unwrap()
            .query_row(
                "SELECT favorita, favorita_actualizada_en FROM pistas WHERE id = 1",
                [],
                |f| Ok((f.get(0)?, f.get(1)?)),
            )
            .unwrap();
        assert!(!fav);
        assert!(hora.is_some());
        assert!(version(&db) > antes);
    }
}

/// Un álbum por su `id`, con sus cifras. `None` si no existe o no tiene canciones
/// visibles.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn album(db: &BaseDeDatos, id: i64) -> NsResult<Option<AlbumResumen>> {
    use rusqlite::OptionalExtension;
    let conn = db.conexion()?;
    conn.query_row(
        "SELECT a.id, a.titulo, ar.nombre, a.artista_id, a.anio, a.tipo, count(p.id),
                total(p.duracion_seg), a.portada_id IS NOT NULL
         FROM albumes a JOIN artistas ar ON ar.id = a.artista_id
         JOIN pistas p ON p.album_id = a.id AND p.estado = 'biblioteca'
         WHERE a.id = ?1 GROUP BY a.id",
        [id],
        |f| {
            Ok(AlbumResumen {
                id: f.get(0)?,
                titulo: f.get(1)?,
                artista: f.get(2)?,
                artista_id: f.get(3)?,
                anio: f.get(4)?,
                tipo: f.get(5)?,
                num_pistas: f.get::<_, i64>(6)? as u32,
                duracion_seg: f.get(7)?,
                tiene_portada: f.get(8)?,
            })
        },
    )
    .optional()
    .map_err(|_| NsError::StorageFailure)
}

/// Un artista por su `id`. `None` si no existe o no tiene canciones visibles.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn artista(db: &BaseDeDatos, id: i64) -> NsResult<Option<ArtistaResumen>> {
    use rusqlite::OptionalExtension;
    let conn = db.conexion()?;
    conn.query_row(
        "SELECT ar.id, ar.nombre, count(DISTINCT p.album_id), count(p.id), ar.imagen_id IS NOT NULL
         FROM artistas ar JOIN pistas p ON p.artista_id = ar.id AND p.estado = 'biblioteca'
         WHERE ar.id = ?1 GROUP BY ar.id",
        [id],
        |f| {
            Ok(ArtistaResumen {
                id: f.get(0)?,
                nombre: f.get(1)?,
                num_albumes: f.get::<_, i64>(2)? as u32,
                num_pistas: f.get::<_, i64>(3)? as u32,
                tiene_imagen: f.get(4)?,
            })
        },
    )
    .optional()
    .map_err(|_| NsError::StorageFailure)
}

#[cfg(test)]
mod pruebas_detalle {
    use super::*;

    #[test]
    fn un_album_o_artista_sin_canciones_visibles_no_existe_para_la_interfaz() {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO artistas (id, nombre, clave) VALUES (1, 'a', 'a'), (2, 'b', 'b');
                 INSERT INTO albumes (id, artista_id, titulo, clave) VALUES (10, 1, 'x', 'x'), (11, 2, 'y', 'y');
                 INSERT INTO pistas (id, album_id, artista_id, titulo, ruta, duracion_seg) VALUES
                     (1, 10, 1, 'p', 'a', 100), (2, 10, 1, 'q', 'b', 50);
                 INSERT INTO pistas (id, album_id, artista_id, titulo, ruta, estado) VALUES
                     (3, 11, 2, 'r', 'c', 'duplicado');",
            )
            .unwrap();
        let a = album(&db, 10).unwrap().unwrap();
        assert_eq!((a.num_pistas, a.duracion_seg), (2, 150.0));
        assert_eq!(album(&db, 11).unwrap(), None);
        assert_eq!(artista(&db, 1).unwrap().unwrap().num_albumes, 1);
        assert_eq!(artista(&db, 2).unwrap(), None);
    }
}
