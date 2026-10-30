//! El manifiesto delta (F3.1.4): lo que cambió desde una `sync_version`, filtrado
//! por la selección del teléfono y, si lo pide, paginado.
//!
//! Es `construir_manifest` de la V1 (`sync_repositorio.py`) campo a campo y en el
//! mismo orden. Las versiones las ponen los disparadores de V5; aquí solo se leen.
//! La V1 enviaba todas las pistas, también las que su deduplicación apartó, y la
//! V2 hace lo mismo: el teléfono ya las tiene y quitarlas sería un cambio que no
//! le llegaría como tumba.

use std::collections::HashSet;

use rusqlite::{Connection, OptionalExtension};
use serde::Serialize;
use serde_json::Value;

use crate::error::{NsError, NsResult};
use crate::playlists::{self, Categoria};

pub const PROTOCOLO: u32 = 1;

fn bd<T>(r: rusqlite::Result<T>) -> NsResult<T> {
    r.map_err(|error| {
        tracing::error!(error = %error, "falló una consulta del manifiesto móvil");
        NsError::StorageFailure
    })
}

#[derive(Debug, Clone, Serialize)]
pub struct Pista {
    pub id: i64,
    pub titulo: String,
    pub artista_nombre: String,
    pub album_titulo: String,
    pub album_id: Option<i64>,
    pub artista_id: Option<i64>,
    pub track_number: Option<i64>,
    pub duracion_seg: Option<f64>,
    pub anio: Option<i64>,
    pub genero: Option<String>,
    pub isrc: Option<String>,
    pub mb_recording_id: Option<String>,
    pub favorita: bool,
    pub favorita_actualizada_en: Option<String>,
    pub hash_sha256: Option<String>,
    pub sync_version: i64,
    pub bpm: Option<f64>,
    pub energy: Option<f64>,
    pub key: Option<String>,
    pub audio_url: String,
    pub cover_url: Option<String>,
    pub lyrics_url: String,
    /// Añadido por la V2: `false` si se importó tal como estaba desde Por revisar
    /// (enmienda de ADR-007). Ver `docs/engineering/contrato-movil.md`.
    pub verificada: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct Album {
    pub id: i64,
    pub titulo: String,
    pub artista_id: i64,
    pub tipo: String,
    pub anio: Option<i64>,
    pub sync_version: i64,
    pub cover_url: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Artista {
    pub id: i64,
    pub nombre: String,
    pub sync_version: i64,
    pub imagen_url: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Playlist {
    pub id: i64,
    pub nombre: String,
    pub descripcion: String,
    pub tipo: String,
    pub subtipo: String,
    pub origen: String,
    pub auto_key: Option<String>,
    pub categoria: &'static str,
    pub etiqueta: &'static str,
    pub es_favoritos: bool,
    pub es_anclada: bool,
    pub num_pistas: usize,
    pub sync_version: i64,
    pub pista_ids: Vec<i64>,
    pub cover_url: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Tumba {
    pub entidad: String,
    pub entidad_id: i64,
    pub sync_version: i64,
}

#[derive(Debug, Clone, Serialize)]
pub struct Estadisticas {
    pub total_pistas: i64,
    pub total_favoritas: i64,
}

#[derive(Debug, Clone, Serialize)]
pub struct Perfil {
    pub nombre: String,
    /// La V1 enviaba aquí la ruta de la foto en el PC, que el teléfono no puede
    /// abrir y no usa (`profile_providers.dart`). La V2 no envía rutas del equipo.
    pub foto: String,
    pub estadisticas: Estadisticas,
}

#[derive(Debug, Clone, Serialize)]
pub struct Manifiesto {
    pub protocolo: u32,
    pub since: i64,
    pub sync_version_actual: i64,
    pub sync_version: i64,
    pub generado_en: String,
    pub pistas: Vec<Pista>,
    pub albums: Vec<Album>,
    pub artistas: Vec<Artista>,
    pub playlists: Vec<Playlist>,
    pub tombstones: Vec<Tumba>,
    pub next_since: i64,
    pub has_more: bool,
    pub perfil: Perfil,
}

fn pistas(conn: &Connection, since: i64) -> NsResult<Vec<Pista>> {
    let mut s = bd(conn.prepare(
        "SELECT p.id, p.titulo, p.artista_nombre, p.album_titulo, p.album_id, p.artista_id,
                p.numero, p.duracion_seg, p.anio, p.genero, p.isrc, p.mbid_grabacion, p.favorita,
                p.favorita_actualizada_en, p.sha256, p.sync_version, r.bpm, r.energia,
                r.tonalidad, p.verificada
         FROM pistas p LEFT JOIN rasgos r ON r.pista_id = p.id
         WHERE p.sync_version > ?1 ORDER BY p.sync_version, p.id",
    ))?;
    let filas = bd(s.query_map([since], |f| {
        let id: i64 = f.get(0)?;
        let album_id: Option<i64> = f.get(4)?;
        Ok(Pista {
            id,
            titulo: f.get(1)?,
            artista_nombre: f.get(2)?,
            album_titulo: f.get(3)?,
            album_id,
            artista_id: f.get(5)?,
            track_number: f.get(6)?,
            duracion_seg: f.get(7)?,
            anio: f.get(8)?,
            genero: f.get(9)?,
            isrc: f.get(10)?,
            mb_recording_id: f.get(11)?,
            favorita: f.get(12)?,
            favorita_actualizada_en: f.get(13)?,
            hash_sha256: f.get(14)?,
            sync_version: f.get(15)?,
            bpm: f.get(16)?,
            energy: f.get(17)?,
            key: f.get(18)?,
            audio_url: format!("/api/v1/track/{id}/audio"),
            cover_url: album_id.map(|a| format!("/api/v1/asset/cover/{a}")),
            lyrics_url: format!("/api/v1/track/{id}/lyrics"),
            verificada: f.get(19)?,
        })
    }))?;
    bd(filas.collect())
}

fn albumes(conn: &Connection, since: i64) -> NsResult<Vec<Album>> {
    let mut s = bd(conn.prepare(
        "SELECT id, titulo, artista_id, tipo, anio, sync_version FROM albumes
         WHERE sync_version > ?1 ORDER BY sync_version, id",
    ))?;
    let filas = bd(s.query_map([since], |f| {
        let id: i64 = f.get(0)?;
        Ok(Album {
            id,
            titulo: f.get(1)?,
            artista_id: f.get(2)?,
            tipo: f.get(3)?,
            anio: f.get(4)?,
            sync_version: f.get(5)?,
            cover_url: format!("/api/v1/asset/cover/{id}"),
        })
    }))?;
    bd(filas.collect())
}

fn artistas(conn: &Connection, since: i64) -> NsResult<Vec<Artista>> {
    let mut s = bd(conn.prepare(
        "SELECT id, nombre, sync_version FROM artistas
         WHERE sync_version > ?1 ORDER BY sync_version, id",
    ))?;
    let filas = bd(s.query_map([since], |f| {
        let id: i64 = f.get(0)?;
        Ok(Artista {
            id,
            nombre: f.get(1)?,
            sync_version: f.get(2)?,
            imagen_url: format!("/api/v1/asset/artist/{id}"),
        })
    }))?;
    bd(filas.collect())
}

fn texto_categoria(c: Categoria) -> &'static str {
    match c {
        Categoria::MeGusta => "me_gusta",
        Categoria::Creada => "creada",
        Categoria::Inteligente => "inteligente",
        Categoria::ThisIs => "this_is",
        Categoria::Sistema => "sistema",
    }
}

/// Si una playlist tiene con qué hacer su mosaico. En la V1 todas las visibles de
/// la instalación real tenían una portada generada; la V2 la compone al pedirla.
const CON_PORTADA: &str = "EXISTS (SELECT 1 FROM playlist_pistas pp JOIN pistas p ON p.id = pp.pista_id
                 LEFT JOIN albumes a ON a.id = p.album_id
                 WHERE pp.playlist_id = pl.id AND coalesce(p.portada_id, a.portada_id) IS NOT NULL)";

fn listas(conn: &Connection, since: i64) -> NsResult<Vec<Playlist>> {
    let mut s = bd(conn.prepare(&format!(
        "SELECT pl.id, pl.nombre, pl.descripcion, pl.tipo, pl.subtipo, pl.origen, pl.clave_auto,
                pl.anclada, pl.sync_version, {CON_PORTADA}
         FROM playlists pl WHERE pl.sync_version > ?1 AND pl.visible = 1
         ORDER BY pl.sync_version, pl.id"
    )))?;
    let filas = bd(s.query_map([since], |f| {
        Ok((
            f.get::<_, i64>(0)?,
            f.get::<_, String>(1)?,
            f.get::<_, Option<String>>(2)?,
            f.get::<_, String>(3)?,
            f.get::<_, Option<String>>(4)?,
            f.get::<_, String>(5)?,
            f.get::<_, Option<String>>(6)?,
            f.get::<_, bool>(7)?,
            f.get::<_, i64>(8)?,
            f.get::<_, bool>(9)?,
        ))
    }))?
    .collect::<rusqlite::Result<Vec<_>>>();
    let filas = bd(filas)?;
    let mut contenido = bd(conn
        .prepare("SELECT pista_id FROM playlist_pistas WHERE playlist_id = ?1 ORDER BY posicion"))?;
    let mut salida = Vec::with_capacity(filas.len());
    for (id, nombre, descripcion, tipo, subtipo, origen, clave, anclada, version, portada) in filas
    {
        let pista_ids =
            bd(contenido.query_map([id], |f| f.get(0)))?.collect::<rusqlite::Result<Vec<i64>>>();
        let pista_ids = bd(pista_ids)?;
        // Los valores efectivos de la V1 (`_subtipo_playlist`, `_origen_playlist`).
        let tipo = if tipo.trim().is_empty() {
            "manual".to_owned()
        } else {
            tipo
        };
        let subtipo = subtipo.filter(|s| !s.trim().is_empty()).unwrap_or_else(|| {
            match tipo.as_str() {
                "manual" => "usuario",
                "sistema" => "sistema",
                otro => otro,
            }
            .to_owned()
        });
        let origen = if origen.trim().is_empty() {
            if tipo == "manual" {
                "usuario"
            } else {
                "generado"
            }
            .to_owned()
        } else {
            origen
        };
        let (categoria, etiqueta) = playlists::clasificar(&tipo, Some(&subtipo), &origen);
        salida.push(Playlist {
            id,
            nombre,
            descripcion: descripcion.unwrap_or_default(),
            tipo,
            subtipo,
            origen,
            auto_key: clave,
            categoria: texto_categoria(categoria),
            etiqueta,
            es_favoritos: categoria == Categoria::MeGusta,
            es_anclada: anclada,
            num_pistas: pista_ids.len(),
            sync_version: version,
            pista_ids,
            cover_url: portada.then(|| format!("/api/v1/asset/playlist/{id}")),
        });
    }
    Ok(salida)
}

fn tumbas(conn: &Connection, since: i64) -> NsResult<Vec<Tumba>> {
    let mut s = bd(conn.prepare(
        "SELECT entidad, entidad_id, sync_version FROM tumbas
         WHERE sync_version > ?1 ORDER BY sync_version, id",
    ))?;
    let filas = bd(s.query_map([since], |f| {
        Ok(Tumba {
            entidad: f.get(0)?,
            entidad_id: f.get(1)?,
            sync_version: f.get(2)?,
        })
    }))?;
    bd(filas.collect())
}

fn perfil(conn: &Connection) -> NsResult<Perfil> {
    let nombre: Option<String> = bd(conn
        .query_row(
            "SELECT valor FROM preferencias WHERE clave = 'nombre_usuario'",
            [],
            |f| f.get(0),
        )
        .optional())?;
    let (total_pistas, total_favoritas) = bd(conn.query_row(
        "SELECT count(*), coalesce(sum(favorita), 0) FROM pistas",
        [],
        |f| Ok((f.get(0)?, f.get(1)?)),
    ))?;
    Ok(Perfil {
        nombre: nombre
            .and_then(|v| serde_json::from_str::<String>(&v).ok())
            .unwrap_or_default(),
        foto: String::new(),
        estadisticas: Estadisticas {
            total_pistas,
            total_favoritas,
        },
    })
}

fn ids(v: Option<&Value>) -> HashSet<i64> {
    v.and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|x| {
            x.as_i64()
                .or_else(|| x.as_f64().map(|f| f as i64))
                .or_else(|| x.as_str().and_then(|s| s.trim().parse().ok()))
        })
        .collect()
}

/// `_aplicar_seleccion` de la V1. Las tumbas y la versión viajan siempre.
fn aplicar_seleccion(
    conn: &Connection,
    m: &mut Manifiesto,
    seleccion: Option<&Value>,
) -> NsResult<()> {
    let Some(sel) = seleccion.filter(|s| s.as_object().is_some_and(|o| !o.is_empty())) else {
        return Ok(());
    };
    match modo(sel).as_str() {
        "nada" => {
            m.pistas.clear();
            m.albums.clear();
            m.artistas.clear();
            m.playlists.clear();
        }
        "artistas" => {
            let permitidos = ids(sel.get("artista_ids"));
            let dentro = |a: Option<i64>| a.is_some_and(|a| permitidos.contains(&a));
            m.pistas.retain(|p| dentro(p.artista_id));
            m.albums.retain(|a| dentro(Some(a.artista_id)));
            m.artistas.retain(|a| dentro(Some(a.id)));
            m.playlists.clear();
        }
        "playlists" => {
            let elegidas = ids(sel.get("playlist_ids"));
            let mut contenidas = HashSet::new();
            let mut s =
                bd(conn.prepare("SELECT pista_id FROM playlist_pistas WHERE playlist_id = ?1"))?;
            for id in &elegidas {
                for p in bd(s.query_map([id], |f| f.get::<_, i64>(0)))? {
                    contenidas.insert(bd(p)?);
                }
            }
            m.pistas.retain(|p| contenidas.contains(&p.id));
            let albumes: HashSet<i64> = m.pistas.iter().filter_map(|p| p.album_id).collect();
            let artistas: HashSet<i64> = m.pistas.iter().filter_map(|p| p.artista_id).collect();
            m.albums.retain(|a| albumes.contains(&a.id));
            m.artistas.retain(|a| artistas.contains(&a.id));
            m.playlists.retain(|p| elegidas.contains(&p.id));
        }
        _ => {}
    }
    Ok(())
}

/// El modo de una selección como lo lee la V1: `str(modo or "todo").lower()`.
pub fn modo(sel: &Value) -> String {
    match sel.get("modo") {
        None | Some(Value::Null) => "todo".to_owned(),
        Some(Value::Bool(false)) => "todo".to_owned(),
        Some(Value::String(s)) if s.is_empty() => "todo".to_owned(),
        Some(Value::String(s)) => s.to_lowercase(),
        Some(otro) => otro.to_string().to_lowercase(),
    }
}

/// `_paginar_manifest`: el contador es global y único por entidad, así que se
/// ordena todo junto por versión (de forma estable, en el orden de tipos de la V1)
/// y se corta.
fn paginar(m: &mut Manifiesto, limite: usize) {
    let mut todo: Vec<(i64, usize, usize)> = Vec::new();
    let versiones: [Vec<i64>; 5] = [
        m.pistas.iter().map(|p| p.sync_version).collect(),
        m.albums.iter().map(|a| a.sync_version).collect(),
        m.artistas.iter().map(|a| a.sync_version).collect(),
        m.playlists.iter().map(|p| p.sync_version).collect(),
        m.tombstones.iter().map(|t| t.sync_version).collect(),
    ];
    for (tipo, vs) in versiones.iter().enumerate() {
        todo.extend(vs.iter().enumerate().map(|(i, v)| (*v, tipo, i)));
    }
    todo.sort_by_key(|t| t.0);
    let has_more = todo.len() > limite;
    todo.truncate(limite);
    let entra: HashSet<(usize, usize)> = todo.iter().map(|t| (t.1, t.2)).collect();
    fn quedarse<T>(v: &mut Vec<T>, tipo: usize, entra: &HashSet<(usize, usize)>) {
        let mut i = 0;
        v.retain(|_| {
            i += 1;
            entra.contains(&(tipo, i - 1))
        });
    }
    quedarse(&mut m.pistas, 0, &entra);
    quedarse(&mut m.albums, 1, &entra);
    quedarse(&mut m.artistas, 2, &entra);
    quedarse(&mut m.playlists, 3, &entra);
    quedarse(&mut m.tombstones, 4, &entra);
    m.next_since = match todo.last() {
        Some(ultima) if has_more => ultima.0,
        // Página final: el teléfono queda al día en la versión global.
        _ => m.sync_version_actual,
    };
    m.has_more = has_more;
}

/// # Errors
///
/// [`NsError::StorageFailure`] si alguna consulta falla.
pub fn construir(
    conn: &Connection,
    since: i64,
    seleccion: Option<&Value>,
    limite: Option<i64>,
    generado_en: String,
) -> NsResult<Manifiesto> {
    let since = since.max(0);
    let version: i64 = bd(conn.query_row("SELECT version FROM sincronizacion", [], |f| f.get(0)))?;
    let mut m = Manifiesto {
        protocolo: PROTOCOLO,
        since,
        sync_version_actual: version,
        sync_version: version,
        generado_en,
        pistas: pistas(conn, since)?,
        albums: albumes(conn, since)?,
        artistas: artistas(conn, since)?,
        playlists: listas(conn, since)?,
        tombstones: tumbas(conn, since)?,
        next_since: version,
        has_more: false,
        perfil: perfil(conn)?,
    };
    aplicar_seleccion(conn, &mut m, seleccion)?;
    if let Some(l) = limite.filter(|l| *l > 0) {
        paginar(&mut m, usize::try_from(l).unwrap_or(usize::MAX));
    }
    Ok(m)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::db::BaseDeDatos;

    fn version_de(conn: &Connection) -> i64 {
        conn.query_row("SELECT sync_version FROM pistas WHERE id = 1", [], |f| {
            f.get(0)
        })
        .unwrap()
    }

    /// La promesa de V5: cambiar cualquier columna que el manifiesto envía de una
    /// pista le sube la versión, o el teléfono se quedaría con el valor viejo.
    #[test]
    fn cada_campo_de_la_pista_en_el_manifiesto_sube_su_version() {
        let db = BaseDeDatos::en_memoria().unwrap();
        let conn = db.conexion().unwrap();
        conn.execute_batch(
            "INSERT INTO artistas (id, nombre, clave) VALUES (1, 'a', 'a');
             INSERT INTO albumes (id, artista_id, titulo, clave) VALUES (10, 1, 'x', 'x');
             INSERT INTO pistas (id, titulo, ruta) VALUES (1, 't', 'r');",
        )
        .unwrap();
        let cambios = [
            ("titulo", "'otro'"),
            ("artista_nombre", "'b'"),
            ("album_titulo", "'y'"),
            ("album_id", "10"),
            ("artista_id", "1"),
            ("numero", "3"),
            ("duracion_seg", "12.5"),
            ("anio", "2001"),
            ("genero", "'Rock'"),
            ("isrc", "'X'"),
            ("mbid_grabacion", "'m'"),
            ("favorita", "1"),
            ("favorita_actualizada_en", "'2026-01-01T00:00:00.000Z'"),
            (
                "sha256",
                "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'",
            ),
            ("verificada", "0"),
        ];
        for (columna, valor) in cambios {
            let antes = version_de(&conn);
            conn.execute(
                &format!("UPDATE pistas SET {columna} = {valor} WHERE id = 1"),
                [],
            )
            .unwrap();
            assert!(version_de(&conn) > antes, "{columna} no sube la versión");
        }
        let m = construir(&conn, 0, None, None, String::new()).unwrap();
        assert_eq!(m.pistas[0].sync_version, m.sync_version_actual);
    }

    #[test]
    fn la_pagina_corta_por_version_y_la_ultima_deja_al_dia() {
        let db = BaseDeDatos::en_memoria().unwrap();
        let conn = db.conexion().unwrap();
        conn.execute_batch(
            "INSERT INTO artistas (id, nombre, clave) VALUES (1, 'a', 'a'), (2, 'b', 'b');
             INSERT INTO pistas (id, titulo, ruta) VALUES (1, 't', 'r');",
        )
        .unwrap();
        let p1 = construir(&conn, 0, None, Some(2), String::new()).unwrap();
        assert!(p1.has_more);
        assert_eq!(
            (p1.artistas.len(), p1.pistas.len(), p1.next_since),
            (2, 0, 2)
        );
        let p2 = construir(&conn, p1.next_since, None, Some(2), String::new()).unwrap();
        assert!(!p2.has_more);
        assert_eq!(
            (p2.pistas.len(), p2.next_since),
            (1, p2.sync_version_actual)
        );
    }

    #[test]
    fn la_seleccion_por_artistas_quita_las_playlists_y_nada_deja_solo_las_tumbas() {
        let db = BaseDeDatos::en_memoria().unwrap();
        let conn = db.conexion().unwrap();
        conn.execute_batch(
            "INSERT INTO artistas (id, nombre, clave) VALUES (1, 'a', 'a'), (2, 'b', 'b');
             INSERT INTO pistas (id, artista_id, titulo, ruta) VALUES (1, 1, 't', 'r'), (2, 2, 'u', 's');
             INSERT INTO playlists (id, nombre) VALUES (5, 'p');
             DELETE FROM pistas WHERE id = 2;",
        )
        .unwrap();
        let sel = serde_json::json!({"modo": "artistas", "artista_ids": ["1"]});
        let m = construir(&conn, 0, Some(&sel), None, String::new()).unwrap();
        assert_eq!(m.pistas.len(), 1);
        assert_eq!(m.artistas.iter().map(|a| a.id).collect::<Vec<_>>(), [1]);
        assert!(m.playlists.is_empty());
        let nada = serde_json::json!({"modo": "NADA"});
        let m = construir(&conn, 0, Some(&nada), None, String::new()).unwrap();
        assert!(m.pistas.is_empty() && m.artistas.is_empty());
        assert_eq!(m.tombstones.len(), 1, "las tumbas viajan siempre");
    }
}
