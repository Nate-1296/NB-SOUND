//! Las rutas HTTP del protocolo `1` (F3.1.1 a F3.1.6), con las respuestas de la
//! V1: mismos códigos, mismos cuerpos de error y mismas cabeceras.
//!
//! Lo que la V1 dejaba a `aiohttp` sin decirlo también se reproduce, porque el
//! teléfono lo recibió durante todo su desarrollo y las respuestas doradas lo
//! guardan: un id de pista que no es un número da 404 y no 400, el 404 de una
//! ruta desconocida es texto plano, y los archivos se sirven con `Range`.

use std::io::SeekFrom;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::{Instant, SystemTime};

use axum::body::{Body, Bytes};
use axum::extract::{Path, Request, State};
use axum::http::{header, HeaderMap, HeaderValue, StatusCode};
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::Router;
use serde::Serialize;
use serde_json::{json, Value};
use tokio::io::{AsyncReadExt, AsyncSeekExt};

use super::repositorio::{self, Dispositivo};
use super::{control, json as pyjson, manifiesto, mosaico, Contexto};
use crate::error::{NsError, NsResult};

/// Cada cuánto se apunta, como mucho, la última conexión de un teléfono. Cada
/// tramo de una descarga es una petición, y la presencia tiene 75 s de margen.
const INTERVALO_TOQUE: std::time::Duration = std::time::Duration::from_secs(15);

/// Lo que se lee de un archivo en cada trozo de la respuesta.
const TROZO: usize = 64 * 1024;

pub fn rutas(ctx: Arc<Contexto>) -> Router {
    Router::new()
        .route("/api/v1/ping", get(ping))
        .route("/api/v1/pair", post(emparejar))
        .route("/api/v1/manifest", get(manifiesto))
        .route("/api/v1/seleccion", get(seleccion).post(fijar_seleccion))
        .route("/api/v1/track/{id}/audio", get(audio))
        .route("/api/v1/track/{id}/stems", get(stems))
        .route("/api/v1/track/{id}/lyrics", get(letras))
        .route("/api/v1/asset/{tipo}/{id}", get(imagen))
        .route("/api/v1/history", post(historial))
        .route("/api/v1/control", get(control::abrir))
        .fallback(no_existe)
        .layer(axum::middleware::from_fn_with_state(
            Arc::clone(&ctx),
            autenticar,
        ))
        .with_state(ctx)
}

/// Una respuesta JSON con el formato de la V1.
pub fn json<T: Serialize + ?Sized>(estado: StatusCode, cuerpo: &T) -> Response {
    (
        estado,
        [(
            header::CONTENT_TYPE,
            HeaderValue::from_static("application/json; charset=utf-8"),
        )],
        pyjson::a_bytes(cuerpo),
    )
        .into_response()
}

fn error(estado: StatusCode, codigo: &str) -> Response {
    json(estado, &json!({ "error": codigo }))
}

/// Las consultas a la base bloquean: van al hilo de bloqueo de tokio, no a los del
/// servidor, que atienden a todos los teléfonos.
pub async fn bloqueo<T: Send + 'static>(
    f: impl FnOnce() -> NsResult<T> + Send + 'static,
) -> NsResult<T> {
    tokio::task::spawn_blocking(f)
        .await
        .map_err(|_| NsError::Internal)?
}

fn fallo_interno() -> Response {
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        "500: Internal Server Error",
    )
        .into_response()
}

fn bearer(cabeceras: &HeaderMap) -> String {
    let valor = |nombre: &str| {
        cabeceras
            .get(nombre)
            .and_then(|v| v.to_str().ok())
            .unwrap_or_default()
    };
    let auth = valor("authorization");
    if auth.len() >= 7 && auth[..7].eq_ignore_ascii_case("bearer ") {
        return auth[7..].trim().to_owned();
    }
    valor("x-device-token").trim().to_owned()
}

/// Apunta que el teléfono está ahí, sin escribir en la base en cada petición.
async fn tocar(ctx: &Arc<Contexto>, id: i64) {
    let toca = {
        let mut t = ctx
            .toques
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        match t.get(&id) {
            Some(antes) if antes.elapsed() < INTERVALO_TOQUE => false,
            _ => {
                t.insert(id, Instant::now());
                true
            }
        }
    };
    if toca {
        let db = ctx.db.clone();
        let _ = bloqueo(move || repositorio::tocar(&db, id)).await;
        (ctx.avisar)();
    }
}

async fn dispositivo(ctx: &Arc<Contexto>, cabeceras: &HeaderMap) -> Option<Dispositivo> {
    let token = bearer(cabeceras);
    if token.is_empty() {
        return None;
    }
    let db = ctx.db.clone();
    bloqueo(move || repositorio::por_token(&db, &token))
        .await
        .ok()
        .flatten()
}

/// Todo exige un `device_token` salvo `ping` y `pair`. `ping` con token vale de
/// latido: el teléfono lo manda cada ~25 s para figurar como conectado.
async fn autenticar(
    State(ctx): State<Arc<Contexto>>,
    mut peticion: Request,
    siguiente: Next,
) -> Response {
    let ruta = peticion.uri().path();
    if ruta == "/api/v1/pair" {
        return siguiente.run(peticion).await;
    }
    let disp = dispositivo(&ctx, peticion.headers()).await;
    if ruta == "/api/v1/ping" {
        if let Some(d) = &disp {
            tocar(&ctx, d.id).await;
        }
        return siguiente.run(peticion).await;
    }
    let Some(d) = disp else {
        return error(StatusCode::UNAUTHORIZED, "no_autorizado");
    };
    tocar(&ctx, d.id).await;
    peticion.extensions_mut().insert(d);
    siguiente.run(peticion).await
}

async fn no_existe() -> Response {
    (
        StatusCode::NOT_FOUND,
        [(
            header::CONTENT_TYPE,
            HeaderValue::from_static("text/plain; charset=utf-8"),
        )],
        "404: Not Found",
    )
        .into_response()
}

#[derive(Serialize)]
struct Ping<'a> {
    ok: bool,
    servicio: &'a str,
    version_protocolo: u32,
}

async fn ping(State(ctx): State<Arc<Contexto>>) -> Response {
    json(
        StatusCode::OK,
        &Ping {
            ok: true,
            servicio: &ctx.nombre,
            version_protocolo: manifiesto::PROTOCOLO,
        },
    )
}

/// Lo que haría `str(valor or "")` en la V1.
fn texto_python(v: Option<&Value>) -> String {
    match v {
        Some(Value::String(s)) => s.clone(),
        Some(v) if repositorio::verdad(Some(v)) => match v {
            Value::Bool(_) => "True".to_owned(),
            otro => otro.to_string(),
        },
        _ => String::new(),
    }
}

async fn emparejar(State(ctx): State<Arc<Contexto>>, cuerpo: Bytes) -> Response {
    let datos: Value = serde_json::from_slice(&cuerpo)
        .ok()
        .filter(Value::is_object)
        .unwrap_or_else(|| json!({}));
    // El token largo del QR o el código corto, en `token` o en `codigo`.
    let credencial = {
        let t = texto_python(datos.get("token"));
        if t.is_empty() {
            texto_python(datos.get("codigo"))
        } else {
            t
        }
    };
    let valida = ctx
        .emparejamiento
        .lock()
        .map(|e| e.valida(&credencial))
        .unwrap_or(false);
    if !valida {
        return error(StatusCode::UNAUTHORIZED, "token_invalido_o_expirado");
    }
    let nombre = {
        let n = texto_python(datos.get("nombre_dispositivo"));
        if n.is_empty() {
            texto_python(datos.get("nombre"))
        } else {
            n
        }
    };
    let plataforma = datos
        .get("plataforma")
        .and_then(Value::as_str)
        .map(str::to_owned);
    let db = ctx.db.clone();
    let Ok((id, token, nombre)) =
        bloqueo(move || repositorio::registrar(&db, &nombre, plataforma.as_deref())).await
    else {
        return fallo_interno();
    };
    // De un solo uso: el siguiente teléfono necesita un QR nuevo.
    if let Ok(mut e) = ctx.emparejamiento.lock() {
        let _ = e.regenerar();
    }
    (ctx.avisar)();
    tracing::info!(dispositivo = id, "teléfono emparejado");
    #[derive(Serialize)]
    struct Emparejado {
        ok: bool,
        device_token: String,
        dispositivo_id: i64,
        nombre: String,
    }
    json(
        StatusCode::OK,
        &Emparejado {
            ok: true,
            device_token: token,
            dispositivo_id: id,
            nombre,
        },
    )
}

/// Los parámetros de la consulta, sin decodificar: solo se esperan enteros.
fn parametro<'a>(consulta: Option<&'a str>, nombre: &str) -> Option<&'a str> {
    consulta?
        .split('&')
        .filter_map(|par| par.split_once('=').or(Some((par, ""))))
        .find(|(k, _)| *k == nombre)
        .map(|(_, v)| v)
}

async fn manifiesto(
    State(ctx): State<Arc<Contexto>>,
    axum::Extension(d): axum::Extension<Dispositivo>,
    peticion: Request,
) -> Response {
    let consulta = peticion.uri().query();
    // `int(x or "0")` con `ValueError` a 0, como la V1.
    let since = parametro(consulta, "since")
        .map_or(Some(0), |s| {
            if s.is_empty() {
                Some(0)
            } else {
                s.trim().parse::<i64>().ok()
            }
        })
        .unwrap_or(0);
    let limite = parametro(consulta, "limit").and_then(|l| {
        if l.is_empty() {
            Some(0)
        } else {
            l.trim().parse::<i64>().ok()
        }
    });
    let db = ctx.db.clone();
    let resultado = bloqueo(move || {
        let conn = db.conexion()?;
        let m = manifiesto::construir(
            &conn,
            since,
            d.seleccion.as_ref(),
            limite,
            repositorio::ahora(),
        )?;
        drop(conn);
        // El avance se guarda solo cuando el teléfono terminó de paginar: un delta a
        // medias no es estar al día.
        if !m.has_more {
            let _ = repositorio::guardar_ultima_sync(&db, d.id, m.sync_version_actual);
        }
        Ok(pyjson::a_bytes(&m))
    })
    .await;
    match resultado {
        Ok(cuerpo) => (
            StatusCode::OK,
            [(
                header::CONTENT_TYPE,
                HeaderValue::from_static("application/json; charset=utf-8"),
            )],
            cuerpo,
        )
            .into_response(),
        Err(_) => fallo_interno(),
    }
}

async fn seleccion(axum::Extension(d): axum::Extension<Dispositivo>) -> Response {
    let actual = d
        .seleccion
        .filter(|s| repositorio::verdad(Some(s)))
        .unwrap_or_else(|| json!({"modo": "todo"}));
    json(StatusCode::OK, &json!({ "seleccion": actual }))
}

async fn fijar_seleccion(
    State(ctx): State<Arc<Contexto>>,
    axum::Extension(d): axum::Extension<Dispositivo>,
    cuerpo: Bytes,
) -> Response {
    let Ok(payload) = serde_json::from_slice::<Value>(&cuerpo) else {
        return error(StatusCode::BAD_REQUEST, "json_invalido");
    };
    // Con o sin el envoltorio `seleccion`.
    let sel = match payload.get("seleccion") {
        Some(s) if payload.is_object() => s.clone(),
        _ => payload,
    };
    if !sel.is_object() {
        return error(StatusCode::BAD_REQUEST, "seleccion_invalida");
    }
    if !["todo", "nada", "artistas", "playlists"].contains(&manifiesto::modo(&sel).as_str()) {
        return error(StatusCode::BAD_REQUEST, "modo_invalido");
    }
    let (db, guardada) = (ctx.db.clone(), sel.clone());
    if bloqueo(move || repositorio::guardar_seleccion(&db, d.id, &guardada))
        .await
        .is_err()
    {
        return error(StatusCode::INTERNAL_SERVER_ERROR, "no_persistida");
    }
    json(StatusCode::OK, &json!({"ok": true, "seleccion": sel}))
}

fn id_de(texto: &str) -> Option<i64> {
    texto.trim().parse().ok()
}

/// El tipo que daría `mimetypes` de Python por la extensión.
fn tipo_de_audio(ruta: &std::path::Path) -> &'static str {
    match ruta
        .extension()
        .and_then(|e| e.to_str())
        .map(str::to_ascii_lowercase)
        .as_deref()
    {
        Some("mp3") => "audio/mpeg",
        Some("flac") => "audio/flac",
        Some("m4a" | "mp4" | "alac") => "audio/mp4",
        Some("aac") => "audio/aac",
        Some("ogg" | "oga") => "audio/ogg",
        Some("opus") => "audio/opus",
        Some("wav") => "audio/x-wav",
        _ => "application/octet-stream",
    }
}

async fn audio(
    State(ctx): State<Arc<Contexto>>,
    Path(id): Path<String>,
    cabeceras: HeaderMap,
) -> Response {
    let Some(id) = id_de(&id).filter(|i| *i != 0) else {
        return error(StatusCode::NOT_FOUND, "no_encontrado");
    };
    let db = ctx.db.clone();
    match bloqueo(move || repositorio::audio(&db, id)).await {
        Ok(Some((ruta, sha))) => {
            let extra = sha.map(|s| ("x-nb-sound-hash", s));
            servir(&ruta, tipo_de_audio(&ruta), extra, &cabeceras).await
        }
        Ok(None) => error(StatusCode::NOT_FOUND, "no_encontrado"),
        Err(_) => fallo_interno(),
    }
}

async fn stems(
    State(ctx): State<Arc<Contexto>>,
    axum::Extension(d): axum::Extension<Dispositivo>,
    Path(id): Path<String>,
    cabeceras: HeaderMap,
) -> Response {
    let Some(id) = id_de(&id).filter(|i| *i != 0) else {
        return error(StatusCode::NOT_FOUND, "sin_stems");
    };
    let (db, rutas) = (ctx.db.clone(), ctx.rutas.clone());
    match bloqueo(move || {
        let ruta = repositorio::instrumental(&db, &rutas, id)?;
        if ruta.is_some() {
            let _ = repositorio::transferencia_iniciada(&db, d.id, id);
        }
        Ok(ruta)
    })
    .await
    {
        Ok(Some(ruta)) => servir(&ruta, tipo_de_audio(&ruta), None, &cabeceras).await,
        Ok(None) => error(StatusCode::NOT_FOUND, "sin_stems"),
        Err(_) => fallo_interno(),
    }
}

async fn letras(State(ctx): State<Arc<Contexto>>, Path(id): Path<String>) -> Response {
    let Some(id) = id_de(&id).filter(|i| *i != 0) else {
        return error(StatusCode::BAD_REQUEST, "id_invalido");
    };
    let db = ctx.db.clone();
    match bloqueo(move || repositorio::letras(&db, id)).await {
        Ok((s, p)) if s.is_empty() && p.is_empty() => error(StatusCode::NOT_FOUND, "sin_lyrics"),
        Ok((s, p)) => {
            #[derive(Serialize)]
            struct Letras {
                synced_lyrics: String,
                plain_lyrics: String,
            }
            json(
                StatusCode::OK,
                &Letras {
                    synced_lyrics: s,
                    plain_lyrics: p,
                },
            )
        }
        Err(_) => fallo_interno(),
    }
}

async fn imagen(
    State(ctx): State<Arc<Contexto>>,
    Path((tipo, id)): Path<(String, String)>,
    cabeceras: HeaderMap,
) -> Response {
    let Some(id) = id_de(&id) else {
        return error(StatusCode::BAD_REQUEST, "id_invalido");
    };
    let (db, rutas) = (ctx.db.clone(), ctx.rutas.clone());
    let encontrada = match tipo.as_str() {
        "cover" | "album" => bloqueo(move || repositorio::imagen(&db, &rutas, false, id)).await,
        "artist" => bloqueo(move || repositorio::imagen(&db, &rutas, true, id)).await,
        "playlist" => {
            bloqueo(move || {
                Ok(mosaico::de_playlist(&db, &rutas, id)?.map(|r| (r, "image/jpeg".to_owned())))
            })
            .await
        }
        _ => Ok(None),
    };
    match encontrada {
        Ok(Some((ruta, mime))) => servir(&ruta, &mime, None, &cabeceras).await,
        Ok(None) => error(StatusCode::NOT_FOUND, "no_encontrado"),
        Err(_) => fallo_interno(),
    }
}

async fn historial(State(ctx): State<Arc<Contexto>>, cuerpo: Bytes) -> Response {
    let Ok(payload) = serde_json::from_slice::<Value>(&cuerpo) else {
        return error(StatusCode::BAD_REQUEST, "json_invalido");
    };
    let db = ctx.db.clone();
    match bloqueo(move || repositorio::aplicar_historial(&db, &payload)).await {
        Ok(r) => {
            #[derive(Serialize)]
            struct Respuesta {
                ok: bool,
                #[serde(flatten)]
                r: repositorio::ResultadoHistorial,
            }
            (ctx.avisar)();
            json(StatusCode::OK, &Respuesta { ok: true, r })
        }
        Err(_) => fallo_interno(),
    }
}

/// Un `Range: bytes=` de un solo tramo, con las reglas de `aiohttp`: `a-b`, `a-`
/// y `-n` (los últimos n bytes). `None` si no hay cabecera; `Err` si no se puede
/// atender.
fn tramo(cabeceras: &HeaderMap, tamano: u64) -> Option<Result<(u64, u64), ()>> {
    let valor = cabeceras.get(header::RANGE)?.to_str().ok()?;
    let Some(espec) = valor.trim().strip_prefix("bytes=") else {
        return Some(Err(()));
    };
    let Some((a, b)) = espec.split_once('-') else {
        return Some(Err(()));
    };
    let numero = |s: &str| -> Result<Option<u64>, ()> {
        if s.is_empty() {
            Ok(None)
        } else if s.bytes().all(|c| c.is_ascii_digit()) {
            s.parse().map(Some).map_err(|_| ())
        } else {
            Err(())
        }
    };
    let (Ok(a), Ok(b)) = (numero(a), numero(b)) else {
        return Some(Err(()));
    };
    let (inicio, fin) = match (a, b) {
        (Some(a), Some(b)) if a > b => return Some(Err(())),
        (Some(a), b) => (
            a,
            b.map_or(tamano.saturating_sub(1), |b| {
                b.min(tamano.saturating_sub(1))
            }),
        ),
        (None, Some(n)) => (tamano.saturating_sub(n), tamano.saturating_sub(1)),
        (None, None) => return Some(Err(())),
    };
    if inicio >= tamano {
        return Some(Err(()));
    }
    Some(Ok((inicio, fin)))
}

/// La fecha de `Last-Modified`, en el formato de HTTP.
fn fecha_http(t: SystemTime) -> String {
    let iso = repositorio::iso(t);
    let dias = t
        .duration_since(SystemTime::UNIX_EPOCH)
        .map(|d| d.as_secs() / 86_400)
        .unwrap_or(0);
    let semana = ["Thu", "Fri", "Sat", "Sun", "Mon", "Tue", "Wed"][(dias % 7) as usize];
    let meses = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ];
    let mes = iso[5..7].parse::<usize>().unwrap_or(1).clamp(1, 12);
    format!(
        "{semana}, {} {} {} {} GMT",
        &iso[8..10],
        meses[mes - 1],
        &iso[0..4],
        &iso[11..19]
    )
}

/// Sirve un archivo como `web.FileResponse` de la V1: entero, o el tramo pedido
/// con 206, y 416 si el tramo no existe. Se envía a trozos, sin cargarlo entero.
pub async fn servir(
    ruta: &PathBuf,
    tipo: &str,
    extra: Option<(&'static str, String)>,
    cabeceras: &HeaderMap,
) -> Response {
    let Ok(meta) = tokio::fs::metadata(ruta).await else {
        return error(StatusCode::NOT_FOUND, "no_encontrado");
    };
    let tamano = meta.len();
    let mut r = Response::builder()
        .header(header::CONTENT_TYPE, tipo)
        .header(header::ACCEPT_RANGES, "bytes");
    if let Ok(t) = meta.modified() {
        r = r.header(header::LAST_MODIFIED, fecha_http(t));
    }
    if let Some((nombre, valor)) = &extra {
        r = r.header(*nombre, valor.as_str());
    }
    let (estado, inicio, largo) = match tramo(cabeceras, tamano) {
        None => (StatusCode::OK, 0, tamano),
        Some(Ok((a, b))) => {
            r = r.header(header::CONTENT_RANGE, format!("bytes {a}-{b}/{tamano}"));
            (StatusCode::PARTIAL_CONTENT, a, b - a + 1)
        }
        Some(Err(())) => {
            return Response::builder()
                .status(StatusCode::RANGE_NOT_SATISFIABLE)
                .header(header::CONTENT_RANGE, format!("bytes */{tamano}"))
                .body(Body::empty())
                .unwrap_or_else(|_| fallo_interno());
        }
    };
    let Ok(mut archivo) = tokio::fs::File::open(ruta).await else {
        return error(StatusCode::NOT_FOUND, "no_encontrado");
    };
    if archivo.seek(SeekFrom::Start(inicio)).await.is_err() {
        return fallo_interno();
    }
    let flujo = futures_util::stream::unfold((archivo, largo), |(mut f, quedan)| async move {
        if quedan == 0 {
            return None;
        }
        let mut buf = vec![0u8; TROZO.min(usize::try_from(quedan).unwrap_or(TROZO))];
        match f.read(&mut buf).await {
            Ok(0) => None,
            Ok(n) => {
                buf.truncate(n);
                Some((
                    Ok::<_, std::io::Error>(Bytes::from(buf)),
                    (f, quedan - n as u64),
                ))
            }
            Err(e) => Some((Err(e), (f, 0))),
        }
    });
    r.status(estado)
        .header(header::CONTENT_LENGTH, largo)
        .body(Body::from_stream(flujo))
        .unwrap_or_else(|_| fallo_interno())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rango(v: &str, tamano: u64) -> Option<Result<(u64, u64), ()>> {
        let mut h = HeaderMap::new();
        h.insert(header::RANGE, HeaderValue::from_str(v).unwrap());
        tramo(&h, tamano)
    }

    #[test]
    fn los_tramos_siguen_las_reglas_de_aiohttp() {
        assert_eq!(tramo(&HeaderMap::new(), 640), None);
        assert_eq!(rango("bytes=0-99", 640), Some(Ok((0, 99))));
        assert_eq!(rango("bytes=600-", 640), Some(Ok((600, 639))));
        assert_eq!(rango("bytes=-40", 640), Some(Ok((600, 639))));
        assert_eq!(rango("bytes=600-9999", 640), Some(Ok((600, 639))));
        assert_eq!(rango("bytes=640-", 640), Some(Err(())));
        assert_eq!(rango("bytes=9-3", 640), Some(Err(())));
        assert_eq!(rango("bytes=0-1,5-6", 640), Some(Err(())));
        assert_eq!(rango("items=0-1", 640), Some(Err(())));
    }

    #[test]
    fn la_fecha_de_http_es_la_del_rfc() {
        let t = SystemTime::UNIX_EPOCH + std::time::Duration::from_secs(784_111_777);
        assert_eq!(fecha_http(t), "Sun, 06 Nov 1994 08:49:37 GMT");
    }

    #[test]
    fn el_token_va_en_bearer_o_en_x_device_token() {
        let mut h = HeaderMap::new();
        h.insert("authorization", HeaderValue::from_static("BEARER  abc "));
        assert_eq!(bearer(&h), "abc");
        let mut h = HeaderMap::new();
        h.insert("x-device-token", HeaderValue::from_static("xyz"));
        assert_eq!(bearer(&h), "xyz");
        assert_eq!(bearer(&HeaderMap::new()), "");
    }

    #[test]
    fn los_parametros_se_leen_como_en_la_v1() {
        assert_eq!(parametro(Some("since=3&limit=500"), "limit"), Some("500"));
        assert_eq!(parametro(Some("since"), "since"), Some(""));
        assert_eq!(parametro(None, "since"), None);
    }
}
