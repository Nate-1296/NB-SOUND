//! Listas inteligentes vivas y regeneración de playlists automáticas (F8.2).
//!
//! Unifica en el mismo mecanismo las listas inteligentes definidas por el usuario
//! (evaluadas en SQLite sobre `pistas`, `rasgos`, `analisis_profundo`,
//! `etiquetas_ambiente`, `stems` e `historial`) y las playlists automáticas que la
//! V1 generaba en `servicios/biblioteca.py` ("Crear para mí").

use std::collections::{HashMap, HashSet};

use rusqlite::types::Value;
use rusqlite::{Connection, OptionalExtension, Transaction};
use serde::{Deserialize, Serialize};
use ts_rs::TS;

use super::{bd, validar_nombre};
use crate::db::{self, BaseDeDatos};
use crate::error::{NsError, NsResult};

/// Límite máximo de pistas en una regla inteligente del usuario.
pub const MAX_LIMITE_INTELIGENTE: u32 = 200;
/// Tope general de las playlists automáticas de la V1 (`PLAYLIST_AUTO_MAX_PISTAS`).
const AUTO_MAX_PISTAS: usize = 50;
/// Mínimo de pistas para las automáticas fuertes (`PLAYLIST_AUTO_STRONG_MIN_PISTAS`).
const AUTO_STRONG_MIN_PISTAS: usize = 30;
/// Mínimo de pistas para las de descubrimiento (`PLAYLIST_AUTO_DESCUBRIR_MIN_PISTAS`).
const AUTO_DESCUBRIR_MIN_PISTAS: usize = 20;
/// Mínimo de pistas para las de ánimo (`PLAYLIST_AUTO_FEATURE_MIN_PISTAS`).
const AUTO_FEATURE_MIN_PISTAS: usize = 30;
/// Mínimo de reproducciones acumuladas para `auto:top_canciones`.
const AUTO_TOP_MIN_REPRODUCCIONES: i64 = 60;
/// Mínimo de pistas de un artista para generar su `This is` (`PLAYLIST_AUTO_THIS_IS_ARTISTA_MIN`).
const AUTO_THIS_IS_ARTISTA_MIN: i64 = 20;
/// Mínimo de pistas en un `This is` (`PLAYLIST_AUTO_THIS_IS_MIN_PISTAS`).
const AUTO_THIS_IS_MIN_PISTAS: usize = 25;
/// Tope de pistas en un `This is` (`PLAYLIST_AUTO_THIS_IS_MAX_PISTAS`).
const AUTO_THIS_IS_MAX_PISTAS: usize = 80;

/// Las once etiquetas que producen `rasgos.rs` y `analisis.rs` en `etiquetas_ambiente`.
pub const ANIMOS_PERMITIDOS: [&str; 11] = [
    "energetica",
    "tranquila",
    "bailable",
    "triste",
    "nocturna",
    "entrenamiento",
    "concentracion",
    "fiesta",
    "feliz",
    "relajada",
    "intensa",
];

/// Cómo se ordenan las pistas que cumplen una [`ReglaInteligente`].
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub enum OrdenInteligente {
    Recientes,
    MasEscuchadas,
    MenosEscuchadas,
    UltimaEscuchaAsc,
    BpmAsc,
    BpmDesc,
    EnergiaDesc,
    TituloAsc,
}

/// Regla declarativa de una lista inteligente viva creada por el usuario.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct ReglaInteligente {
    pub bpm_min: Option<f64>,
    pub bpm_max: Option<f64>,
    pub energia_min: Option<f64>,
    pub energia_max: Option<f64>,
    pub animo: Option<String>,
    pub con_instrumental: Option<bool>,
    pub solo_favoritas: bool,
    pub reproducciones_min: Option<u32>,
    pub reproducciones_max: Option<u32>,
    pub escuchada_en_dias: Option<u32>,
    pub sin_escuchar_dias: Option<u32>,
    pub anio_min: Option<i32>,
    pub anio_max: Option<i32>,
    pub genero: Option<String>,
    pub orden: OrdenInteligente,
    pub limite: u32,
}

/// Valida y limpia una [`ReglaInteligente`] antes de guardarla.
pub fn normalizar_regla(r: &ReglaInteligente) -> NsResult<ReglaInteligente> {
    if let Some(min) = r.bpm_min {
        if !min.is_finite() || !(1.0..=400.0).contains(&min) {
            return Err(NsError::InvalidInput);
        }
    }
    if let Some(max) = r.bpm_max {
        if !max.is_finite() || !(1.0..=400.0).contains(&max) {
            return Err(NsError::InvalidInput);
        }
    }
    if let (Some(min), Some(max)) = (r.bpm_min, r.bpm_max) {
        if min > max {
            return Err(NsError::InvalidInput);
        }
    }

    if let Some(min) = r.energia_min {
        if !min.is_finite() || !(0.0..=1.0).contains(&min) {
            return Err(NsError::InvalidInput);
        }
    }
    if let Some(max) = r.energia_max {
        if !max.is_finite() || !(0.0..=1.0).contains(&max) {
            return Err(NsError::InvalidInput);
        }
    }
    if let (Some(min), Some(max)) = (r.energia_min, r.energia_max) {
        if min > max {
            return Err(NsError::InvalidInput);
        }
    }

    let animo = match r.animo.as_deref().map(str::trim).filter(|s| !s.is_empty()) {
        Some(a) if ANIMOS_PERMITIDOS.contains(&a) => Some(a.to_owned()),
        Some(_) => return Err(NsError::InvalidInput),
        None => None,
    };

    if let (Some(min), Some(max)) = (r.reproducciones_min, r.reproducciones_max) {
        if min > max {
            return Err(NsError::InvalidInput);
        }
    }

    let escuchada_en_dias = r.escuchada_en_dias.filter(|&d| d > 0);
    let sin_escuchar_dias = r.sin_escuchar_dias.filter(|&d| d > 0);
    if escuchada_en_dias.is_some() && sin_escuchar_dias.is_some() {
        return Err(NsError::InvalidInput);
    }
    if escuchada_en_dias.is_some_and(|d| d > 36_500)
        || sin_escuchar_dias.is_some_and(|d| d > 36_500)
    {
        return Err(NsError::InvalidInput);
    }

    if let Some(min) = r.anio_min {
        if !(1000..=9999).contains(&min) {
            return Err(NsError::InvalidInput);
        }
    }
    if let Some(max) = r.anio_max {
        if !(1000..=9999).contains(&max) {
            return Err(NsError::InvalidInput);
        }
    }
    if let (Some(min), Some(max)) = (r.anio_min, r.anio_max) {
        if min > max {
            return Err(NsError::InvalidInput);
        }
    }

    let genero = r
        .genero
        .as_deref()
        .map(str::trim)
        .filter(|g| !g.is_empty())
        .map(str::to_owned);
    if genero.as_ref().is_some_and(|g| g.chars().count() > 80) {
        return Err(NsError::InvalidInput);
    }

    Ok(ReglaInteligente {
        bpm_min: r.bpm_min,
        bpm_max: r.bpm_max,
        energia_min: r.energia_min,
        energia_max: r.energia_max,
        animo,
        con_instrumental: r.con_instrumental,
        solo_favoritas: r.solo_favoritas,
        reproducciones_min: r.reproducciones_min,
        reproducciones_max: r.reproducciones_max,
        escuchada_en_dias,
        sin_escuchar_dias,
        anio_min: r.anio_min,
        anio_max: r.anio_max,
        genero,
        orden: r.orden,
        limite: r.limite.clamp(1, MAX_LIMITE_INTELIGENTE),
    })
}

/// Evalúa en SQLite una [`ReglaInteligente`] y devuelve los `id` de las pistas en orden.
pub fn evaluar_regla(conn: &Connection, r: &ReglaInteligente) -> NsResult<Vec<i64>> {
    let mut condiciones = vec!["p.estado = 'biblioteca'".to_owned()];
    let mut params: Vec<Value> = vec![Value::from(crate::analisis::VERSION.to_owned())];

    let mut siguiente_param = |v: Value| -> String {
        params.push(v);
        format!("?{}", params.len())
    };

    if let Some(min) = r.bpm_min {
        let p = siguiente_param(Value::from(min));
        condiciones.push(format!("r.bpm IS NOT NULL AND r.bpm >= {p}"));
    }
    if let Some(max) = r.bpm_max {
        let p = siguiente_param(Value::from(max));
        condiciones.push(format!("r.bpm IS NOT NULL AND r.bpm <= {p}"));
    }
    if let Some(min) = r.energia_min {
        let p = siguiente_param(Value::from(min));
        condiciones.push(format!(
            "coalesce(ap.activacion, r.energia) IS NOT NULL AND coalesce(ap.activacion, r.energia) >= {p}"
        ));
    }
    if let Some(max) = r.energia_max {
        let p = siguiente_param(Value::from(max));
        condiciones.push(format!(
            "coalesce(ap.activacion, r.energia) IS NOT NULL AND coalesce(ap.activacion, r.energia) <= {p}"
        ));
    }
    if let Some(animo) = &r.animo {
        let p = siguiente_param(Value::from(animo.clone()));
        condiciones.push(format!(
            "EXISTS (SELECT 1 FROM etiquetas_ambiente ea WHERE ea.pista_id = p.id AND ea.etiqueta = {p} AND ea.puntuacion >= 0.5)"
        ));
    }
    match r.con_instrumental {
        Some(true) => condiciones.push(
            "EXISTS (SELECT 1 FROM stems st WHERE st.pista_id = p.id AND st.estado = 'lista')"
                .to_owned(),
        ),
        Some(false) => condiciones.push(
            "NOT EXISTS (SELECT 1 FROM stems st WHERE st.pista_id = p.id AND st.estado = 'lista')"
                .to_owned(),
        ),
        None => {}
    }
    if r.solo_favoritas {
        condiciones.push("p.favorita = 1".to_owned());
    }
    if let Some(min) = r.reproducciones_min {
        let p = siguiente_param(Value::from(i64::from(min)));
        condiciones.push(format!(
            "max(p.reproducciones, coalesce(h.hist_reps, 0)) >= {p}"
        ));
    }
    if let Some(max) = r.reproducciones_max {
        let p = siguiente_param(Value::from(i64::from(max)));
        condiciones.push(format!(
            "max(p.reproducciones, coalesce(h.hist_reps, 0)) <= {p}"
        ));
    }
    if let Some(dias) = r.escuchada_en_dias {
        let p = siguiente_param(Value::from(format!("-{dias} days")));
        condiciones.push(format!(
            "coalesce(h.hist_ultima, p.ultima_reproduccion) IS NOT NULL \
             AND datetime(coalesce(h.hist_ultima, p.ultima_reproduccion)) >= datetime('now', {p})"
        ));
    }
    if let Some(dias) = r.sin_escuchar_dias {
        let p = siguiente_param(Value::from(format!("-{dias} days")));
        condiciones.push(format!(
            "(coalesce(h.hist_ultima, p.ultima_reproduccion) IS NULL \
             OR datetime(coalesce(h.hist_ultima, p.ultima_reproduccion)) <= datetime('now', {p}))"
        ));
    }
    if let Some(min) = r.anio_min {
        let p = siguiente_param(Value::from(i64::from(min)));
        condiciones.push(format!("p.anio IS NOT NULL AND p.anio >= {p}"));
    }
    if let Some(max) = r.anio_max {
        let p = siguiente_param(Value::from(i64::from(max)));
        condiciones.push(format!("p.anio IS NOT NULL AND p.anio <= {p}"));
    }
    if let Some(genero) = &r.genero {
        let p = siguiente_param(Value::from(genero.to_lowercase()));
        condiciones.push(format!(
            "p.genero IS NOT NULL AND lower(p.genero) LIKE '%' || {p} || '%'"
        ));
    }

    let orden = match r.orden {
        OrdenInteligente::Recientes => "datetime(coalesce(p.creada_en, p.actualizada_en)) DESC, p.id DESC",
        OrdenInteligente::MasEscuchadas => {
            "max(p.reproducciones, coalesce(h.hist_reps, 0)) DESC, \
             datetime(coalesce(h.hist_ultima, p.ultima_reproduccion, p.creada_en)) DESC, p.id"
        }
        OrdenInteligente::MenosEscuchadas => {
            "max(p.reproducciones, coalesce(h.hist_reps, 0)) ASC, \
             datetime(coalesce(p.creada_en, p.actualizada_en)) DESC, p.id"
        }
        OrdenInteligente::UltimaEscuchaAsc => {
            "coalesce(h.hist_ultima, p.ultima_reproduccion) IS NOT NULL, \
             datetime(coalesce(h.hist_ultima, p.ultima_reproduccion, p.creada_en)) ASC, p.id"
        }
        OrdenInteligente::BpmAsc => "r.bpm IS NULL, r.bpm ASC, p.id",
        OrdenInteligente::BpmDesc => "r.bpm IS NULL, r.bpm DESC, p.id",
        OrdenInteligente::EnergiaDesc => {
            "coalesce(ap.activacion, r.energia) IS NULL, coalesce(ap.activacion, r.energia) DESC, p.id"
        }
        OrdenInteligente::TituloAsc => "p.titulo COLLATE NOCASE ASC, p.id",
    };

    let limite = i64::from(r.limite.clamp(1, MAX_LIMITE_INTELIGENTE));
    let p_lim = siguiente_param(Value::from(limite));

    let sql = format!(
        "SELECT p.id
         FROM pistas p
         LEFT JOIN rasgos r ON r.pista_id = p.id
         LEFT JOIN analisis_profundo ap ON ap.pista_id = p.id AND ap.version = ?1
         LEFT JOIN (
             SELECT pista_id, count(*) AS hist_reps, max(reproducida_en) AS hist_ultima
             FROM historial
             WHERE pista_id IS NOT NULL
             GROUP BY pista_id
         ) h ON h.pista_id = p.id
         WHERE {}
         ORDER BY {orden}
         LIMIT {p_lim}",
        condiciones.join(" AND ")
    );

    let mut s = bd(conn.prepare(&sql))?;
    let ids = bd(
        bd(s.query_map(rusqlite::params_from_iter(params), |f| f.get(0)))?
            .collect::<rusqlite::Result<Vec<i64>>>(),
    )?;
    Ok(ids)
}

fn pistas_actuales(conn: &Connection, playlist_id: i64) -> NsResult<Vec<i64>> {
    let mut s = bd(conn.prepare_cached(
        "SELECT pista_id FROM playlist_pistas WHERE playlist_id = ?1 ORDER BY posicion, pista_id",
    ))?;
    let ids =
        bd(bd(s.query_map([playlist_id], |f| f.get(0)))?.collect::<rusqlite::Result<Vec<i64>>>())?;
    Ok(ids)
}

fn escribir_pistas_playlist(
    tx: &Transaction<'_>,
    playlist_id: i64,
    nuevos: &[i64],
) -> NsResult<bool> {
    let actuales = pistas_actuales(tx, playlist_id)?;
    if actuales == nuevos {
        return Ok(false);
    }
    bd(tx.execute(
        "DELETE FROM playlist_pistas WHERE playlist_id = ?1",
        [playlist_id],
    ))?;
    for (pos, pista_id) in nuevos.iter().enumerate() {
        bd(tx.execute(
            "INSERT OR IGNORE INTO playlist_pistas (playlist_id, pista_id, posicion)
             VALUES (?1, ?2, ?3)",
            rusqlite::params![playlist_id, pista_id, pos as i64],
        ))?;
    }
    bd(tx.execute(
        "UPDATE playlists SET
             generada_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
             actualizada_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
         WHERE id = ?1",
        [playlist_id],
    ))?;
    Ok(true)
}

/// Evalúa todas las listas inteligentes vivas visibles y actualiza `playlist_pistas`
/// solo en las que cambiaron, sin abrir transacción de escritura si todo sigue igual.
pub fn refrescar_inteligentes(db: &BaseDeDatos) -> NsResult<u32> {
    let mut conn = db.conexion()?;
    let filas: Vec<(i64, String)> = {
        let mut s = bd(conn.prepare_cached(
            "SELECT id, regla FROM playlists
             WHERE tipo = 'automatica' AND subtipo = 'inteligente'
               AND auto_actualizable = 1 AND editada = 0 AND visible = 1 AND regla IS NOT NULL",
        ))?;
        let r = bd(bd(s.query_map([], |f| Ok((f.get(0)?, f.get(1)?))))?
            .collect::<rusqlite::Result<Vec<_>>>())?;
        r
    };
    let mut cambios = Vec::new();
    for (id, regla_json) in filas {
        let Ok(regla) = serde_json::from_str::<ReglaInteligente>(&regla_json) else {
            continue;
        };
        let nuevos = evaluar_regla(&conn, &regla)?;
        if pistas_actuales(&conn, id)? != nuevos {
            cambios.push((id, nuevos));
        }
    }
    if cambios.is_empty() {
        return Ok(0);
    }
    let tx = db::transaccion_de_escritura(&mut conn)?;
    let mut tocadas = 0;
    for (id, nuevos) in &cambios {
        if escribir_pistas_playlist(&tx, *id, nuevos)? {
            tocadas += 1;
        }
    }
    bd(tx.commit())?;
    Ok(tocadas)
}

/// Si `id` es una lista inteligente viva, la evalúa y actualiza `playlist_pistas`
/// solo cuando sus canciones cambiaron.
pub fn refrescar_inteligente_si_aplica(db: &BaseDeDatos, id: i64) -> NsResult<()> {
    let mut conn = db.conexion()?;
    let regla_json: Option<String> = bd(conn
        .query_row(
            "SELECT regla FROM playlists
             WHERE id = ?1 AND tipo = 'automatica' AND subtipo = 'inteligente'
               AND auto_actualizable = 1 AND editada = 0 AND regla IS NOT NULL",
            [id],
            |f| f.get(0),
        )
        .optional())?;
    let Some(regla_json) = regla_json else {
        return Ok(());
    };
    let Ok(regla) = serde_json::from_str::<ReglaInteligente>(&regla_json) else {
        return Ok(());
    };
    let nuevos = evaluar_regla(&conn, &regla)?;
    if pistas_actuales(&conn, id)? == nuevos {
        return Ok(());
    }
    let tx = db::transaccion_de_escritura(&mut conn)?;
    escribir_pistas_playlist(&tx, id, &nuevos)?;
    bd(tx.commit())
}

/// Crea una lista inteligente viva del usuario, evalúa su regla de inmediato y
/// devuelve su `id`.
///
/// # Errors
///
/// [`NsError::InvalidInput`] si el nombre o la regla son inválidos;
/// [`NsError::NameTaken`] si el nombre ya existe.
pub fn crear_inteligente(
    db: &BaseDeDatos,
    nombre: &str,
    descripcion: Option<&str>,
    regla: &ReglaInteligente,
) -> NsResult<i64> {
    let regla = normalizar_regla(regla)?;
    let regla_json = serde_json::to_string(&regla).map_err(|_| NsError::InvalidInput)?;
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    let nombre = validar_nombre(&tx, nombre, None)?;
    let nuevos = evaluar_regla(&tx, &regla)?;
    bd(tx.execute(
        "INSERT INTO playlists (nombre, descripcion, tipo, subtipo, origen, regla,
                                auto_actualizable, generada_en)
         VALUES (?1, ?2, 'automatica', 'inteligente', 'usuario', ?3, 1,
                 strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
        rusqlite::params![
            nombre,
            descripcion.map(str::trim).filter(|d| !d.is_empty()),
            regla_json
        ],
    ))?;
    let id = tx.last_insert_rowid();
    for (pos, pista_id) in nuevos.iter().enumerate() {
        bd(tx.execute(
            "INSERT OR IGNORE INTO playlist_pistas (playlist_id, pista_id, posicion)
             VALUES (?1, ?2, ?3)",
            rusqlite::params![id, pista_id, pos as i64],
        ))?;
    }
    bd(tx.commit())?;
    Ok(id)
}

/// Edita el nombre, la descripción y la regla de una lista inteligente del usuario,
/// y actualiza sus canciones si la regla cambió el resultado.
///
/// # Errors
///
/// [`NsError::PathNotAllowed`] si no es una lista inteligente del usuario;
/// [`NsError::FileNotFound`] si no existe.
pub fn editar_inteligente(
    db: &BaseDeDatos,
    id: i64,
    nombre: &str,
    descripcion: Option<&str>,
    regla: &ReglaInteligente,
) -> NsResult<()> {
    let regla = normalizar_regla(regla)?;
    let regla_json = serde_json::to_string(&regla).map_err(|_| NsError::InvalidInput)?;
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    let es_inteligente: Option<bool> = bd(tx
        .query_row(
            "SELECT tipo = 'automatica' AND subtipo = 'inteligente' AND origen = 'usuario'
             FROM playlists WHERE id = ?1",
            [id],
            |f| f.get(0),
        )
        .optional())?;
    match es_inteligente {
        Some(true) => {}
        Some(false) => return Err(NsError::PathNotAllowed),
        None => return Err(NsError::FileNotFound),
    }
    let nombre = validar_nombre(&tx, nombre, Some(id))?;
    let nuevos = evaluar_regla(&tx, &regla)?;
    bd(tx.execute(
        "UPDATE playlists SET nombre = ?2, descripcion = ?3, regla = ?4,
             actualizada_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
         WHERE id = ?1",
        rusqlite::params![
            id,
            nombre,
            descripcion.map(str::trim).filter(|d| !d.is_empty()),
            regla_json
        ],
    ))?;
    escribir_pistas_playlist(&tx, id, &nuevos)?;
    bd(tx.commit())
}

// --- Playlists automáticas de la V1 ("Crear para mí") ---------------------------------

struct SpecAutomatica {
    clave_auto: String,
    nombre: String,
    descripcion: String,
    subtipo: &'static str,
    regla_json: String,
    min_pistas: usize,
    max_pistas: usize,
    candidatos: Vec<i64>,
}

fn ids_consulta(conn: &Connection, sql: &str, limite: usize) -> NsResult<Vec<i64>> {
    let mut s = bd(conn.prepare(sql))?;
    let ids = bd(
        bd(s.query_map([limite as i64], |f| f.get(0)))?.collect::<rusqlite::Result<Vec<i64>>>()
    )?;
    Ok(ids)
}

fn candidatos_top_canciones(conn: &Connection) -> NsResult<Vec<i64>> {
    let mut s = bd(conn.prepare(
        "SELECT p.id, max(p.reproducciones, coalesce(h.reproducciones, 0)) AS reps
         FROM pistas p
         LEFT JOIN (
             SELECT pista_id, count(*) AS reproducciones, max(reproducida_en) AS ultima
             FROM historial WHERE pista_id IS NOT NULL GROUP BY pista_id
         ) h ON h.pista_id = p.id
         WHERE p.estado = 'biblioteca' AND max(p.reproducciones, coalesce(h.reproducciones, 0)) > 0
         ORDER BY reps DESC,
                  datetime(coalesce(h.ultima, p.ultima_reproduccion, p.actualizada_en)) DESC,
                  p.id
         LIMIT ?1",
    ))?;
    let filas = bd(bd(s.query_map([AUTO_MAX_PISTAS as i64], |f| {
        Ok((f.get::<_, i64>(0)?, f.get::<_, i64>(1)?))
    }))?
    .collect::<rusqlite::Result<Vec<_>>>())?;
    let total_reps: i64 = filas.iter().map(|(_, r)| *r).sum();
    if total_reps < AUTO_TOP_MIN_REPRODUCCIONES {
        return Ok(Vec::new());
    }
    Ok(filas.into_iter().map(|(id, _)| id).collect())
}

fn candidatos_artistas_frecuentes(conn: &Connection) -> NsResult<Vec<i64>> {
    let mut s = bd(conn.prepare(
        "SELECT p.artista_id, sum(max(p.reproducciones, coalesce(h.reproducciones, 0))) AS score
         FROM pistas p
         LEFT JOIN (
             SELECT pista_id, count(*) AS reproducciones
             FROM historial WHERE pista_id IS NOT NULL GROUP BY pista_id
         ) h ON h.pista_id = p.id
         WHERE p.estado = 'biblioteca' AND p.artista_id IS NOT NULL
         GROUP BY p.artista_id
         HAVING score > 0
         ORDER BY score DESC, p.artista_id
         LIMIT 10",
    ))?;
    let artistas =
        bd(bd(s.query_map([], |f| f.get::<_, i64>(0)))?.collect::<rusqlite::Result<Vec<i64>>>())?;
    let mut ids = Vec::new();
    let mut usados = HashSet::new();
    let mut s_pistas = bd(conn.prepare(
        "SELECT p.id
         FROM pistas p
         LEFT JOIN (
             SELECT pista_id, count(*) AS reproducciones
             FROM historial WHERE pista_id IS NOT NULL GROUP BY pista_id
         ) h ON h.pista_id = p.id
         WHERE p.estado = 'biblioteca' AND p.artista_id = ?1
         ORDER BY max(p.reproducciones, coalesce(h.reproducciones, 0)) DESC,
                  p.favorita DESC, p.titulo COLLATE NOCASE, p.id
         LIMIT 5",
    ))?;
    for artista_id in artistas {
        let filas = bd(
            bd(s_pistas.query_map([artista_id], |f| f.get::<_, i64>(0)))?
                .collect::<rusqlite::Result<Vec<i64>>>(),
        )?;
        for pid in filas {
            if usados.insert(pid) {
                ids.push(pid);
            }
        }
        if ids.len() >= AUTO_MAX_PISTAS {
            break;
        }
    }
    ids.truncate(AUTO_MAX_PISTAS);
    Ok(ids)
}

fn candidatos_albumes_frecuentes(conn: &Connection) -> NsResult<Vec<i64>> {
    let mut s = bd(conn.prepare(
        "SELECT p.album_id, sum(max(p.reproducciones, coalesce(h.reproducciones, 0))) AS score
         FROM pistas p
         LEFT JOIN (
             SELECT pista_id, count(*) AS reproducciones
             FROM historial WHERE pista_id IS NOT NULL GROUP BY pista_id
         ) h ON h.pista_id = p.id
         WHERE p.estado = 'biblioteca' AND p.album_id IS NOT NULL
         GROUP BY p.album_id
         HAVING score > 0
         ORDER BY score DESC, p.album_id
         LIMIT 10",
    ))?;
    let albumes =
        bd(bd(s.query_map([], |f| f.get::<_, i64>(0)))?.collect::<rusqlite::Result<Vec<i64>>>())?;
    let mut ids = Vec::new();
    let mut usados = HashSet::new();
    let mut s_pistas = bd(conn.prepare(
        "SELECT p.id
         FROM pistas p
         LEFT JOIN (
             SELECT pista_id, count(*) AS reproducciones
             FROM historial WHERE pista_id IS NOT NULL GROUP BY pista_id
         ) h ON h.pista_id = p.id
         WHERE p.estado = 'biblioteca' AND p.album_id = ?1
         ORDER BY max(p.reproducciones, coalesce(h.reproducciones, 0)) DESC,
                  coalesce(p.numero, 9999), p.titulo COLLATE NOCASE, p.id
         LIMIT 4",
    ))?;
    for album_id in albumes {
        let filas = bd(bd(s_pistas.query_map([album_id], |f| f.get::<_, i64>(0)))?
            .collect::<rusqlite::Result<Vec<i64>>>())?;
        for pid in filas {
            if usados.insert(pid) {
                ids.push(pid);
            }
        }
        if ids.len() >= AUTO_MAX_PISTAS {
            break;
        }
    }
    ids.truncate(AUTO_MAX_PISTAS);
    Ok(ids)
}

fn candidatos_albumes_para_volver(conn: &Connection) -> NsResult<Vec<i64>> {
    let mut s = bd(conn.prepare(
        "SELECT p.album_id,
                count(DISTINCT p.id) AS num_pistas,
                sum(max(p.reproducciones, coalesce(h.reproducciones, 0))) AS reps,
                sum(p.favorita) AS favs,
                max(coalesce(h.ultima, p.ultima_reproduccion, p.actualizada_en, p.creada_en)) AS ultima_act
         FROM pistas p
         LEFT JOIN (
             SELECT pista_id, count(*) AS reproducciones, max(reproducida_en) AS ultima
             FROM historial WHERE pista_id IS NOT NULL GROUP BY pista_id
         ) h ON h.pista_id = p.id
         WHERE p.estado = 'biblioteca' AND p.album_id IS NOT NULL
         GROUP BY p.album_id
         HAVING num_pistas >= 6 AND (reps >= 6 OR favs >= 2)
         ORDER BY (favs * 12 + reps) DESC, datetime(ultima_act) ASC, p.album_id
         LIMIT 10",
    ))?;
    let albumes =
        bd(bd(s.query_map([], |f| f.get::<_, i64>(0)))?.collect::<rusqlite::Result<Vec<i64>>>())?;
    let mut ids = Vec::new();
    let mut usados = HashSet::new();
    let mut s_pistas = bd(conn.prepare(
        "SELECT p.id
         FROM pistas p
         LEFT JOIN (
             SELECT pista_id, count(*) AS reproducciones
             FROM historial WHERE pista_id IS NOT NULL GROUP BY pista_id
         ) h ON h.pista_id = p.id
         WHERE p.estado = 'biblioteca' AND p.album_id = ?1
         ORDER BY p.favorita DESC,
                  max(p.reproducciones, coalesce(h.reproducciones, 0)) DESC,
                  coalesce(p.numero, 9999), p.titulo COLLATE NOCASE, p.id
         LIMIT 6",
    ))?;
    for album_id in albumes {
        let filas = bd(bd(s_pistas.query_map([album_id], |f| f.get::<_, i64>(0)))?
            .collect::<rusqlite::Result<Vec<i64>>>())?;
        for pid in filas {
            if usados.insert(pid) {
                ids.push(pid);
            }
        }
        if ids.len() >= AUTO_MAX_PISTAS {
            break;
        }
    }
    ids.truncate(AUTO_MAX_PISTAS);
    Ok(ids)
}

fn candidatos_this_is(conn: &Connection, artista_id: i64) -> NsResult<Vec<i64>> {
    let mut s = bd(conn.prepare(
        "SELECT p.id, coalesce(p.album_id, 0)
         FROM pistas p
         LEFT JOIN (
             SELECT pista_id, count(*) AS reproducciones
             FROM historial WHERE pista_id IS NOT NULL GROUP BY pista_id
         ) h ON h.pista_id = p.id
         WHERE p.estado = 'biblioteca' AND p.artista_id = ?1
         ORDER BY p.favorita DESC,
                  max(p.reproducciones, coalesce(h.reproducciones, 0)) DESC,
                  datetime(coalesce(p.ultima_reproduccion, p.actualizada_en, p.creada_en)) DESC,
                  coalesce(p.album_id, 0),
                  coalesce(p.numero, 9999),
                  p.titulo COLLATE NOCASE, p.id
         LIMIT ?2",
    ))?;
    let filas = bd(bd(s.query_map(
        rusqlite::params![artista_id, (AUTO_THIS_IS_MAX_PISTAS * 4) as i64],
        |f| Ok((f.get::<_, i64>(0)?, f.get::<_, i64>(1)?)),
    ))?
    .collect::<rusqlite::Result<Vec<_>>>())?;

    let mut ids = Vec::new();
    let mut diferidos = Vec::new();
    let mut por_album: HashMap<i64, usize> = HashMap::new();
    for (pid, album_id) in filas {
        let n = por_album.entry(album_id).or_insert(0);
        if album_id != 0 && *n >= 8 {
            diferidos.push(pid);
            continue;
        }
        *n += 1;
        ids.push(pid);
        if ids.len() >= AUTO_THIS_IS_MAX_PISTAS {
            return Ok(ids);
        }
    }
    for pid in diferidos {
        if ids.len() >= AUTO_THIS_IS_MAX_PISTAS {
            break;
        }
        if !ids.contains(&pid) {
            ids.push(pid);
        }
    }

    if ids.len() < AUTO_THIS_IS_MIN_PISTAS {
        let faltan = AUTO_THIS_IS_MAX_PISTAS - ids.len();
        let mut s_sim = bd(conn.prepare(
            "SELECT p.id, coalesce(p.artista_id, 0)
             FROM pistas p
             LEFT JOIN (
                 SELECT pista_id, count(*) AS reproducciones
                 FROM historial WHERE pista_id IS NOT NULL GROUP BY pista_id
             ) h ON h.pista_id = p.id
             WHERE p.estado = 'biblioteca'
               AND p.artista_id IS NOT ?1
               AND lower(trim(coalesce(p.genero, ''))) IN (
                   SELECT DISTINCT lower(trim(genero)) FROM pistas
                   WHERE artista_id = ?1 AND estado = 'biblioteca' AND coalesce(trim(genero), '') <> ''
               )
             ORDER BY p.favorita DESC,
                      max(p.reproducciones, coalesce(h.reproducciones, 0)) DESC,
                      datetime(coalesce(p.ultima_reproduccion, p.actualizada_en, p.creada_en)) DESC,
                      p.titulo COLLATE NOCASE, p.id
             LIMIT ?2",
        ))?;
        let sim = bd(bd(s_sim
            .query_map(rusqlite::params![artista_id, (faltan * 4) as i64], |f| {
                Ok((f.get::<_, i64>(0)?, f.get::<_, i64>(1)?))
            }))?
        .collect::<rusqlite::Result<Vec<_>>>())?;
        let mut por_artista: HashMap<i64, usize> = HashMap::new();
        for (pid, otro_artista) in sim {
            if ids.contains(&pid) {
                continue;
            }
            let usados = por_artista.entry(otro_artista).or_insert(0);
            if *usados >= 4 {
                continue;
            }
            *usados += 1;
            ids.push(pid);
            if ids.len() >= AUTO_THIS_IS_MAX_PISTAS {
                break;
            }
        }
    }

    Ok(ids)
}

fn construir_specs(db: &BaseDeDatos, conn: &Connection) -> NsResult<Vec<SpecAutomatica>> {
    let mut specs = vec![
        SpecAutomatica {
            clave_auto: "auto:favoritas_sonando".to_owned(),
            nombre: "Favoritas que siguen sonando".to_owned(),
            descripcion: "Favoritas que también tienen historial de escucha local.".to_owned(),
            subtipo: "descubrimiento_local",
            regla_json: "{\"tipo\":\"favoritas_sonando\"}".to_owned(),
            min_pistas: 5,
            max_pistas: AUTO_MAX_PISTAS,
            candidatos: ids_consulta(
                conn,
                "SELECT p.id
                 FROM pistas p
                 LEFT JOIN (
                     SELECT pista_id, count(*) AS reproducciones
                     FROM historial WHERE pista_id IS NOT NULL GROUP BY pista_id
                 ) h ON h.pista_id = p.id
                 WHERE p.estado = 'biblioteca' AND p.favorita = 1
                   AND max(p.reproducciones, coalesce(h.reproducciones, 0)) > 0
                 ORDER BY max(p.reproducciones, coalesce(h.reproducciones, 0)) DESC,
                          datetime(coalesce(p.ultima_reproduccion, p.actualizada_en, p.creada_en)) DESC,
                          p.id
                 LIMIT ?1",
                AUTO_MAX_PISTAS,
            )?,
        },
        SpecAutomatica {
            clave_auto: "auto:redescubrir".to_owned(),
            nombre: "Para redescubrir".to_owned(),
            descripcion: "Canciones de tu biblioteca con señales locales para volver.".to_owned(),
            subtipo: "descubrimiento_local",
            regla_json: "{\"tipo\":\"redescubrir\"}".to_owned(),
            min_pistas: AUTO_STRONG_MIN_PISTAS,
            max_pistas: AUTO_MAX_PISTAS,
            candidatos: ids_consulta(
                conn,
                "SELECT p.id
                 FROM pistas p
                 LEFT JOIN (
                     SELECT pista_id, count(*) AS reproducciones
                     FROM historial WHERE pista_id IS NOT NULL GROUP BY pista_id
                 ) h ON h.pista_id = p.id
                 WHERE p.estado = 'biblioteca'
                   AND (p.favorita = 1 OR max(p.reproducciones, coalesce(h.reproducciones, 0)) > 0)
                 ORDER BY datetime(coalesce(p.ultima_reproduccion, p.creada_en, p.actualizada_en)) ASC,
                          max(p.reproducciones, coalesce(h.reproducciones, 0)) DESC,
                          p.titulo COLLATE NOCASE, p.id
                 LIMIT ?1",
                AUTO_MAX_PISTAS,
            )?,
        },
        SpecAutomatica {
            clave_auto: "auto:recientes_biblioteca".to_owned(),
            nombre: "Recientes de tu biblioteca".to_owned(),
            descripcion: "Últimas canciones añadidas a tu biblioteca local.".to_owned(),
            subtipo: "recientes",
            regla_json: "{\"tipo\":\"recientes\"}".to_owned(),
            min_pistas: AUTO_DESCUBRIR_MIN_PISTAS,
            max_pistas: AUTO_MAX_PISTAS,
            candidatos: ids_consulta(
                conn,
                "SELECT id FROM pistas WHERE estado = 'biblioteca'
                 ORDER BY datetime(coalesce(creada_en, actualizada_en)) DESC, titulo COLLATE NOCASE, id
                 LIMIT ?1",
                AUTO_MAX_PISTAS,
            )?,
        },
        SpecAutomatica {
            clave_auto: "auto:descubrir:canciones".to_owned(),
            nombre: "Canciones por descubrir".to_owned(),
            descripcion: "Canciones de tu biblioteca que todavía casi no han sonado.".to_owned(),
            subtipo: "descubrimiento_local",
            regla_json: "{\"tipo\":\"canciones_por_descubrir\",\"max_reproducciones\":9}".to_owned(),
            min_pistas: AUTO_DESCUBRIR_MIN_PISTAS,
            max_pistas: AUTO_MAX_PISTAS,
            candidatos: ids_consulta(
                conn,
                "SELECT p.id
                 FROM pistas p
                 LEFT JOIN (
                     SELECT pista_id, count(*) AS reproducciones
                     FROM historial WHERE pista_id IS NOT NULL GROUP BY pista_id
                 ) h ON h.pista_id = p.id
                 WHERE p.estado = 'biblioteca'
                   AND max(p.reproducciones, coalesce(h.reproducciones, 0)) < 10
                 ORDER BY max(p.reproducciones, coalesce(h.reproducciones, 0)) ASC,
                          datetime(coalesce(p.creada_en, p.actualizada_en)) DESC,
                          p.titulo COLLATE NOCASE, p.id
                 LIMIT ?1",
                AUTO_MAX_PISTAS,
            )?,
        },
        SpecAutomatica {
            clave_auto: "auto:recientes_sin_escuchar".to_owned(),
            nombre: "Recientes sin escuchar".to_owned(),
            descripcion: "Últimas canciones añadidas que aún no tienen reproducciones.".to_owned(),
            subtipo: "recientes",
            regla_json: "{\"tipo\":\"recientes_sin_escuchar\"}".to_owned(),
            min_pistas: 15,
            max_pistas: AUTO_MAX_PISTAS,
            candidatos: ids_consulta(
                conn,
                "SELECT p.id
                 FROM pistas p
                 LEFT JOIN (
                     SELECT pista_id, count(*) AS reproducciones
                     FROM historial WHERE pista_id IS NOT NULL GROUP BY pista_id
                 ) h ON h.pista_id = p.id
                 WHERE p.estado = 'biblioteca'
                   AND max(p.reproducciones, coalesce(h.reproducciones, 0)) = 0
                 ORDER BY datetime(coalesce(p.creada_en, p.actualizada_en)) DESC,
                          p.titulo COLLATE NOCASE, p.id
                 LIMIT ?1",
                AUTO_MAX_PISTAS,
            )?,
        },
        SpecAutomatica {
            clave_auto: "auto:favoritas_olvidadas".to_owned(),
            nombre: "Favoritas que no escuchas hace rato".to_owned(),
            descripcion: "Favoritas que llevan tiempo sin sonar en esta biblioteca.".to_owned(),
            subtipo: "descubrimiento_local",
            regla_json: "{\"tipo\":\"favoritas_olvidadas\"}".to_owned(),
            min_pistas: 5,
            max_pistas: AUTO_MAX_PISTAS,
            candidatos: ids_consulta(
                conn,
                "SELECT p.id
                 FROM pistas p
                 LEFT JOIN (
                     SELECT pista_id, max(reproducida_en) AS ultima
                     FROM historial WHERE pista_id IS NOT NULL GROUP BY pista_id
                 ) h ON h.pista_id = p.id
                 WHERE p.estado = 'biblioteca' AND p.favorita = 1
                   AND (coalesce(h.ultima, p.ultima_reproduccion) IS NULL
                        OR datetime(coalesce(h.ultima, p.ultima_reproduccion)) <= datetime('now', '-60 days'))
                 ORDER BY datetime(coalesce(h.ultima, p.ultima_reproduccion, p.creada_en, p.actualizada_en)) ASC,
                          p.titulo COLLATE NOCASE, p.id
                 LIMIT ?1",
                AUTO_MAX_PISTAS,
            )?,
        },
        SpecAutomatica {
            clave_auto: "auto:top_canciones".to_owned(),
            nombre: "Tu top canciones".to_owned(),
            descripcion: "Canciones con más reproducciones registradas localmente.".to_owned(),
            subtipo: "top_canciones",
            regla_json: "{\"tipo\":\"top_canciones\"}".to_owned(),
            min_pistas: AUTO_STRONG_MIN_PISTAS,
            max_pistas: AUTO_MAX_PISTAS,
            candidatos: candidatos_top_canciones(conn)?,
        },
        SpecAutomatica {
            clave_auto: "auto:artist_mix_frecuentes".to_owned(),
            nombre: "Mix de tus artistas frecuentes".to_owned(),
            descripcion: "Canciones combinadas de los artistas que más suenan en tu biblioteca.".to_owned(),
            subtipo: "artist_mix",
            regla_json: "{\"tipo\":\"artist_mix\"}".to_owned(),
            min_pistas: AUTO_STRONG_MIN_PISTAS,
            max_pistas: AUTO_MAX_PISTAS,
            candidatos: candidatos_artistas_frecuentes(conn)?,
        },
        SpecAutomatica {
            clave_auto: "auto:album_mix_frecuentes".to_owned(),
            nombre: "Mix de álbumes frecuentes".to_owned(),
            descripcion: "Canciones de álbumes con más actividad local.".to_owned(),
            subtipo: "album_mix",
            regla_json: "{\"tipo\":\"album_mix\"}".to_owned(),
            min_pistas: AUTO_STRONG_MIN_PISTAS,
            max_pistas: AUTO_MAX_PISTAS,
            candidatos: candidatos_albumes_frecuentes(conn)?,
        },
        SpecAutomatica {
            clave_auto: "auto:albumes_para_volver".to_owned(),
            nombre: "Vuelve a esos álbumes".to_owned(),
            descripcion: "Canciones de álbumes con actividad suficiente para retomarlos.".to_owned(),
            subtipo: "album_mix",
            regla_json: "{\"tipo\":\"albumes_para_volver\"}".to_owned(),
            min_pistas: AUTO_STRONG_MIN_PISTAS,
            max_pistas: AUTO_MAX_PISTAS,
            candidatos: candidatos_albumes_para_volver(conn)?,
        },
    ];

    // Artistas con al menos 20 pistas en la biblioteca -> "This is <Artista>".
    let artistas: Vec<(i64, String)> = {
        let mut s = bd(conn.prepare(
            "SELECT a.id, a.nombre,
                    count(p.id) AS total_pistas,
                    sum(p.favorita) AS total_favs,
                    sum(max(p.reproducciones, coalesce(h.reproducciones, 0))) AS total_reps
             FROM artistas a
             JOIN pistas p ON p.artista_id = a.id AND p.estado = 'biblioteca'
             LEFT JOIN (
                 SELECT pista_id, count(*) AS reproducciones
                 FROM historial WHERE pista_id IS NOT NULL GROUP BY pista_id
             ) h ON h.pista_id = p.id
             GROUP BY a.id
             HAVING total_pistas >= ?1
             ORDER BY total_pistas DESC, (total_favs * 20 + total_reps * 3) DESC, a.nombre COLLATE NOCASE",
        ))?;
        let r = bd(
            bd(s.query_map([AUTO_THIS_IS_ARTISTA_MIN], |f| Ok((f.get(0)?, f.get(1)?))))?
                .collect::<rusqlite::Result<Vec<_>>>(),
        )?;
        r
    };

    for (artista_id, nombre) in artistas {
        let nombre = nombre.trim().to_owned();
        if nombre.is_empty() {
            continue;
        }
        let candidatos = candidatos_this_is(conn, artista_id)?;
        specs.push(SpecAutomatica {
            clave_auto: format!("auto:this_is:{artista_id}"),
            nombre: format!("This is {nombre}"),
            descripcion: format!("Canciones de {nombre} en tu biblioteca local."),
            subtipo: "this_is",
            regla_json: serde_json::json!({
                "tipo": "this_is",
                "artista_id": artista_id,
                "artista_nombre": nombre
            })
            .to_string(),
            min_pistas: AUTO_THIS_IS_MIN_PISTAS,
            max_pistas: AUTO_THIS_IS_MAX_PISTAS,
            candidatos,
        });
    }

    // Las siete listas por ánimo de la V1 apoyadas en `descubrir` (confianza >= 0,45).
    for (clave_auto, nombre, consulta) in [
        ("auto:mood:workout", "Para entrenar", "para entrenar"),
        ("auto:mood:party", "Para fiesta", "para fiesta"),
        ("auto:mood:focus", "Para concentrarme", "para concentrarme"),
        ("auto:mood:chill", "Algo tranquilo", "algo tranquilo"),
        ("auto:mood:night", "Algo de noche", "algo de noche"),
        ("auto:mood:fast", "Rápidas", "rápido"),
        (
            "auto:mood:sad_energy",
            "Tristes pero con energía",
            "algo triste pero con energía",
        ),
    ] {
        let candidatos =
            crate::descubrir::candidatos_con_confianza(db, consulta, 0.45, AUTO_MAX_PISTAS)?;
        specs.push(SpecAutomatica {
            clave_auto: clave_auto.to_owned(),
            nombre: nombre.to_owned(),
            descripcion: "Selección local creada con el análisis de audio.".to_owned(),
            subtipo: "mood",
            regla_json: serde_json::json!({ "tipo": "mood", "query": consulta }).to_string(),
            min_pistas: AUTO_FEATURE_MIN_PISTAS,
            max_pistas: AUTO_MAX_PISTAS,
            candidatos,
        });
    }

    Ok(specs)
}

/// Regenera las playlists automáticas de la V1 ("Crear para mí") y refresca las
/// listas inteligentes vivas del usuario. Devuelve cuántas playlists se crearon
/// o actualizaron.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si alguna lectura o escritura falla.
pub fn regenerar_automaticas(db: &BaseDeDatos) -> NsResult<u32> {
    let mut tocadas = refrescar_inteligentes(db)?;
    let specs = {
        let conn = db.conexion()?;
        construir_specs(db, &conn)?
    };
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    for mut spec in specs {
        let existente: Option<(i64, bool, bool, bool)> = bd(tx
            .query_row(
                "SELECT id, visible = 1, editada = 1, auto_actualizable = 1
                 FROM playlists WHERE clave_auto = ?1",
                [&spec.clave_auto],
                |f| Ok((f.get(0)?, f.get(1)?, f.get(2)?, f.get(3)?)),
            )
            .optional())?;

        if let Some((_, _, editada, auto_act)) = existente {
            if editada || !auto_act {
                continue;
            }
        }

        if spec.candidatos.len() < spec.min_pistas {
            if let Some((id, visible, false, true)) = existente {
                if visible {
                    bd(tx.execute(
                        "UPDATE playlists SET visible = 0,
                             actualizada_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                         WHERE id = ?1",
                        [id],
                    ))?;
                }
            }
            continue;
        }

        spec.candidatos.truncate(spec.max_pistas);
        if let Some((id, visible, _, _)) = existente {
            if !visible {
                bd(tx.execute(
                    "UPDATE playlists SET visible = 1,
                         actualizada_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                     WHERE id = ?1",
                    [id],
                ))?;
            }
            if escribir_pistas_playlist(&tx, id, &spec.candidatos)? || !visible {
                tocadas += 1;
            }
        } else {
            // Si el usuario ya tiene una playlist visible con ese mismo nombre, no se pisa.
            if validar_nombre(&tx, &spec.nombre, None).is_err() {
                continue;
            }
            bd(tx.execute(
                "INSERT INTO playlists (nombre, descripcion, tipo, subtipo, origen, regla,
                                        clave_auto, visible, auto_actualizable, editada, generada_en)
                 VALUES (?1, ?2, 'automatica', ?3, 'generado', ?4, ?5, 1, 1, 0,
                         strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
                rusqlite::params![
                    spec.nombre,
                    spec.descripcion,
                    spec.subtipo,
                    spec.regla_json,
                    spec.clave_auto,
                ],
            ))?;
            let id = tx.last_insert_rowid();
            escribir_pistas_playlist(&tx, id, &spec.candidatos)?;
            tocadas += 1;
        }
    }
    bd(tx.commit())?;
    Ok(tocadas)
}
