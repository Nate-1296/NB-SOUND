//! El control remoto (F3.2.1): `WS /api/v1/control`.
//!
//! El teléfono recibe el estado del reproductor al conectar y en cada cambio, y la
//! cola cuando cambia o la pide; manda órdenes y recibe un ack por cada una. Es
//! `ModeloSincronizacion` de la V1 (`_construir_snapshot`, `_aplicar_comando`,
//! `_difundir_cola`) sobre el reproductor de la V2.
//!
//! El reproductor publica su [`Instantanea`] en un [`Puente`] aunque el servidor
//! esté apagado; cada conexión la observa y construye sus propios frames, con la
//! base fuera de los hilos del servidor.

use std::collections::HashMap;
use std::sync::{Arc, Mutex, PoisonError};
use std::time::{Duration, Instant};

use axum::extract::ws::{Message, WebSocket, WebSocketUpgrade};
use axum::extract::State;
use axum::response::Response;
use axum::Extension;
use rusqlite::OptionalExtension;
use serde::Serialize;
#[cfg(test)]
use serde_json::json;
use serde_json::Value;
use tokio::sync::{broadcast, watch};

use super::http::bloqueo;
use super::repositorio::{verdad, Dispositivo};
use super::{json as pyjson, Contexto};
use crate::cola::Repeticion;
use crate::db::BaseDeDatos;
use crate::error::{NsError, NsResult};
use crate::reproductor::{Instantanea, Orden};

/// aiohttp mandaba un ping cada 30 s (`heartbeat=30.0`) y cerraba si no llegaba
/// el pong: así se notan los teléfonos que se fueron sin cerrar.
const LATIDO: Duration = Duration::from_secs(30);

/// Mientras suena, la posición cambia sin parar; al teléfono le basta una vez por
/// segundo para su barra. Cualquier otro cambio sale en el acto.
const CADENCIA_POSICION: Duration = Duration::from_secs(1);

type Ordenar = Box<dyn Fn(Orden) + Send + Sync>;

/// Lo que une el reproductor con el servidor móvil.
#[derive(Clone)]
pub struct Puente {
    estado: watch::Sender<Option<Instantanea>>,
    ordenar: Arc<Mutex<Option<Ordenar>>>,
    /// Teléfonos quitados desde Ajustes: su control remoto se cierra al momento.
    expulsados: broadcast::Sender<i64>,
}

impl Default for Puente {
    fn default() -> Self {
        Self {
            estado: watch::channel(None).0,
            ordenar: Arc::new(Mutex::new(None)),
            expulsados: broadcast::channel(16).0,
        }
    }
}

impl Puente {
    /// La llama el oyente del reproductor en cada cambio.
    pub fn publicar(&self, i: &Instantanea) {
        self.estado.send_replace(Some(i.clone()));
    }

    /// Conecta las órdenes al reproductor cuando este arranca.
    pub fn conectar(&self, ordenar: impl Fn(Orden) + Send + Sync + 'static) {
        *self.ordenar.lock().unwrap_or_else(PoisonError::into_inner) = Some(Box::new(ordenar));
    }

    fn ordenar(&self, o: Orden) {
        if let Some(f) = self
            .ordenar
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .as_ref()
        {
            f(o);
        }
    }

    pub fn expulsar(&self, dispositivo: i64) {
        let _ = self.expulsados.send(dispositivo);
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
struct PistaRemota {
    id: i64,
    titulo: String,
    artista: String,
    album: String,
    duracion_seg: f64,
    cover_url: Option<String>,
}

/// El frame `estado`, plano y con los campos de la V1 en su orden.
#[derive(Debug, Clone, PartialEq, Serialize)]
struct Estado {
    tipo: &'static str,
    reproduciendo: bool,
    pista: Option<PistaRemota>,
    posicion_seg: f64,
    volumen: i64,
    modo_repeticion: String,
    aleatorio: bool,
    karaoke_activo: bool,
    karaoke_disponible: bool,
    indice_cola: i64,
    dj_activo: bool,
}

impl Estado {
    fn sin_posicion(&self) -> Self {
        Self {
            posicion_seg: 0.0,
            ..self.clone()
        }
    }
}

#[derive(Debug, Clone, Serialize)]
struct ItemCola {
    id: i64,
    titulo: String,
    artista: String,
    album: String,
    duracion_seg: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
struct Cola {
    tipo: &'static str,
    items: Vec<ItemCola>,
    indice: i64,
}

/// El título, el artista y el álbum de una pista, como los da la cola de la V1.
struct DatosPista {
    titulo: String,
    artista: String,
    album: String,
    album_id: Option<i64>,
}

fn datos_pista(db: &BaseDeDatos, id: i64) -> NsResult<Option<DatosPista>> {
    db.conexion()?
        .query_row(
            "SELECT titulo, artista_nombre, album_titulo, album_id FROM pistas WHERE id = ?1",
            [id],
            |f| {
                Ok(DatosPista {
                    titulo: f.get(0)?,
                    artista: f.get(1)?,
                    album: f.get(2)?,
                    album_id: f.get(3)?,
                })
            },
        )
        .optional()
        .map_err(|_| NsError::StorageFailure)
}

fn estado(db: &BaseDeDatos, i: Option<&Instantanea>) -> NsResult<Estado> {
    let Some(i) = i else {
        // Sin reproductor (no hay salida de audio): lo que la V1 enviaba sin él.
        return Ok(Estado {
            tipo: "estado",
            reproduciendo: false,
            pista: None,
            posicion_seg: 0.0,
            volumen: 100,
            modo_repeticion: "ninguno".to_owned(),
            aleatorio: false,
            karaoke_activo: false,
            karaoke_disponible: false,
            indice_cola: -1,
            dj_activo: false,
        });
    };
    let pista = match i.pista_id {
        Some(id) => datos_pista(db, id)?.map(|d| PistaRemota {
            id,
            titulo: d.titulo,
            artista: d.artista,
            album: d.album,
            duracion_seg: i.duracion_seg,
            cover_url: d.album_id.map(|a| format!("/api/v1/asset/cover/{a}")),
        }),
        None => None,
    };
    Ok(Estado {
        tipo: "estado",
        reproduciendo: i.estado == "reproduciendo",
        pista,
        posicion_seg: i.posicion_seg,
        volumen: (f64::from(i.volumen) * 100.0).round().clamp(0.0, 100.0) as i64,
        modo_repeticion: i.repeticion.clone(),
        aleatorio: i.aleatorio,
        karaoke_activo: i.karaoke_activo,
        karaoke_disponible: i.karaoke_disponible,
        indice_cola: i.indice_cola.map_or(-1, i64::from),
        // El DJ Privado llega en la Fase 6.
        dj_activo: false,
    })
}

fn cola(db: &BaseDeDatos, i: Option<&Instantanea>) -> NsResult<Cola> {
    let Some(i) = i else {
        return Ok(Cola {
            tipo: "cola",
            items: Vec::new(),
            indice: -1,
        });
    };
    let conn = db.conexion()?;
    let mut s = conn
        .prepare(
            "SELECT id, titulo, artista_nombre, album_titulo, duracion_seg FROM pistas
             WHERE id IN (SELECT value FROM json_each(?1))",
        )
        .map_err(|_| NsError::StorageFailure)?;
    let ids = serde_json::to_string(&i.cola).map_err(|_| NsError::Internal)?;
    let por_id: HashMap<i64, ItemCola> = s
        .query_map([ids], |f| {
            Ok(ItemCola {
                id: f.get(0)?,
                titulo: f.get(1)?,
                artista: f.get(2)?,
                album: f.get(3)?,
                duracion_seg: f.get(4)?,
            })
        })
        .map_err(|_| NsError::StorageFailure)?
        .filter_map(Result::ok)
        .map(|it| (it.id, it))
        .collect();
    let items = i
        .cola
        .iter()
        .filter_map(|id| por_id.get(id).cloned())
        .collect();
    // La V1 mandaba -1 cuando el índice era 0 (`int(x or -1)`): aquí va el índice.
    Ok(Cola {
        tipo: "cola",
        items,
        indice: i.indice_cola.map_or(-1, i64::from),
    })
}

fn numero(v: Option<&Value>) -> Option<f64> {
    match v? {
        Value::Number(n) => n.as_f64(),
        Value::String(s) => s.trim().parse().ok(),
        Value::Bool(b) => Some(f64::from(u8::from(*b))),
        _ => None,
    }
}

fn indice(v: Option<&Value>) -> usize {
    numero(v).map_or(0, |n| n.max(0.0) as usize)
}

fn existe(db: &BaseDeDatos, id: i64) -> bool {
    db.conexion()
        .ok()
        .and_then(|c| {
            c.query_row("SELECT 1 FROM pistas WHERE id = ?1", [id], |_| Ok(()))
                .optional()
                .ok()
                .flatten()
        })
        .is_some()
}

/// Lo que hace cada acción, con los alias de la V1. Devuelve `true` si hay que
/// responder con la cola. Una acción desconocida no hace nada, y su ack dice
/// igualmente `encolado`, como en la V1.
fn aplicar(db: &BaseDeDatos, puente: &Puente, m: &Value, actual: Option<&Instantanea>) -> bool {
    let accion = m
        .get("accion")
        .filter(|a| verdad(Some(a)))
        .or_else(|| m.get("comando"))
        .and_then(Value::as_str)
        .unwrap_or_default();
    let posicion = numero(m.get("posicion_seg")).filter(|p| p.is_finite() && *p > 0.0);
    match accion {
        "play_pause" | "play" | "pause" | "toggle" => puente.ordenar(Orden::PausarReanudar),
        "next" | "siguiente" => puente.ordenar(Orden::Siguiente),
        "prev" | "previous" | "anterior" => puente.ordenar(Orden::Anterior),
        // La V2 no tiene "detener" aparte: parar es pausar, y la cola se queda.
        "stop" | "detener" => {
            if actual.is_some_and(|i| i.estado == "reproduciendo") {
                puente.ordenar(Orden::PausarReanudar);
            }
        }
        "seek" => puente.ordenar(Orden::Buscar(
            numero(m.get("posicion_seg")).unwrap_or(0.0).max(0.0),
        )),
        "set_volume" | "volume" | "volumen" => {
            let v = numero(m.get("volumen").or_else(|| m.get("valor"))).unwrap_or(100.0);
            puente.ordenar(Orden::Volumen((v.trunc() / 100.0).clamp(0.0, 1.0) as f32));
        }
        "play_index" | "play_indice" => {
            puente.ordenar(Orden::ReproducirIndice(indice(m.get("indice"))))
        }
        "repeat" | "repeticion" => {
            let modo = match m.get("modo").and_then(Value::as_str).unwrap_or("ninguno") {
                "ninguno" => Some(Repeticion::Ninguno),
                "todo" => Some(Repeticion::Todo),
                "uno" => Some(Repeticion::Uno),
                _ => None,
            };
            if let Some(r) = modo {
                puente.ordenar(Orden::Repeticion(r));
            }
        }
        "shuffle" | "aleatorio" => puente.ordenar(Orden::Aleatorio(verdad(m.get("activo")))),
        "queue" | "cola" => return true,
        "karaoke" | "toggle_karaoke" => {
            puente.ordenar(Orden::Karaoke(!actual.is_some_and(|i| i.karaoke_activo)));
        }
        "set_queue" | "establecer_cola" => {
            let ids: Vec<i64> = m
                .get("ids")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .filter_map(|x| numero(Some(x)).map(|n| n as i64))
                .filter(|id| existe(db, *id))
                .collect();
            if !ids.is_empty() {
                let desde = indice(m.get("indice")).min(ids.len() - 1);
                puente.ordenar(Orden::ReproducirPistas { ids, desde });
                if let Some(p) = posicion {
                    puente.ordenar(Orden::Buscar(p));
                }
            }
        }
        "move_queue" | "mover_cola" => puente.ordenar(Orden::Mover {
            desde: indice(m.get("desde")),
            hasta: indice(m.get("hasta")),
        }),
        "remove_queue" | "quitar_cola" => puente.ordenar(Orden::Quitar(indice(m.get("indice")))),
        "clear_queue" | "vaciar_cola" => puente.ordenar(Orden::Vaciar {
            salvo_la_actual: true,
        }),
        "reproducir_pista" | "play_track" => {
            let id = numero(m.get("pista_id")).map_or(0, |n| n as i64);
            if existe(db, id) {
                puente.ordenar(Orden::ReproducirPista(id));
                if let Some(p) = posicion {
                    puente.ordenar(Orden::Buscar(p));
                }
            }
        }
        "encolar_pista" | "enqueue_track" => {
            let id = numero(m.get("pista_id")).map_or(0, |n| n as i64);
            if existe(db, id) {
                puente.ordenar(Orden::Agregar {
                    ids: vec![id],
                    justo_despues: false,
                });
            }
        }
        _ => {}
    }
    false
}

async fn enviar<T: Serialize>(ws: &mut WebSocket, frame: &T) -> bool {
    let texto = String::from_utf8(pyjson::a_bytes(frame)).unwrap_or_default();
    ws.send(Message::Text(texto.into())).await.is_ok()
}

/// La presencia: cuántos controles tiene abiertos cada teléfono.
struct Presencia {
    ctx: Arc<Contexto>,
    id: i64,
}

impl Presencia {
    fn entrar(ctx: Arc<Contexto>, id: i64) -> Self {
        *ctx.presencia
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .entry(id)
            .or_insert(0) += 1;
        (ctx.avisar)();
        Self { ctx, id }
    }
}

impl Drop for Presencia {
    fn drop(&mut self) {
        let mut p = self
            .ctx
            .presencia
            .lock()
            .unwrap_or_else(PoisonError::into_inner);
        if let Some(n) = p.get_mut(&self.id) {
            *n -= 1;
            if *n == 0 {
                p.remove(&self.id);
            }
        }
        drop(p);
        (self.ctx.avisar)();
    }
}

pub async fn abrir(
    State(ctx): State<Arc<Contexto>>,
    Extension(d): Extension<Dispositivo>,
    ws: WebSocketUpgrade,
) -> Response {
    ws.max_message_size(1 << 20)
        .on_upgrade(move |socket| sesion(socket, ctx, d.id))
}

async fn sesion(mut ws: WebSocket, ctx: Arc<Contexto>, dispositivo: i64) {
    let _presencia = Presencia::entrar(Arc::clone(&ctx), dispositivo);
    let mut cambios = ctx.puente.estado.subscribe();
    let mut expulsados = ctx.puente.expulsados.subscribe();
    let db = ctx.db.clone();

    let actual = cambios.borrow_and_update().clone();
    let (d, a) = (db.clone(), actual.clone());
    let Ok(primero) = bloqueo(move || estado(&d, a.as_ref())).await else {
        return;
    };
    if !enviar(&mut ws, &primero).await {
        return;
    }
    let mut enviado = (primero, Instant::now());
    // La cola no se manda al conectar: el teléfono la pide con `queue`.
    let mut cola_enviada = actual.as_ref().map(|i| (i.cola.clone(), i.indice_cola));

    let mut latido = tokio::time::interval_at(tokio::time::Instant::now() + LATIDO, LATIDO);
    let mut esperando_pong = false;
    loop {
        tokio::select! {
            mensaje = ws.recv() => match mensaje {
                Some(Ok(Message::Text(texto))) => {
                    let actual = cambios.borrow().clone();
                    let (d, p) = (db.clone(), ctx.puente.clone());
                    let Ok(frames) = bloqueo(move || Ok(responder(&d, &p, texto.as_str(), actual.as_ref()))).await else {
                        break;
                    };
                    let mut vivo = true;
                    for f in frames {
                        vivo &= ws.send(Message::Text(f.into())).await.is_ok();
                    }
                    if !vivo {
                        break;
                    }
                }
                Some(Ok(Message::Pong(_))) => esperando_pong = false,
                Some(Ok(Message::Close(_))) | None | Some(Err(_)) => break,
                Some(Ok(_)) => {}
            },
            r = cambios.changed() => {
                if r.is_err() {
                    break;
                }
                let actual = cambios.borrow_and_update().clone();
                let (d, a) = (db.clone(), actual.clone());
                let Ok(nuevo) = bloqueo(move || estado(&d, a.as_ref())).await else {
                    continue;
                };
                let solo_posicion = nuevo.sin_posicion() == enviado.0.sin_posicion();
                if nuevo != enviado.0 && (!solo_posicion || enviado.1.elapsed() >= CADENCIA_POSICION) {
                    if !enviar(&mut ws, &nuevo).await {
                        break;
                    }
                    enviado = (nuevo, Instant::now());
                }
                let de_cola = actual.as_ref().map(|i| (i.cola.clone(), i.indice_cola));
                if de_cola != cola_enviada {
                    let (d, a) = (db.clone(), actual.clone());
                    if let Ok(c) = bloqueo(move || cola(&d, a.as_ref())).await {
                        if !enviar(&mut ws, &c).await {
                            break;
                        }
                    }
                    cola_enviada = de_cola;
                }
            },
            quitado = expulsados.recv() => {
                if matches!(quitado, Ok(id) if id == dispositivo) {
                    let _ = ws.send(Message::Close(None)).await;
                    break;
                }
            },
            _ = latido.tick() => {
                if esperando_pong {
                    break;
                }
                if ws.send(Message::Ping(Vec::new().into())).await.is_err() {
                    break;
                }
                esperando_pong = true;
            },
        }
    }
}

#[derive(Serialize)]
struct Ack {
    tipo: &'static str,
    accion: Value,
    resultado: Resultado,
}

#[derive(Serialize)]
struct Resultado {
    ok: bool,
    encolado: bool,
}

#[derive(Serialize)]
struct ErrorWs {
    tipo: &'static str,
    detalle: &'static str,
}

fn texto<T: Serialize>(v: &T) -> String {
    String::from_utf8(pyjson::a_bytes(v)).unwrap_or_default()
}

/// Los frames que responden a un mensaje del teléfono: el ack y, si pidió la cola,
/// la cola. Un mensaje que no es un objeto JSON solo recibe el error.
fn responder(
    db: &BaseDeDatos,
    puente: &Puente,
    mensaje: &str,
    actual: Option<&Instantanea>,
) -> Vec<String> {
    let Some(m) = serde_json::from_str::<Value>(mensaje)
        .ok()
        .filter(Value::is_object)
    else {
        return vec![texto(&ErrorWs {
            tipo: "error",
            detalle: "json_invalido",
        })];
    };
    let accion = m
        .get("accion")
        .filter(|a| verdad(Some(a)))
        .or_else(|| m.get("comando"))
        .cloned()
        .unwrap_or(Value::Null);
    let con_cola = aplicar(db, puente, &m, actual);
    let mut frames = vec![texto(&Ack {
        tipo: "ack",
        accion,
        resultado: Resultado {
            ok: true,
            encolado: true,
        },
    })];
    if con_cola {
        if let Ok(c) = cola(db, actual) {
            frames.push(texto(&c));
        }
    }
    frames
}

#[cfg(test)]
mod tests {
    use super::*;

    fn instantanea() -> Instantanea {
        Instantanea {
            estado: "reproduciendo".into(),
            pista_id: Some(1),
            posicion_seg: 42.5,
            duracion_seg: 201.5,
            indice_cola: Some(0),
            cola: vec![1, 2],
            aleatorio: false,
            repeticion: "todo".into(),
            volumen: 0.8,
            normalizar: true,
            karaoke_disponible: true,
            karaoke_activo: false,
        }
    }

    fn base() -> BaseDeDatos {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO artistas (id, nombre, clave) VALUES (1, 'a', 'a');
                 INSERT INTO albumes (id, artista_id, titulo, clave) VALUES (10, 1, 'x', 'x');
                 INSERT INTO pistas (id, album_id, titulo, artista_nombre, album_titulo, ruta, duracion_seg)
                 VALUES (1, 10, 'uno', 'a', 'x', 'a', 201.5), (2, NULL, 'dos', 'b', '', 'b', 99);",
            )
            .unwrap();
        db
    }

    fn grabar(puente: &Puente) -> Arc<Mutex<Vec<String>>> {
        let ordenes = Arc::new(Mutex::new(Vec::new()));
        let o = Arc::clone(&ordenes);
        puente.conectar(move |orden| o.lock().unwrap().push(format!("{orden:?}")));
        ordenes
    }

    #[test]
    fn el_estado_tiene_la_forma_de_la_v1() {
        let db = base();
        let e = String::from_utf8(pyjson::a_bytes(&estado(&db, Some(&instantanea())).unwrap()))
            .unwrap();
        assert_eq!(
            e,
            r#"{"tipo": "estado", "reproduciendo": true, "pista": {"id": 1, "titulo": "uno", "artista": "a", "album": "x", "duracion_seg": 201.5, "cover_url": "/api/v1/asset/cover/10"}, "posicion_seg": 42.5, "volumen": 80, "modo_repeticion": "todo", "aleatorio": false, "karaoke_activo": false, "karaoke_disponible": true, "indice_cola": 0, "dj_activo": false}"#
        );
    }

    #[test]
    fn la_cola_va_en_su_orden_con_el_indice_de_verdad() {
        let db = base();
        let mut i = instantanea();
        i.cola = vec![2, 1, 999];
        let c = cola(&db, Some(&i)).unwrap();
        assert_eq!(c.items.iter().map(|x| x.id).collect::<Vec<_>>(), [2, 1]);
        assert_eq!(c.indice, 0);
    }

    #[test]
    fn cada_accion_llega_al_reproductor_como_su_orden() {
        let (db, puente) = (base(), Puente::default());
        let ordenes = grabar(&puente);
        let i = instantanea();
        for m in [
            json!({"tipo": "comando", "accion": "play_pause"}),
            json!({"tipo": "comando", "accion": "seek", "posicion_seg": 90.0}),
            json!({"tipo": "comando", "comando": "set_volume", "volumen": 70}),
            json!({"accion": "repeat", "modo": "una"}),
            json!({"accion": "repeat", "modo": "uno"}),
            json!({"accion": "shuffle", "activo": true}),
            json!({"accion": "karaoke"}),
            json!({"accion": "set_queue", "ids": [2, 999, 1], "indice": 5, "posicion_seg": 12}),
            json!({"accion": "reproducir_pista", "pista_id": 999}),
            json!({"accion": "encolar_pista", "pista_id": 2}),
            json!({"accion": "clear_queue"}),
            json!({"accion": "stop"}),
            json!({"accion": "no_existe"}),
        ] {
            aplicar(&db, &puente, &m, Some(&i));
        }
        assert_eq!(
            *ordenes.lock().unwrap(),
            [
                "PausarReanudar",
                "Buscar(90.0)",
                "Volumen(0.7)",
                "Repeticion(Uno)",
                "Aleatorio(true)",
                "Karaoke(true)",
                "ReproducirPistas { ids: [2, 1], desde: 1 }",
                "Buscar(12.0)",
                "Agregar { ids: [2], justo_despues: false }",
                "Vaciar { salvo_la_actual: true }",
                "PausarReanudar",
            ]
        );
    }

    #[test]
    fn el_json_invalido_da_error_y_lo_demas_un_ack() {
        let (db, puente) = (base(), Puente::default());
        let i = instantanea();
        let f = responder(&db, &puente, "esto no es json", Some(&i));
        assert_eq!(f, [r#"{"tipo": "error", "detalle": "json_invalido"}"#]);
        let f = responder(
            &db,
            &puente,
            r#"{"tipo": "comando", "accion": "no_existe"}"#,
            Some(&i),
        );
        assert_eq!(
            f,
            [
                r#"{"tipo": "ack", "accion": "no_existe", "resultado": {"ok": true, "encolado": true}}"#
            ]
        );
        let f = responder(&db, &puente, r#"{"accion": "queue"}"#, Some(&i));
        assert_eq!(f.len(), 2);
        assert!(f[1].starts_with(r#"{"tipo": "cola", "items": [{"id": 1"#));
    }
}
