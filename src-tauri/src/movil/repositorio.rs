//! Lo que el servidor móvil lee y escribe en la base: los teléfonos, su
//! selección, el historial y los favoritos que suben, y los archivos que piden.
//!
//! Es `sync_repositorio.py` de la V1 sobre el esquema de la V2. La diferencia que
//! importa: el `device_token` no se guarda, solo su SHA-256 (V5).

use std::collections::HashSet;
use std::path::PathBuf;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use rusqlite::{params, OptionalExtension};
use serde::Serialize;
use serde_json::Value;
use ts_rs::TS;

use super::emparejamiento;
use crate::db::{self, BaseDeDatos};
use crate::error::{NsError, NsResult};
use crate::paths::Rutas;
use crate::reproductor::persistencia;

fn bd<T>(r: rusqlite::Result<T>) -> NsResult<T> {
    r.map_err(|error| {
        tracing::error!(error = %error, "falló una consulta del servidor móvil");
        NsError::StorageFailure
    })
}

/// Las plataformas que acepta la V1; cualquier otra es `desconocida`.
const PLATAFORMAS: [&str; 5] = ["android", "ios", "ipados", "tablet", "desconocida"];

/// Un teléfono cuenta como conectado si tocó el servidor en este margen: más que
/// el latido del móvil (~25 s), para que un salto no lo haga parpadear (la V1).
pub const VENTANA_PRESENCIA: Duration = Duration::from_secs(75);

/// Tope de teléfonos que se listan: en la instalación real hay doce, once
/// revocados, y cada emparejamiento lo hace una persona a mano.
pub const MAX_DISPOSITIVOS: usize = 200;

/// ISO 8601 en UTC con microsegundos, como `_ahora_iso` de la V1. Las mismas
/// cifras que la V1 importan: el `content-length` de las respuestas doradas las
/// cuenta, y el orden de las cadenas es el cronológico.
pub fn iso(t: SystemTime) -> String {
    let d = t.duration_since(UNIX_EPOCH).unwrap_or_default();
    let segundos = d.as_secs() as i64;
    let (dias, resto) = (segundos.div_euclid(86_400), segundos.rem_euclid(86_400));
    // Días desde 1970 a fecha civil (Howard Hinnant, `civil_from_days`).
    let z = dias + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z.rem_euclid(146_097);
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let dia = doy - (153 * mp + 2) / 5 + 1;
    let mes = if mp < 10 { mp + 3 } else { mp - 9 };
    let anio = yoe + era * 400 + i64::from(mes <= 2);
    format!(
        "{anio:04}-{mes:02}-{dia:02}T{:02}:{:02}:{:02}.{:06}Z",
        resto / 3600,
        resto / 60 % 60,
        resto % 60,
        d.subsec_micros()
    )
}

pub fn ahora() -> String {
    iso(SystemTime::now())
}

/// Un teléfono emparejado.
#[derive(Debug, Clone, PartialEq)]
pub struct Dispositivo {
    pub id: i64,
    pub nombre: String,
    pub seleccion: Option<Value>,
}

/// Lo que ve Ajustes > Dispositivos.
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct Telefono {
    #[ts(type = "number")]
    pub id: i64,
    pub nombre: String,
    pub plataforma: Option<String>,
    pub ultima_conexion: Option<String>,
    /// Tocó el servidor hace poco (latido, sincronización o control).
    pub conectado: bool,
    /// Tiene abierto el control remoto: está manejando este equipo.
    pub controlando: bool,
}

/// Empareja un teléfono y devuelve su id y su `device_token`, que solo viaja en
/// esta respuesta.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si no se puede escribir.
pub fn registrar(
    db: &BaseDeDatos,
    nombre: &str,
    plataforma: Option<&str>,
) -> NsResult<(i64, String, String)> {
    let nombre = match nombre.trim() {
        "" => "Dispositivo móvil".to_owned(),
        n => n.chars().take(120).collect(),
    };
    let plataforma = plataforma
        .map(|p| p.trim().to_lowercase())
        .filter(|p| PLATAFORMAS.contains(&p.as_str()))
        .unwrap_or_else(|| "desconocida".to_owned());
    let token = emparejamiento::generar_token()?;
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    bd(tx.execute(
        "INSERT INTO dispositivos (token_sha256, nombre, plataforma, ultima_conexion)
         VALUES (?1, ?2, ?3, ?4)",
        params![
            emparejamiento::huella_token(&token),
            nombre,
            plataforma,
            ahora()
        ],
    ))?;
    let id = tx.last_insert_rowid();
    bd(tx.commit())?;
    Ok((id, token, nombre))
}

/// El teléfono dueño de un token, si no está revocado.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn por_token(db: &BaseDeDatos, token: &str) -> NsResult<Option<Dispositivo>> {
    if token.is_empty() {
        return Ok(None);
    }
    let conn = db.conexion()?;
    let fila = bd(conn
        .query_row(
            "SELECT id, nombre, seleccion FROM dispositivos
             WHERE token_sha256 = ?1 AND revocado = 0",
            [emparejamiento::huella_token(token)],
            |f| {
                Ok((
                    f.get::<_, i64>(0)?,
                    f.get::<_, String>(1)?,
                    f.get::<_, Option<String>>(2)?,
                ))
            },
        )
        .optional())?;
    Ok(fila.map(|(id, nombre, seleccion)| Dispositivo {
        id,
        nombre,
        seleccion: seleccion.and_then(|s| serde_json::from_str(&s).ok()),
    }))
}

fn actualizar(db: &BaseDeDatos, sql: &str, p: impl rusqlite::Params) -> NsResult<usize> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    let n = bd(tx.execute(sql, p))?;
    bd(tx.commit())?;
    Ok(n)
}

/// # Errors
///
/// [`NsError::StorageFailure`] si no se puede escribir.
pub fn tocar(db: &BaseDeDatos, id: i64) -> NsResult<()> {
    actualizar(
        db,
        "UPDATE dispositivos SET ultima_conexion = ?1 WHERE id = ?2",
        params![ahora(), id],
    )
    .map(|_| ())
}

/// # Errors
///
/// [`NsError::StorageFailure`] si no se puede escribir.
pub fn guardar_seleccion(db: &BaseDeDatos, id: i64, seleccion: &Value) -> NsResult<()> {
    actualizar(
        db,
        "UPDATE dispositivos SET seleccion = ?1 WHERE id = ?2",
        params![seleccion.to_string(), id],
    )
    .map(|_| ())
}

/// # Errors
///
/// [`NsError::StorageFailure`] si no se puede escribir.
pub fn guardar_ultima_sync(db: &BaseDeDatos, id: i64, version: i64) -> NsResult<()> {
    actualizar(
        db,
        "UPDATE dispositivos SET ultima_sync_version = ?1 WHERE id = ?2",
        params![version.max(0), id],
    )
    .map(|_| ())
}

/// Revoca un teléfono: su token deja de valer. Se conserva la fila para que lo
/// siga rechazando. `false` si no existía o ya estaba revocado.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si no se puede escribir.
pub fn revocar(db: &BaseDeDatos, id: i64) -> NsResult<bool> {
    actualizar(
        db,
        "UPDATE dispositivos SET revocado = 1 WHERE id = ?1 AND revocado = 0",
        [id],
    )
    .map(|n| n > 0)
}

/// Los teléfonos no revocados, del más reciente al más antiguo, como la V1.
/// Cota: [`MAX_DISPOSITIVOS`].
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn listar(db: &BaseDeDatos, controlando: &HashSet<i64>) -> NsResult<Vec<Telefono>> {
    let corte = iso(SystemTime::now() - VENTANA_PRESENCIA);
    let conn = db.conexion()?;
    let mut s = bd(conn.prepare(
        "SELECT id, nombre, plataforma, ultima_conexion, coalesce(ultima_conexion >= ?1, 0)
         FROM dispositivos WHERE revocado = 0
         ORDER BY ultima_conexion IS NULL, ultima_conexion DESC, id DESC LIMIT ?2",
    ))?;
    let filas = bd(s.query_map(params![corte, MAX_DISPOSITIVOS as i64], |f| {
        let id: i64 = f.get(0)?;
        Ok(Telefono {
            id,
            nombre: f.get(1)?,
            plataforma: f.get(2)?,
            ultima_conexion: f.get(3)?,
            conectado: f.get::<_, bool>(4)? || controlando.contains(&id),
            controlando: controlando.contains(&id),
        })
    }))?;
    bd(filas.collect())
}

/// Lo que respondió el merge de `POST /history`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub struct ResultadoHistorial {
    pub historial_insertado: u32,
    pub favoritos_aplicados: u32,
    pub favoritos_ignorados: u32,
}

fn entero(v: Option<&Value>) -> Option<i64> {
    match v? {
        Value::Number(n) => n.as_i64().or_else(|| n.as_f64().map(|f| f as i64)),
        Value::String(s) => s.trim().parse().ok(),
        _ => None,
    }
}

/// La verdad de Python: lo que la V1 entendía por `if valor`.
pub fn verdad(v: Option<&Value>) -> bool {
    match v {
        None | Some(Value::Null) => false,
        Some(Value::Bool(b)) => *b,
        Some(Value::Number(n)) => n.as_f64().is_some_and(|f| f != 0.0),
        Some(Value::String(s)) => !s.is_empty(),
        Some(Value::Array(a)) => !a.is_empty(),
        Some(Value::Object(o)) => !o.is_empty(),
    }
}

/// Aplica el historial y los favoritos del teléfono (`aplicar_historial_remoto`).
///
/// El historial se añade siempre; el favorito del teléfono gana solo si su marca de
/// tiempo es estrictamente más reciente que la del equipo (sin marca, no gana).
/// Dos diferencias con la V1, las dos para no guardar basura: una escucha de una
/// pista que el equipo no tiene no se apunta (la V1 la apuntaba sin título), y
/// una escucha completa suma una reproducción, como las del equipo.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si no se puede escribir.
pub fn aplicar_historial(db: &BaseDeDatos, payload: &Value) -> NsResult<ResultadoHistorial> {
    let lista = |clave: &str| {
        payload
            .get(clave)
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default()
    };
    let mut r = ResultadoHistorial {
        historial_insertado: 0,
        favoritos_aplicados: 0,
        favoritos_ignorados: 0,
    };
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    for ev in lista("historial") {
        let Some(pista) = entero(ev.get("pista_id")) else {
            continue;
        };
        let cuando = ev
            .get("reproducido_en")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|s| !s.is_empty() && s.len() <= 40)
            .map_or_else(ahora, str::to_owned);
        let completada = ev.get("completada").is_none_or(|c| verdad(Some(c)));
        let segundos = ev
            .get("duracion_seg")
            .and_then(Value::as_f64)
            .filter(|s| s.is_finite() && *s >= 0.0);
        let n = bd(tx.execute(
            "INSERT INTO historial (pista_id, titulo, artista, reproducida_en, escuchado_seg, completada)
             SELECT id, titulo, artista_nombre, ?2, ?3, ?4 FROM pistas WHERE id = ?1",
            params![pista, cuando, segundos, completada],
        ))?;
        if n == 0 {
            continue;
        }
        if completada {
            bd(tx.execute(
                "UPDATE pistas SET reproducciones = reproducciones + 1,
                     ultima_reproduccion = max(coalesce(ultima_reproduccion, ''), ?2)
                 WHERE id = ?1",
                params![pista, cuando],
            ))?;
        }
        r.historial_insertado += 1;
    }
    for fav in lista("favoritos") {
        let Some(pista) = entero(fav.get("pista_id")) else {
            continue;
        };
        let remoto = fav
            .get("actualizada_en")
            .and_then(Value::as_str)
            .map(str::trim)
            .unwrap_or_default()
            .to_owned();
        let local: Option<Option<String>> = bd(tx
            .query_row(
                "SELECT favorita_actualizada_en FROM pistas WHERE id = ?1",
                [pista],
                |f| f.get(0),
            )
            .optional())?;
        let Some(local) = local else {
            continue;
        };
        let local = local.unwrap_or_default();
        if remoto.is_empty() || (!local.trim().is_empty() && remoto.as_str() <= local.trim()) {
            r.favoritos_ignorados += 1;
            continue;
        }
        let favorita = verdad(fav.get("favorita"));
        bd(tx.execute(
            "UPDATE pistas SET favorita = ?2, favorita_actualizada_en = ?3,
                 actualizada_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
             WHERE id = ?1",
            params![pista, favorita, remoto],
        ))?;
        // "Me gusta" la mantiene la V2 al marcar favoritas; si todavía no existe, la
        // creará entera la primera vez que se necesite (`playlists`).
        crate::playlists::reflejar_favorita_si_existe(&tx, pista, favorita)?;
        r.favoritos_aplicados += 1;
    }
    bd(tx.commit())?;
    Ok(r)
}

/// El archivo de audio de una pista y su SHA-256, si existe.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn audio(db: &BaseDeDatos, pista: i64) -> NsResult<Option<(PathBuf, Option<String>)>> {
    let conn = db.conexion()?;
    let musica = persistencia::carpeta_musica(&conn)?;
    let fila: Option<(String, Option<String>)> = bd(conn
        .query_row(
            "SELECT ruta, sha256 FROM pistas WHERE id = ?1",
            [pista],
            |f| Ok((f.get(0)?, f.get(1)?)),
        )
        .optional())?;
    Ok(fila.and_then(|(ruta, sha)| {
        let ruta = PathBuf::from(ruta);
        let ruta = match &musica {
            Some(m) if ruta.is_relative() => m.join(ruta),
            _ => ruta,
        };
        ruta.is_file().then_some((ruta, sha))
    }))
}

/// El instrumental de una pista, si está listo y en su sitio.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn instrumental(db: &BaseDeDatos, rutas: &Rutas, pista: i64) -> NsResult<Option<PathBuf>> {
    let conn = db.conexion()?;
    let relativa: Option<String> = bd(conn
        .query_row(
            "SELECT instrumental FROM stems WHERE pista_id = ?1 AND estado = 'lista'",
            [pista],
            |f| f.get(0),
        )
        .optional())?
    .flatten();
    Ok(relativa
        .and_then(|r| {
            crate::security::resolve_within(&rutas.stems(), std::path::Path::new(&r)).ok()
        })
        .filter(|r| r.is_file()))
}

/// # Errors
///
/// [`NsError::StorageFailure`] si no se puede escribir.
pub fn transferencia_iniciada(db: &BaseDeDatos, dispositivo: i64, pista: i64) -> NsResult<()> {
    actualizar(
        db,
        "INSERT INTO transferencias_stems (dispositivo_id, pista_id, estado, bytes_enviados)
         VALUES (?1, ?2, 'in_progress', 0)
         ON CONFLICT (dispositivo_id, pista_id) DO UPDATE SET estado = 'in_progress',
             bytes_enviados = 0, actualizada_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')",
        params![dispositivo, pista],
    )
    .map(|_| ())
}

/// Las letras de una pista: sincronizadas y planas, vacías si no hay.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn letras(db: &BaseDeDatos, pista: i64) -> NsResult<(String, String)> {
    let conn = db.conexion()?;
    let fila: Option<(Option<String>, Option<String>)> = bd(conn
        .query_row(
            "SELECT sincronizadas, planas FROM letras WHERE pista_id = ?1",
            [pista],
            |f| Ok((f.get(0)?, f.get(1)?)),
        )
        .optional())?;
    let (s, p) = fila.unwrap_or_default();
    Ok((s.unwrap_or_default(), p.unwrap_or_default()))
}

/// Una portada original: el archivo y su tipo.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn imagen(
    db: &BaseDeDatos,
    rutas: &Rutas,
    de_artista: bool,
    id: i64,
) -> NsResult<Option<(PathBuf, String)>> {
    let sql = if de_artista {
        "SELECT po.ruta, po.mime FROM artistas a JOIN portadas po ON po.id = a.imagen_id WHERE a.id = ?1"
    } else {
        "SELECT po.ruta, po.mime FROM albumes a JOIN portadas po ON po.id = a.portada_id WHERE a.id = ?1"
    };
    let conn = db.conexion()?;
    let fila: Option<(String, String)> = bd(conn
        .query_row(sql, [id], |f| Ok((f.get(0)?, f.get(1)?)))
        .optional())?;
    Ok(fila.and_then(|(ruta, mime)| {
        let ruta =
            crate::security::resolve_within(&rutas.portadas(), std::path::Path::new(&ruta)).ok()?;
        ruta.is_file().then_some((ruta, mime))
    }))
}

/// Las portadas (distintas, en orden) de las primeras pistas de una playlist, para
/// su mosaico. Cota: cuatro.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn portadas_de_playlist(
    db: &BaseDeDatos,
    rutas: &Rutas,
    id: i64,
) -> NsResult<Vec<(i64, PathBuf)>> {
    let conn = db.conexion()?;
    let mut s = bd(conn.prepare(
        "SELECT po.id, po.ruta, min(pp.posicion) AS orden FROM playlist_pistas pp
         JOIN pistas p ON p.id = pp.pista_id
         LEFT JOIN albumes a ON a.id = p.album_id
         JOIN portadas po ON po.id = coalesce(p.portada_id, a.portada_id)
         JOIN playlists pl ON pl.id = pp.playlist_id AND pl.visible = 1
         WHERE pp.playlist_id = ?1 GROUP BY po.id ORDER BY orden LIMIT 4",
    ))?;
    let filas = bd(s.query_map([id], |f| Ok((f.get::<_, i64>(0)?, f.get::<_, String>(1)?))))?;
    Ok(bd(filas.collect::<rusqlite::Result<Vec<_>>>())?
        .into_iter()
        .filter_map(|(id, r)| {
            crate::security::resolve_within(&rutas.portadas(), std::path::Path::new(&r))
                .ok()
                .map(|r| (id, r))
        })
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn la_fecha_tiene_el_formato_de_la_v1() {
        let t = UNIX_EPOCH + Duration::new(1_780_000_000, 123_456_000);
        assert_eq!(iso(t), "2026-05-28T20:26:40.123456Z");
        assert_eq!(iso(UNIX_EPOCH), "1970-01-01T00:00:00.000000Z");
        assert_eq!(
            iso(UNIX_EPOCH + Duration::from_secs(951_782_400)),
            "2000-02-29T00:00:00.000000Z"
        );
    }

    #[test]
    fn el_token_no_se_guarda_y_sirve_hasta_revocarse() {
        let db = BaseDeDatos::en_memoria().unwrap();
        let (id, token, nombre) = registrar(&db, "  ", Some("ANDROID")).unwrap();
        assert_eq!(nombre, "Dispositivo móvil");
        let guardado: (String, String) = db
            .conexion()
            .unwrap()
            .query_row(
                "SELECT token_sha256, plataforma FROM dispositivos",
                [],
                |f| Ok((f.get(0)?, f.get(1)?)),
            )
            .unwrap();
        assert_ne!(guardado.0, token);
        assert_eq!(guardado.1, "android");
        assert_eq!(por_token(&db, &token).unwrap().unwrap().id, id);
        assert!(por_token(&db, "otro").unwrap().is_none());
        assert!(revocar(&db, id).unwrap());
        assert!(!revocar(&db, id).unwrap());
        assert!(
            por_token(&db, &token).unwrap().is_none(),
            "revocado no entra"
        );
    }

    #[test]
    fn la_plataforma_desconocida_se_normaliza() {
        let db = BaseDeDatos::en_memoria().unwrap();
        registrar(&db, "x", Some("symbian")).unwrap();
        registrar(&db, "y", None).unwrap();
        let n: i64 = db
            .conexion()
            .unwrap()
            .query_row(
                "SELECT count(*) FROM dispositivos WHERE plataforma = 'desconocida'",
                [],
                |f| f.get(0),
            )
            .unwrap();
        assert_eq!(n, 2);
    }

    fn con_pistas() -> BaseDeDatos {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO pistas (id, titulo, ruta, favorita, favorita_actualizada_en) VALUES
                     (1, 'uno', 'a', 0, '2026-01-01T00:00:00.000Z'), (2, 'dos', 'b', 1, NULL);",
            )
            .unwrap();
        db
    }

    #[test]
    fn el_favorito_mas_reciente_gana_y_sin_marca_no_pisa() {
        let db = con_pistas();
        let r = aplicar_historial(
            &db,
            &json!({"favoritos": [
                {"pista_id": 1, "favorita": true, "actualizada_en": "2026-01-01T00:00:00.000Z"},
                {"pista_id": 1, "favorita": true, "actualizada_en": "2026-02-01T00:00:00.000Z"},
                {"pista_id": 2, "favorita": false},
                {"pista_id": 99, "favorita": true, "actualizada_en": "2030-01-01T00:00:00.000Z"},
            ]}),
        )
        .unwrap();
        assert_eq!((r.favoritos_aplicados, r.favoritos_ignorados), (1, 2));
        let (f1, f2): (bool, bool) = db
            .conexion()
            .unwrap()
            .query_row(
                "SELECT (SELECT favorita FROM pistas WHERE id = 1), (SELECT favorita FROM pistas WHERE id = 2)",
                [],
                |f| Ok((f.get(0)?, f.get(1)?)),
            )
            .unwrap();
        assert!(f1 && f2);
    }

    #[test]
    fn el_historial_del_telefono_cuenta_como_escucha() {
        let db = con_pistas();
        let r = aplicar_historial(
            &db,
            &json!({"historial": [
                {"pista_id": 1, "reproducido_en": "2026-05-30T10:00:00.000Z", "duracion_seg": 180.0},
                {"pista_id": "2", "completada": false},
                {"pista_id": 99},
                {"pista_id": null},
            ]}),
        )
        .unwrap();
        assert_eq!(
            r.historial_insertado, 2,
            "la pista que no existe no se apunta"
        );
        let (n, rep1, rep2): (i64, i64, i64) = db
            .conexion()
            .unwrap()
            .query_row(
                "SELECT (SELECT count(*) FROM historial), (SELECT reproducciones FROM pistas WHERE id = 1),
                        (SELECT reproducciones FROM pistas WHERE id = 2)",
                [],
                |f| Ok((f.get(0)?, f.get(1)?, f.get(2)?)),
            )
            .unwrap();
        assert_eq!((n, rep1, rep2), (2, 1, 0), "la saltada no suma");
    }

    #[test]
    fn la_verdad_es_la_de_python() {
        assert!(!verdad(Some(&json!(0))));
        assert!(!verdad(Some(&json!(""))));
        assert!(verdad(Some(&json!("no"))));
        assert!(verdad(Some(&json!(1))));
        assert!(!verdad(None));
    }
}
