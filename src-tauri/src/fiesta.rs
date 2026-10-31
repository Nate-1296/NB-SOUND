//! Modo fiesta (F8.5, ADR-012): servidor HTTP efímero y aislado para que los
//! invitados en la misma red local busquen en el catálogo y sugieran canciones
//! escaneando un código QR desde el navegador de su teléfono.
//!
//! Cumple el modelo de confianza de `docs/adr/decisions/ADR-012-modo-fiesta.md`:
//! - Listener `axum` independiente del servidor TLS de NB Sound Mobile, en el
//!   rango `8831..=8899`, activo únicamente mientras dura la sesión de fiesta.
//! - Token de sesión de 128 bits (`22` caracteres base64 URL-safe) en la URL del
//!   QR (`/f/{token}`) validado en tiempo constante, más identificador opaco de
//!   invitado en cookie `HttpOnly; SameSite=Strict`.
//! - Cinco únicas rutas (`GET /f/{token}`, `GET /api/estado`, `GET /api/buscar`,
//!   `POST /api/sugerir`, `GET /api/portada/{id}`): ningún archivo de audio,
//!   ninguna orden de control del reproductor y ninguna escritura en SQLite.
//! - Cuotas en memoria: máximo 3 sugerencias pendientes por invitado o IP,
//!   enfriamiento de 10 s entre envíos, tope global de 50 sugerencias pendientes
//!   y 30 peticiones por minuto por IP.

use std::collections::{HashMap, HashSet};
use std::net::{IpAddr, Ipv4Addr, SocketAddr, UdpSocket};
use std::ops::RangeInclusive;
use std::sync::{Arc, Mutex, PoisonError};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use axum::body::Bytes;
use axum::extract::{ConnectInfo, Path, State};
use axum::http::{header, HeaderMap, HeaderValue, StatusCode, Uri};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::Router;
use serde::{Deserialize, Serialize};
use serde_json::json;
use tokio_rustls::rustls::crypto::ring::default_provider;
use ts_rs::TS;

use crate::biblioteca::{self, ConsultaPistas, OrdenPistas, PistaResumen};
use crate::db::BaseDeDatos;
use crate::error::{NsError, NsResult};
use crate::movil::{self, Qr};
use crate::paths::Rutas;
use crate::portadas::{self, Clase, Peticion};

/// Rango de puertos separado de NB Sound Mobile (`8731..=8799`).
pub const PUERTOS_FIESTA: RangeInclusive<u16> = 8831..=8899;

/// Cuotas de ADR-012.
pub const MAX_PENDIENTES_POR_INVITADO: usize = 3;
pub const MAX_PENDIENTES_GLOBAL: usize = 50;
pub const ENFRIAMIENTO_SUGERENCIA: Duration = Duration::from_secs(10);
pub const MAX_PETICIONES_POR_MINUTO: u32 = 30;
pub const AUTOCIERRE_INACTIVIDAD: Duration = Duration::from_secs(2 * 3600);

/// Una canción sugerida por un invitado durante la fiesta (F8.5).
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct SugerenciaFiesta {
    #[ts(type = "number")]
    pub id: u64,
    pub pista: PistaResumen,
    pub alias: Option<String>,
    pub invitado_id: String,
    pub aceptada: bool,
}

/// Estado del Modo fiesta que ve el anfitrión (F8.5).
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct EstadoFiesta {
    pub activo: bool,
    pub url: Option<String>,
    pub qr: Option<Qr>,
    pub aceptar_automaticamente: bool,
    pub sugerencias: Vec<SugerenciaFiesta>,
    pub bloqueados: u32,
}

#[derive(Debug, Clone)]
pub struct OpcionesFiesta {
    pub host: Option<IpAddr>,
    pub puertos: RangeInclusive<u16>,
    pub enfriamiento: Duration,
}

impl Default for OpcionesFiesta {
    fn default() -> Self {
        Self {
            host: None,
            puertos: PUERTOS_FIESTA,
            enfriamiento: ENFRIAMIENTO_SUGERENCIA,
        }
    }
}

struct EstadoMemoria {
    token_sesion: String,
    aceptar_automaticamente: bool,
    siguiente_id: u64,
    sugerencias: Vec<SugerenciaFiesta>,
    ultimo_envio_invitado: HashMap<String, Instant>,
    ultimo_envio_ip: HashMap<IpAddr, Instant>,
    bloqueados_invitado: HashSet<String>,
    bloqueados_ip: HashSet<IpAddr>,
    invitado_a_ip: HashMap<String, IpAddr>,
    ventana_peticiones: HashMap<IpAddr, (Instant, u32)>,
    ultima_actividad: Instant,
    sonando: Option<PistaResumen>,
}

impl EstadoMemoria {
    fn nuevo(token_sesion: String) -> Self {
        Self {
            token_sesion,
            aceptar_automaticamente: false,
            siguiente_id: 1,
            sugerencias: Vec::new(),
            ultimo_envio_invitado: HashMap::new(),
            ultimo_envio_ip: HashMap::new(),
            bloqueados_invitado: HashSet::new(),
            bloqueados_ip: HashSet::new(),
            invitado_a_ip: HashMap::new(),
            ventana_peticiones: HashMap::new(),
            ultima_actividad: Instant::now(),
            sonando: None,
        }
    }
}

pub(crate) struct ContextoFiesta {
    db: BaseDeDatos,
    rutas: Rutas,
    enfriamiento: Duration,
    memoria: Mutex<EstadoMemoria>,
    al_encolar: Arc<dyn Fn(i64) + Send + Sync>,
    avisar: Arc<dyn Fn() + Send + Sync>,
}

struct EnMarchaFiesta {
    direccion: SocketAddr,
    parar: Option<tokio::sync::oneshot::Sender<()>>,
    hilo: Option<JoinHandle<()>>,
}

/// El servidor efímero del Modo fiesta (F8.5).
pub struct ServidorFiesta {
    ctx: Arc<ContextoFiesta>,
    opciones: OpcionesFiesta,
    en_marcha: Mutex<Option<EnMarchaFiesta>>,
}

fn aleatorio(buf: &mut [u8]) -> NsResult<()> {
    default_provider()
        .secure_random
        .fill(buf)
        .map_err(|_| NsError::Internal)
}

fn base64_url(bytes: &[u8]) -> String {
    const A: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    let mut s = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for trozo in bytes.chunks(3) {
        let n = trozo
            .iter()
            .enumerate()
            .fold(0u32, |n, (i, b)| n | u32::from(*b) << (16 - 8 * i));
        for i in 0..=trozo.len() {
            s.push(A[(n >> (18 - 6 * i) & 63) as usize] as char);
        }
    }
    s
}

/// Token de sesión de 128 bits (22 caracteres base64 URL-safe).
pub fn generar_token_sesion() -> NsResult<String> {
    let mut b = [0u8; 16];
    aleatorio(&mut b)?;
    Ok(base64_url(&b))
}

fn generar_id_invitado() -> NsResult<String> {
    let mut b = [0u8; 8];
    aleatorio(&mut b)?;
    let mut s = String::with_capacity(16);
    for x in b {
        use std::fmt::Write as _;
        let _ = write!(s, "{x:02x}");
    }
    Ok(s)
}

/// Comparación en tiempo constante (ADR-012).
fn iguales_constante(a: &[u8], b: &[u8]) -> bool {
    a.len() == b.len() && a.iter().zip(b).fold(0u8, |d, (x, y)| d | (x ^ y)) == 0
}

fn ip_lan() -> IpAddr {
    let probada = UdpSocket::bind((Ipv4Addr::UNSPECIFIED, 0)).and_then(|s| {
        s.connect((Ipv4Addr::new(10, 255, 255, 255), 1))?;
        s.local_addr()
    });
    match probada {
        Ok(a) if !a.ip().is_loopback() && !a.ip().is_unspecified() => a.ip(),
        _ => IpAddr::V4(Ipv4Addr::LOCALHOST),
    }
}

impl ServidorFiesta {
    pub fn nuevo(
        db: BaseDeDatos,
        rutas: Rutas,
        opciones: OpcionesFiesta,
        al_encolar: impl Fn(i64) + Send + Sync + 'static,
        avisar: impl Fn() + Send + Sync + 'static,
    ) -> Self {
        let token = generar_token_sesion().unwrap_or_else(|_| "sesion-cerrada".to_owned());
        Self {
            ctx: Arc::new(ContextoFiesta {
                db,
                rutas,
                enfriamiento: opciones.enfriamiento,
                memoria: Mutex::new(EstadoMemoria::nuevo(token)),
                al_encolar: Arc::new(al_encolar),
                avisar: Arc::new(avisar),
            }),
            opciones,
            en_marcha: Mutex::new(None),
        }
    }

    /// Enciende el listener efímero de fiesta y genera un token de sesión nuevo.
    ///
    /// # Errors
    ///
    /// Devuelve error si no hay puertos libres o falla el generador aleatorio.
    pub fn encender(&self) -> NsResult<EstadoFiesta> {
        let mut guardia = self
            .en_marcha
            .lock()
            .unwrap_or_else(PoisonError::into_inner);
        if guardia.is_some() {
            drop(guardia);
            return self.estado();
        }
        let nuevo_token = generar_token_sesion()?;
        {
            let mut m = self
                .ctx
                .memoria
                .lock()
                .unwrap_or_else(PoisonError::into_inner);
            let sonando = m.sonando.take();
            *m = EstadoMemoria::nuevo(nuevo_token);
            m.sonando = sonando;
        }

        let host = self.opciones.host.unwrap_or_else(ip_lan);
        let tcp = self
            .opciones
            .puertos
            .clone()
            .find_map(|p| std::net::TcpListener::bind((host, p)).ok())
            .ok_or(NsError::ComponentUnavailable)?;
        tcp.set_nonblocking(true).map_err(|_| NsError::Internal)?;
        let direccion = tcp.local_addr().map_err(|_| NsError::Internal)?;

        let (parar, al_parar) = tokio::sync::oneshot::channel::<()>();
        let (listo_tx, listo_rx) = std::sync::mpsc::channel::<NsResult<()>>();
        let ctx = Arc::clone(&self.ctx);
        let hilo = std::thread::Builder::new()
            .name("servidor-fiesta".into())
            .spawn(move || {
                let runtime = match tokio::runtime::Builder::new_multi_thread()
                    .worker_threads(2)
                    .thread_name("servidor-fiesta-red")
                    .enable_all()
                    .build()
                {
                    Ok(r) => r,
                    Err(_) => {
                        let _ = listo_tx.send(Err(NsError::Internal));
                        return;
                    }
                };
                runtime.block_on(async move {
                    let oyente = match tokio::net::TcpListener::from_std(tcp) {
                        Ok(o) => o,
                        Err(_) => {
                            let _ = listo_tx.send(Err(NsError::Internal));
                            return;
                        }
                    };
                    let _ = listo_tx.send(Ok(()));
                    let app = rutas_http(ctx).into_make_service_with_connect_info::<SocketAddr>();
                    let _ = axum::serve(oyente, app)
                        .with_graceful_shutdown(async {
                            let _ = al_parar.await;
                        })
                        .await;
                });
                runtime.shutdown_timeout(Duration::from_secs(1));
            })
            .map_err(|_| NsError::Internal)?;

        listo_rx.recv().map_err(|_| NsError::Internal)??;
        *guardia = Some(EnMarchaFiesta {
            direccion,
            parar: Some(parar),
            hilo: Some(hilo),
        });
        drop(guardia);
        (self.ctx.avisar)();
        self.estado()
    }

    /// Apaga el listener efímero y borra todas las sugerencias y sesiones en memoria.
    pub fn apagar(&self) -> NsResult<EstadoFiesta> {
        let m = self
            .en_marcha
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .take();
        if let Some(mut activa) = m {
            if let Some(parar) = activa.parar.take() {
                let _ = parar.send(());
            }
            if let Some(hilo) = activa.hilo.take() {
                let _ = hilo.join();
            }
        }
        {
            let mut mem = self
                .ctx
                .memoria
                .lock()
                .unwrap_or_else(PoisonError::into_inner);
            *mem = EstadoMemoria::nuevo("inactivo".to_owned());
        }
        (self.ctx.avisar)();
        self.estado()
    }

    /// Rota el token del QR en el acto, invalidando la URL y las cookies previas.
    ///
    /// # Errors
    ///
    /// Devuelve error si falla el generador aleatorio.
    pub fn regenerar_qr(&self) -> NsResult<EstadoFiesta> {
        let nuevo = generar_token_sesion()?;
        {
            let mut mem = self
                .ctx
                .memoria
                .lock()
                .unwrap_or_else(PoisonError::into_inner);
            mem.token_sesion = nuevo;
            mem.ultima_actividad = Instant::now();
        }
        (self.ctx.avisar)();
        self.estado()
    }

    pub fn fijar_automatico(&self, activo: bool) -> NsResult<EstadoFiesta> {
        let pendientes_a_encolar: Vec<i64> = {
            let mut mem = self
                .ctx
                .memoria
                .lock()
                .unwrap_or_else(PoisonError::into_inner);
            mem.aceptar_automaticamente = activo;
            mem.ultima_actividad = Instant::now();
            if activo {
                let mut ids = Vec::new();
                for s in &mut mem.sugerencias {
                    if !s.aceptada {
                        s.aceptada = true;
                        ids.push(s.pista.id);
                    }
                }
                ids
            } else {
                Vec::new()
            }
        };
        for id in pendientes_a_encolar {
            (self.ctx.al_encolar)(id);
        }
        (self.ctx.avisar)();
        self.estado()
    }

    /// Acepta o descarta una sugerencia pendiente y, opcionalmente, bloquea al invitado/IP.
    pub fn resolver(
        &self,
        sugerencia_id: u64,
        aceptar: bool,
        bloquear_invitado: bool,
    ) -> NsResult<EstadoFiesta> {
        let mut a_encolar: Option<i64> = None;
        {
            let mut mem = self
                .ctx
                .memoria
                .lock()
                .unwrap_or_else(PoisonError::into_inner);
            mem.ultima_actividad = Instant::now();
            if let Some(pos) = mem.sugerencias.iter().position(|s| s.id == sugerencia_id) {
                if aceptar {
                    let s = &mut mem.sugerencias[pos];
                    if !s.aceptada {
                        s.aceptada = true;
                        a_encolar = Some(s.pista.id);
                    }
                } else {
                    let quitada = mem.sugerencias.remove(pos);
                    if bloquear_invitado {
                        if let Some(ip) = mem.invitado_a_ip.get(&quitada.invitado_id).copied() {
                            mem.bloqueados_ip.insert(ip);
                        }
                        mem.bloqueados_invitado.insert(quitada.invitado_id);
                    }
                }
            }
        }
        if let Some(id) = a_encolar {
            (self.ctx.al_encolar)(id);
        }
        (self.ctx.avisar)();
        self.estado()
    }

    /// Actualiza qué pista está sonando para que los invitados la vean en `/api/estado`.
    pub fn actualizar_sonando(&self, pista: Option<PistaResumen>) {
        let mut mem = self
            .ctx
            .memoria
            .lock()
            .unwrap_or_else(PoisonError::into_inner);
        mem.sonando = pista;
    }

    /// Actualiza la pista que suena a partir de su identificador si ha cambiado.
    pub fn actualizar_sonando_id(&self, id: Option<i64>) {
        let actual = self
            .ctx
            .memoria
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .sonando
            .as_ref()
            .map(|p| p.id);
        if actual == id {
            return;
        }
        let resumen = id.and_then(|pid| {
            biblioteca::resumenes(&self.ctx.db, &[pid])
                .ok()
                .and_then(|mut v| v.pop())
        });
        self.actualizar_sonando(resumen);
    }

    pub fn estado(&self) -> NsResult<EstadoFiesta> {
        let direccion = self
            .en_marcha
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .as_ref()
            .map(|e| e.direccion);
        let mem = self
            .ctx
            .memoria
            .lock()
            .unwrap_or_else(PoisonError::into_inner);
        let Some(dir) = direccion else {
            return Ok(EstadoFiesta {
                activo: false,
                url: None,
                qr: None,
                aceptar_automaticamente: false,
                sugerencias: Vec::new(),
                bloqueados: 0,
            });
        };
        let url = format!("http://{}:{}/f/{}", dir.ip(), dir.port(), mem.token_sesion);
        let qr = movil::qr(url.as_bytes())?;
        Ok(EstadoFiesta {
            activo: true,
            url: Some(url),
            qr: Some(qr),
            aceptar_automaticamente: mem.aceptar_automaticamente,
            sugerencias: mem.sugerencias.clone(),
            bloqueados: mem.bloqueados_invitado.len() as u32,
        })
    }
}

// --- Servidor HTTP aislado (ADR-012) --------------------------------------------

pub(crate) fn rutas_http(ctx: Arc<ContextoFiesta>) -> Router {
    Router::new()
        .route("/f/{token}", get(servir_pagina))
        .route("/api/estado", get(http_estado))
        .route("/api/buscar", get(http_buscar))
        .route("/api/sugerir", post(http_sugerir))
        .route("/api/portada/{id}", get(http_portada))
        .with_state(ctx)
}

fn extraer_cookie(headers: &HeaderMap, clave: &str) -> Option<String> {
    let raw = headers.get(header::COOKIE)?.to_str().ok()?;
    for par in raw.split(';') {
        let (k, v) = par.trim().split_once('=')?;
        if k.trim() == clave {
            return Some(v.trim().to_owned());
        }
    }
    None
}

fn verificar_cuota_y_token(
    ctx: &ContextoFiesta,
    ip: IpAddr,
    headers: &HeaderMap,
) -> Result<String, StatusCode> {
    let mut mem = ctx.memoria.lock().unwrap_or_else(PoisonError::into_inner);
    if mem.ultima_actividad.elapsed() > AUTOCIERRE_INACTIVIDAD {
        return Err(StatusCode::UNAUTHORIZED);
    }
    let ahora = Instant::now();
    let entrada = mem.ventana_peticiones.entry(ip).or_insert((ahora, 0));
    if ahora.duration_since(entrada.0) >= Duration::from_secs(60) {
        *entrada = (ahora, 1);
    } else {
        entrada.1 += 1;
        if entrada.1 > MAX_PETICIONES_POR_MINUTO {
            return Err(StatusCode::TOO_MANY_REQUESTS);
        }
    }
    if mem.bloqueados_ip.contains(&ip) {
        return Err(StatusCode::FORBIDDEN);
    }
    let token_recibido = extraer_cookie(headers, "ns_fiesta_tok")
        .or_else(|| {
            headers
                .get("x-fiesta-token")
                .and_then(|v| v.to_str().ok())
                .map(str::to_owned)
        })
        .ok_or(StatusCode::UNAUTHORIZED)?;

    if !iguales_constante(token_recibido.as_bytes(), mem.token_sesion.as_bytes()) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    let invitado = extraer_cookie(headers, "ns_fiesta_inv").unwrap_or_else(|| format!("ip-{ip}"));
    if mem.bloqueados_invitado.contains(&invitado) {
        return Err(StatusCode::FORBIDDEN);
    }
    mem.invitado_a_ip.insert(invitado.clone(), ip);
    mem.ultima_actividad = ahora;
    Ok(invitado)
}

async fn servir_pagina(
    State(ctx): State<Arc<ContextoFiesta>>,
    ConnectInfo(remoto): ConnectInfo<SocketAddr>,
    Path(token): Path<String>,
    headers: HeaderMap,
) -> Response {
    let ip = remoto.ip();
    {
        let mut mem = ctx.memoria.lock().unwrap_or_else(PoisonError::into_inner);
        let ahora = Instant::now();
        let entrada = mem.ventana_peticiones.entry(ip).or_insert((ahora, 0));
        if ahora.duration_since(entrada.0) >= Duration::from_secs(60) {
            *entrada = (ahora, 1);
        } else {
            entrada.1 += 1;
            if entrada.1 > MAX_PETICIONES_POR_MINUTO {
                return StatusCode::TOO_MANY_REQUESTS.into_response();
            }
        }
        if mem.bloqueados_ip.contains(&ip) {
            return StatusCode::FORBIDDEN.into_response();
        }
        if !iguales_constante(token.as_bytes(), mem.token_sesion.as_bytes()) {
            return StatusCode::UNAUTHORIZED.into_response();
        }
        mem.ultima_actividad = ahora;
    }

    let invitado = extraer_cookie(&headers, "ns_fiesta_inv")
        .filter(|id| id.len() == 16 && id.bytes().all(|b| b.is_ascii_hexdigit()))
        .or_else(|| generar_id_invitado().ok())
        .unwrap_or_else(|| "invitado00000000".to_owned());

    let cookie_tok = format!("ns_fiesta_tok={token}; HttpOnly; SameSite=Strict; Path=/");
    let cookie_inv = format!("ns_fiesta_inv={invitado}; HttpOnly; SameSite=Strict; Path=/");

    let mut resp = (
        StatusCode::OK,
        [
            (
                header::CONTENT_TYPE,
                HeaderValue::from_static("text/html; charset=utf-8"),
            ),
            (
                header::CONTENT_SECURITY_POLICY,
                HeaderValue::from_static(
                    "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src 'self' data:",
                ),
            ),
        ],
        PAGINA_INVITADO_HTML,
    )
        .into_response();
    if let Ok(v) = HeaderValue::from_str(&cookie_tok) {
        resp.headers_mut().append(header::SET_COOKIE, v);
    }
    if let Ok(v) = HeaderValue::from_str(&cookie_inv) {
        resp.headers_mut().append(header::SET_COOKIE, v);
    }
    resp
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct SugerenciaPublica {
    id: u64,
    titulo: String,
    artista: String,
    alias: Option<String>,
    aceptada: bool,
}

async fn http_estado(
    State(ctx): State<Arc<ContextoFiesta>>,
    ConnectInfo(remoto): ConnectInfo<SocketAddr>,
    headers: HeaderMap,
) -> Response {
    let invitado = match verificar_cuota_y_token(&ctx, remoto.ip(), &headers) {
        Ok(i) => i,
        Err(code) => return code.into_response(),
    };
    let mem = ctx.memoria.lock().unwrap_or_else(PoisonError::into_inner);
    let mis_pendientes = mem
        .sugerencias
        .iter()
        .filter(|s| !s.aceptada && s.invitado_id == invitado)
        .count();
    let sugerencias: Vec<SugerenciaPublica> = mem
        .sugerencias
        .iter()
        .map(|s| SugerenciaPublica {
            id: s.id,
            titulo: s.pista.titulo.clone(),
            artista: s.pista.artista.clone(),
            alias: s.alias.clone(),
            aceptada: s.aceptada,
        })
        .collect();
    let sonando = mem.sonando.as_ref().map(|p| {
        json!({
            "id": p.id,
            "titulo": p.titulo,
            "artista": p.artista,
            "album": p.album,
            "tienePortada": p.tiene_portada,
        })
    });
    drop(mem);
    (
        StatusCode::OK,
        [(
            header::CONTENT_TYPE,
            HeaderValue::from_static("application/json; charset=utf-8"),
        )],
        serde_json::to_vec(&json!({
            "sonando": sonando,
            "sugerencias": sugerencias,
            "misPendientes": mis_pendientes,
            "maxPendientes": MAX_PENDIENTES_POR_INVITADO,
        }))
        .unwrap_or_default(),
    )
        .into_response()
}

fn decodificar_url(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'+' {
            out.push(b' ');
            i += 1;
        } else if bytes[i] == b'%' && i + 2 < bytes.len() {
            if let Ok(hex) = std::str::from_utf8(&bytes[i + 1..i + 3]) {
                if let Ok(val) = u8::from_str_radix(hex, 16) {
                    out.push(val);
                    i += 3;
                    continue;
                }
            }
            out.push(bytes[i]);
            i += 1;
        } else {
            out.push(bytes[i]);
            i += 1;
        }
    }
    String::from_utf8_lossy(&out).into_owned()
}

fn extraer_param_q(uri: &Uri) -> String {
    let Some(query) = uri.query() else {
        return String::new();
    };
    for par in query.split('&') {
        let (k, v) = par.split_once('=').unwrap_or((par, ""));
        if k == "q" {
            return decodificar_url(v)
                .trim()
                .chars()
                .take(120)
                .collect::<String>();
        }
    }
    String::new()
}

async fn http_buscar(
    State(ctx): State<Arc<ContextoFiesta>>,
    ConnectInfo(remoto): ConnectInfo<SocketAddr>,
    headers: HeaderMap,
    uri: Uri,
) -> Response {
    if let Err(code) = verificar_cuota_y_token(&ctx, remoto.ip(), &headers) {
        return code.into_response();
    }
    let q = extraer_param_q(&uri);
    let db = ctx.db.clone();
    let resultado = tokio::task::spawn_blocking(move || {
        let consulta = ConsultaPistas {
            texto: if q.is_empty() { None } else { Some(q) },
            favoritas: false,
            sin_verificar: false,
            para_cantar: None,
            album_id: None,
            artista_id: None,
            orden: OrdenPistas::MasReproducidas,
        };
        biblioteca::pistas(&db, &consulta, 0, 25)
    })
    .await;

    let Ok(Ok(pagina)) = resultado else {
        return StatusCode::INTERNAL_SERVER_ERROR.into_response();
    };
    let pistas: Vec<_> = pagina
        .pistas
        .into_iter()
        .map(|p| {
            json!({
                "id": p.id,
                "titulo": p.titulo,
                "artista": p.artista,
                "album": p.album,
                "duracionSeg": p.duracion_seg,
                "tienePortada": p.tiene_portada,
            })
        })
        .collect();
    (
        StatusCode::OK,
        [(
            header::CONTENT_TYPE,
            HeaderValue::from_static("application/json; charset=utf-8"),
        )],
        serde_json::to_vec(&json!({ "pistas": pistas })).unwrap_or_default(),
    )
        .into_response()
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct CuerpoSugerir {
    pista_id: i64,
    alias: Option<String>,
}

async fn http_sugerir(
    State(ctx): State<Arc<ContextoFiesta>>,
    ConnectInfo(remoto): ConnectInfo<SocketAddr>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    let ip = remoto.ip();
    let invitado = match verificar_cuota_y_token(&ctx, ip, &headers) {
        Ok(i) => i,
        Err(code) => return code.into_response(),
    };
    if body.len() > 512 {
        return StatusCode::PAYLOAD_TOO_LARGE.into_response();
    }
    let Ok(pedido) = serde_json::from_slice::<CuerpoSugerir>(&body) else {
        return StatusCode::BAD_REQUEST.into_response();
    };
    let alias = pedido
        .alias
        .map(|a| a.trim().chars().take(24).collect::<String>())
        .filter(|a| !a.is_empty());

    // Comprobación previa de cuotas en memoria antes de tocar SQLite.
    {
        let mem = ctx.memoria.lock().unwrap_or_else(PoisonError::into_inner);
        let ahora = Instant::now();
        if let Some(&ult) = mem.ultimo_envio_invitado.get(&invitado) {
            if ahora.duration_since(ult) < ctx.enfriamiento {
                return StatusCode::TOO_MANY_REQUESTS.into_response();
            }
        }
        if let Some(&ult_ip) = mem.ultimo_envio_ip.get(&ip) {
            if ahora.duration_since(ult_ip) < ctx.enfriamiento {
                return StatusCode::TOO_MANY_REQUESTS.into_response();
            }
        }
        let pendientes_inv = mem
            .sugerencias
            .iter()
            .filter(|s| !s.aceptada && s.invitado_id == invitado)
            .count();
        if pendientes_inv >= MAX_PENDIENTES_POR_INVITADO {
            return StatusCode::TOO_MANY_REQUESTS.into_response();
        }
        let pendientes_global = mem.sugerencias.iter().filter(|s| !s.aceptada).count();
        if pendientes_global >= MAX_PENDIENTES_GLOBAL {
            return StatusCode::TOO_MANY_REQUESTS.into_response();
        }
        if mem
            .sugerencias
            .iter()
            .any(|s| !s.aceptada && s.pista.id == pedido.pista_id)
        {
            return (
                StatusCode::OK,
                [(
                    header::CONTENT_TYPE,
                    HeaderValue::from_static("application/json; charset=utf-8"),
                )],
                br#"{"ok":true,"duplicada":true}"#.to_vec(),
            )
                .into_response();
        }
    }

    let db = ctx.db.clone();
    let pista_id = pedido.pista_id;
    let pista = tokio::task::spawn_blocking(move || {
        biblioteca::resumenes(&db, &[pista_id]).map(|mut v| v.pop())
    })
    .await;
    let Ok(Ok(Some(pista_resumen))) = pista else {
        return StatusCode::NOT_FOUND.into_response();
    };

    let auto = {
        let mut mem = ctx.memoria.lock().unwrap_or_else(PoisonError::into_inner);
        let ahora = Instant::now();
        mem.ultimo_envio_invitado.insert(invitado.clone(), ahora);
        mem.ultimo_envio_ip.insert(ip, ahora);
        let id = mem.siguiente_id;
        mem.siguiente_id += 1;
        let auto = mem.aceptar_automaticamente;
        mem.sugerencias.push(SugerenciaFiesta {
            id,
            pista: pista_resumen,
            alias,
            invitado_id: invitado,
            aceptada: auto,
        });
        auto
    };

    if auto {
        (ctx.al_encolar)(pista_id);
    }
    (ctx.avisar)();

    (
        StatusCode::OK,
        [(
            header::CONTENT_TYPE,
            HeaderValue::from_static("application/json; charset=utf-8"),
        )],
        br#"{"ok":true}"#.to_vec(),
    )
        .into_response()
}

async fn http_portada(
    State(ctx): State<Arc<ContextoFiesta>>,
    ConnectInfo(remoto): ConnectInfo<SocketAddr>,
    headers: HeaderMap,
    Path(id): Path<i64>,
) -> Response {
    if let Err(code) = verificar_cuota_y_token(&ctx, remoto.ip(), &headers) {
        return code.into_response();
    }
    let db = ctx.db.clone();
    let rutas = ctx.rutas.clone();
    let res = tokio::task::spawn_blocking(move || {
        portadas::servir(
            &db,
            &rutas,
            Peticion {
                clase: Clase::Pista,
                id,
                tamano: Some(64),
            },
        )
    })
    .await;
    let Ok(Ok((bytes, mime))) = res else {
        return StatusCode::NOT_FOUND.into_response();
    };
    (
        StatusCode::OK,
        [(header::CONTENT_TYPE, HeaderValue::from_static(mime))],
        bytes,
    )
        .into_response()
}

const PAGINA_INVITADO_HTML: &str = r#"<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NB Sound · Modo fiesta</title>
  <style>
    :root { color-scheme: dark; }
    * { box-sizing: border-box; }
    body {
      margin: 0; padding: 16px;
      background: #0d0f14; color: #f3f5f9;
      font-family: system-ui, -apple-system, sans-serif;
      max-width: 540px; margin-inline: auto;
    }
    h1 { font-size: 1.25rem; margin: 0 0 4px; color: #e8a849; }
    p.sub { margin: 0 0 14px; font-size: 0.85rem; color: #9aa3b8; }
    .tarjeta {
      background: #171b26; border: 1px solid #262c3d;
      border-radius: 12px; padding: 12px; margin-bottom: 14px;
    }
    .etiqueta { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; color: #e8a849; font-weight: 700; }
    input {
      width: 100%; padding: 10px 12px; border-radius: 10px;
      border: 1px solid #2c3347; background: #11141d; color: #f3f5f9;
      font-size: 0.95rem; margin-bottom: 8px;
    }
    ul { list-style: none; padding: 0; margin: 0; }
    li {
      display: flex; align-items: center; justify-content: space-between;
      gap: 10px; padding: 8px 0; border-bottom: 1px solid #202534;
    }
    li:last-child { border-bottom: none; }
    .txt { min-width: 0; flex: 1; }
    .txt strong, .txt span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .txt strong { font-size: 0.92rem; }
    .txt span { font-size: 0.78rem; color: #9aa3b8; }
    button {
      border: none; border-radius: 999px; padding: 7px 14px;
      background: #e8a849; color: #16120a; font-weight: 700; cursor: pointer;
    }
    button:disabled { opacity: 0.4; cursor: default; }
    .aviso { font-size: 0.82rem; color: #e8a849; margin-top: 6px; min-height: 1.2em; }
  </style>
</head>
<body>
  <h1>NB Sound · Modo fiesta</h1>
  <p class="sub">Busca en la biblioteca y sugiere qué suena después.</p>
  <div class="tarjeta" id="bloque-sonando">
    <span class="etiqueta">Sonando ahora</span>
    <div id="sonando-texto" style="margin-top:4px;font-weight:600">Cargando…</div>
  </div>
  <div class="tarjeta">
    <input id="alias" maxlength="24" placeholder="Tu nombre (opcional)">
    <input id="buscar" maxlength="100" placeholder="Buscar canción o artista…">
    <div class="aviso" id="aviso"></div>
    <ul id="resultados"></ul>
  </div>
  <div class="tarjeta">
    <span class="etiqueta">Sugerencias de la fiesta</span>
    <ul id="cola" style="margin-top:6px"></ul>
  </div>
  <script>
    const qInput = document.getElementById('buscar');
    const aliasInput = document.getElementById('alias');
    const resUl = document.getElementById('resultados');
    const colaUl = document.getElementById('cola');
    const aviso = document.getElementById('aviso');
    const sonando = document.getElementById('sonando-texto');

    async function cargarEstado() {
      const r = await fetch('/api/estado');
      if (!r.ok) return;
      const d = await r.json();
      sonando.textContent = d.sonando ? (d.sonando.titulo + ' · ' + d.sonando.artista) : 'En pausa';
      colaUl.replaceChildren(...d.sugerencias.map(s => {
        const li = document.createElement('li');
        const div = document.createElement('div');
        div.className = 'txt';
        const st = document.createElement('strong');
        st.textContent = s.titulo;
        const sp = document.createElement('span');
        sp.textContent = s.artista + (s.alias ? ' · por ' + s.alias : '') + (s.aceptada ? ' · En cola' : ' · Pendiente');
        div.append(st, sp);
        li.append(div);
        return li;
      }));
    }

    async function buscar() {
      const q = qInput.value.trim();
      const r = await fetch('/api/buscar?q=' + encodeURIComponent(q));
      if (!r.ok) return;
      const d = await r.json();
      resUl.replaceChildren(...d.pistas.map(p => {
        const li = document.createElement('li');
        const div = document.createElement('div');
        div.className = 'txt';
        const st = document.createElement('strong');
        st.textContent = p.titulo;
        const sp = document.createElement('span');
        sp.textContent = p.artista + ' · ' + p.album;
        div.append(st, sp);
        const btn = document.createElement('button');
        btn.textContent = 'Sugerir';
        btn.onclick = () => sugerir(p.id, btn);
        li.append(div, btn);
        return li;
      }));
    }

    async function sugerir(pistaId, btn) {
      btn.disabled = true;
      aviso.textContent = '';
      const r = await fetch('/api/sugerir', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pistaId, alias: aliasInput.value.trim() || null })
      });
      if (r.status === 429) {
        aviso.textContent = 'Espera unos segundos o a que se acepten tus sugerencias pendientes.';
      } else if (r.ok) {
        aviso.textContent = 'Sugerencia enviada.';
        await cargarEstado();
      }
      setTimeout(() => { btn.disabled = false; }, 2000);
    }

    let timer;
    qInput.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(buscar, 220);
    });
    cargarEstado();
    buscar();
    setInterval(cargarEstado, 5000);
  </script>
</body>
</html>
"#;

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};
    use std::net::TcpStream;

    fn peticion_http(
        addr: SocketAddr,
        metodo: &str,
        ruta: &str,
        headers: &[(&str, &str)],
        cuerpo: &[u8],
    ) -> (u16, String, String) {
        let mut stream = TcpStream::connect(addr).unwrap();
        stream
            .set_read_timeout(Some(Duration::from_secs(3)))
            .unwrap();
        let mut req = format!(
            "{metodo} {ruta} HTTP/1.1\r\nHost: {addr}\r\nConnection: close\r\nContent-Length: {}\r\n",
            cuerpo.len()
        );
        for (k, v) in headers {
            req.push_str(&format!("{k}: {v}\r\n"));
        }
        req.push_str("\r\n");
        stream.write_all(req.as_bytes()).unwrap();
        if !cuerpo.is_empty() {
            stream.write_all(cuerpo).unwrap();
        }
        let mut resp = Vec::new();
        stream.read_to_end(&mut resp).unwrap();
        let texto = String::from_utf8_lossy(&resp).into_owned();
        let (cab, body) = texto.split_once("\r\n\r\n").unwrap_or((&texto, ""));
        let codigo = cab
            .lines()
            .next()
            .and_then(|l| l.split_whitespace().nth(1))
            .and_then(|c| c.parse::<u16>().ok())
            .unwrap_or(0);
        (codigo, cab.to_owned(), body.to_owned())
    }

    #[test]
    fn modo_fiesta_exige_token_aplica_cuotas_y_aprueba_o_bloquea() {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO artistas (id, nombre, clave) VALUES (1, 'Soda Stereo', 'soda');
                 INSERT INTO albumes (id, artista_id, titulo, clave) VALUES (10, 1, 'Canción Animal', 'ca');
                 INSERT INTO pistas (id, album_id, artista_id, titulo, artista_nombre, album_titulo, ruta, duracion_seg)
                 VALUES
                     (1, 10, 1, 'De música ligera', 'Soda Stereo', 'Canción Animal', 'a.mp3', 210.0),
                     (2, 10, 1, 'Té para tres', 'Soda Stereo', 'Canción Animal', 'b.mp3', 180.0),
                     (3, 10, 1, 'Un millón de años luz', 'Soda Stereo', 'Canción Animal', 'c.mp3', 300.0),
                     (4, 10, 1, 'Hombre al agua', 'Soda Stereo', 'Canción Animal', 'd.mp3', 320.0);",
            )
            .unwrap();

        let dir = std::env::temp_dir().join(format!("ns-fiesta-test-{}", std::process::id()));
        let rutas = Rutas::bajo(&dir).unwrap();
        let encoladas: Arc<Mutex<Vec<i64>>> = Arc::new(Mutex::new(Vec::new()));
        let encoladas_clon = Arc::clone(&encoladas);

        let servidor = ServidorFiesta::nuevo(
            db,
            rutas,
            OpcionesFiesta {
                host: Some(IpAddr::V4(Ipv4Addr::LOCALHOST)),
                puertos: 18831..=18899,
                enfriamiento: Duration::from_millis(0),
            },
            move |id| {
                encoladas_clon.lock().unwrap().push(id);
            },
            || {},
        );

        let est = servidor.encender().unwrap();
        assert!(est.activo);
        let url = est.url.unwrap();
        let sin_esquema = url.strip_prefix("http://").unwrap();
        let (host_port, ruta_f) = sin_esquema.split_once('/').unwrap();
        let addr: SocketAddr = host_port.parse().unwrap();
        let token = ruta_f.strip_prefix("f/").unwrap();

        // 1. Sin token: 401 Unauthorized en las rutas de API y en un token falso.
        let (cod, _, _) = peticion_http(addr, "GET", "/api/estado", &[], b"");
        assert_eq!(cod, 401);
        let (cod, _, _) = peticion_http(addr, "GET", "/f/token-falso", &[], b"");
        assert_eq!(cod, 401);

        // 2. Con el token del QR: devuelve la página y emite las cookies HttpOnly.
        let (cod, cab, html) = peticion_http(addr, "GET", &format!("/f/{token}"), &[], b"");
        assert_eq!(cod, 200);
        assert!(html.contains("NB Sound · Modo fiesta"));
        assert!(cab.contains("ns_fiesta_tok="));

        let hdr_token = [("x-fiesta-token", token)];

        // 3. Búsqueda de catálogo y envío de hasta 3 sugerencias pendientes; la 4ª da 429.
        let (cod, _, body) = peticion_http(addr, "GET", "/api/buscar?q=musica", &hdr_token, b"");
        assert_eq!(cod, 200);
        assert!(body.contains("De música ligera"));

        for id in [1, 2, 3] {
            let payload = format!(r#"{{"pistaId":{id},"alias":"Ana"}}"#);
            let (c, _, _) =
                peticion_http(addr, "POST", "/api/sugerir", &hdr_token, payload.as_bytes());
            assert_eq!(c, 200);
        }
        let (c4, _, _) = peticion_http(
            addr,
            "POST",
            "/api/sugerir",
            &hdr_token,
            br#"{"pistaId":4,"alias":"Ana"}"#,
        );
        assert_eq!(c4, 429, "máximo 3 sugerencias pendientes por invitado");

        // 4. El anfitrión acepta la primera sugerencia: se encola en el reproductor.
        let est2 = servidor.resolver(1, true, false).unwrap();
        assert_eq!(encoladas.lock().unwrap().as_slice(), &[1]);
        assert!(est2.sugerencias.iter().any(|s| s.id == 1 && s.aceptada));

        // 5. Regenerar el QR invalida el token anterior en el acto.
        let _ = servidor.regenerar_qr().unwrap();
        let (cod_viejo, _, _) = peticion_http(addr, "GET", "/api/estado", &hdr_token, b"");
        assert_eq!(cod_viejo, 401);

        let est_apagado = servidor.apagar().unwrap();
        assert!(!est_apagado.activo);
        let _ = std::fs::remove_dir_all(&dir);
    }
}
