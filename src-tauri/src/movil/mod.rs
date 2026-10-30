//! El servidor de NB Sound Mobile (Fase 3, ADR-005).
//!
//! HTTPS y WebSocket con el protocolo `1` de la V1, compatible byte a byte: los
//! teléfonos emparejados con la V1 se reconectan sin volver a escanear el QR,
//! porque la identidad TLS y los `device_token` vinieron con el importador.
//!
//! Corre en su propio hilo con su propio runtime de tokio: un teléfono que
//! descarga la biblioteca no compite con la ventana ni con el audio. Se enciende
//! al abrir la aplicación si el usuario lo dejó así (la V1 lo llamaba
//! `sync_auto_encender`), y siempre que se pide conectar un teléfono.

mod control;
mod emparejamiento;
mod http;
mod json;
mod manifiesto;
mod mosaico;
mod repositorio;
mod tls;

use std::collections::{HashMap, HashSet};
use std::net::{IpAddr, Ipv4Addr, SocketAddr, UdpSocket};
use std::ops::RangeInclusive;
use std::sync::{Arc, Mutex, PoisonError};
use std::thread::JoinHandle;
use std::time::Instant;

use serde::Serialize;
use ts_rs::TS;

pub use control::Puente;
pub use emparejamiento::{huella_token, Qr};
/// El JSON como lo escribía la V1; lo usa el arnés de respuestas doradas.
pub use json::a_bytes as json_como_v1;
pub use repositorio::{aplicar_historial, Telefono, MAX_DISPOSITIVOS};

use crate::db::BaseDeDatos;
use crate::error::{NsError, NsResult};
use crate::paths::Rutas;

/// El nombre que anuncia el servidor: va en `ping`, en el QR y en mDNS.
const NOMBRE: &str = "NB Sound";
const TIPO_MDNS: &str = "_nbsound._tcp.local.";
/// Los puertos de la V1: el primero libre. El teléfono lo aprende del QR o de mDNS.
pub const PUERTOS: RangeInclusive<u16> = 8731..=8799;

/// Lo compartido por todas las peticiones.
pub struct Contexto {
    db: BaseDeDatos,
    rutas: Rutas,
    nombre: String,
    emparejamiento: Mutex<emparejamiento::Emparejamiento>,
    puente: Puente,
    /// Controles remotos abiertos por teléfono.
    presencia: Mutex<HashMap<i64, u32>>,
    /// Cuándo se apuntó por última vez que cada teléfono estaba ahí.
    toques: Mutex<HashMap<i64, Instant>>,
    /// Avisa a la interfaz de que cambió algo que se ve en Ajustes.
    avisar: Arc<dyn Fn() + Send + Sync>,
}

/// Lo que ve Ajustes > Dispositivos del servidor.
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct EstadoMovil {
    pub activo: bool,
    /// `host:puerto`, para quien quiera escribirlo a mano.
    pub direccion: Option<String>,
    /// Encender al abrir la aplicación.
    pub al_arrancar: bool,
}

/// Lo que se muestra para emparejar un teléfono.
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct Emparejar {
    pub qr: Qr,
    /// Para teclearlo en el teléfono si no puede escanear.
    pub codigo: String,
    pub segundos: u32,
}

/// Dónde escuchar. En la aplicación, la interfaz de la LAN y mDNS; en las pruebas,
/// la de bucle y sin anunciarse.
#[derive(Debug, Clone)]
pub struct Opciones {
    pub host: Option<IpAddr>,
    pub mdns: bool,
    pub puertos: RangeInclusive<u16>,
    /// La identidad de la V1. Si el servidor se enciende antes de que el
    /// importador la copie (al pedir un QR durante la primera importación), la
    /// copia él: crear una nueva rompería todos los teléfonos emparejados.
    pub identidad_v1: Option<std::path::PathBuf>,
}

impl Default for Opciones {
    fn default() -> Self {
        Self {
            host: None,
            mdns: true,
            puertos: PUERTOS,
            identidad_v1: None,
        }
    }
}

struct EnMarcha {
    direccion: SocketAddr,
    huella: String,
    parar: Option<tokio::sync::oneshot::Sender<()>>,
    hilo: Option<JoinHandle<()>>,
    mdns: Option<(mdns_sd::ServiceDaemon, String)>,
}

/// El servidor y su ciclo de vida. Encender y apagar son idempotentes.
pub struct ServidorMovil {
    ctx: Arc<Contexto>,
    opciones: Opciones,
    en_marcha: Mutex<Option<EnMarcha>>,
}

/// La IP por la que sale el tráfico a la LAN, que es la que alcanza el teléfono.
/// Conectar un socket UDP no envía nada: solo hace que el sistema elija la
/// interfaz (`ip_lan_probable` de la V1).
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

fn anunciar(direccion: SocketAddr) -> Option<(mdns_sd::ServiceDaemon, String)> {
    let daemon = mdns_sd::ServiceDaemon::new().ok()?;
    let host = format!("nbsound-{}.local.", direccion.port());
    let info = mdns_sd::ServiceInfo::new(
        TIPO_MDNS,
        NOMBRE,
        &host,
        direccion.ip(),
        direccion.port(),
        &[("version", "1"), ("servicio", NOMBRE)][..],
    )
    .ok()?;
    let nombre = info.get_fullname().to_owned();
    if daemon.register(info).is_err() {
        let _ = daemon.shutdown();
        return None;
    }
    Some((daemon, nombre))
}

impl ServidorMovil {
    pub fn nuevo(
        db: BaseDeDatos,
        rutas: Rutas,
        puente: Puente,
        opciones: Opciones,
        avisar: impl Fn() + Send + Sync + 'static,
    ) -> Self {
        Self {
            ctx: Arc::new(Contexto {
                db,
                rutas,
                nombre: NOMBRE.to_owned(),
                emparejamiento: Mutex::new(emparejamiento::Emparejamiento::default()),
                puente,
                presencia: Mutex::new(HashMap::new()),
                toques: Mutex::new(HashMap::new()),
                avisar: Arc::new(avisar),
            }),
            opciones,
            en_marcha: Mutex::new(None),
        }
    }

    /// Enciende el servidor si no lo estaba y espera a que escuche.
    ///
    /// # Errors
    ///
    /// - [`NsError::ComponentUnavailable`] si no hay ningún puerto libre.
    /// - Los de [`tls::cargar`] si la identidad no se puede leer ni crear.
    pub fn encender(&self) -> NsResult<()> {
        let mut en_marcha = self
            .en_marcha
            .lock()
            .unwrap_or_else(PoisonError::into_inner);
        if en_marcha.is_some() {
            return Ok(());
        }
        let dir = self.ctx.rutas.identidad_movil();
        if let Some(v1) = &self.opciones.identidad_v1 {
            crate::identidad_movil::copiar_de_la_v1(v1, &dir)?;
        }
        let (config, huella) = tls::cargar(&dir)?;
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
            .name("servidor-movil".into())
            .spawn(move || {
                let runtime = match tokio::runtime::Builder::new_multi_thread()
                    .worker_threads(2)
                    .thread_name("servidor-movil-red")
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
                    let oyente = match tokio::net::TcpListener::from_std(tcp)
                        .and_then(|t| tls::OyenteTls::nuevo(t, config))
                    {
                        Ok(o) => o,
                        Err(_) => {
                            let _ = listo_tx.send(Err(NsError::Internal));
                            return;
                        }
                    };
                    let _ = listo_tx.send(Ok(()));
                    let servido = axum::serve(oyente, http::rutas(ctx))
                        .with_graceful_shutdown(async {
                            let _ = al_parar.await;
                        })
                        .await;
                    if servido.is_err() {
                        tracing::error!("el servidor móvil terminó con error");
                    }
                });
                // Los controles remotos abiertos no esperan a que el teléfono cierre.
                runtime.shutdown_timeout(std::time::Duration::from_secs(2));
            })
            .map_err(|_| NsError::Internal)?;
        listo_rx.recv().map_err(|_| NsError::Internal)??;
        {
            let mut e = self
                .ctx
                .emparejamiento
                .lock()
                .unwrap_or_else(PoisonError::into_inner);
            e.regenerar()?;
        }
        let mdns = if self.opciones.mdns {
            anunciar(direccion)
        } else {
            None
        };
        if self.opciones.mdns && mdns.is_none() {
            tracing::info!("sin anuncio mDNS: los teléfonos se conectarán por el QR");
        }
        tracing::info!(puerto = direccion.port(), "servidor móvil encendido");
        *en_marcha = Some(EnMarcha {
            direccion,
            huella,
            parar: Some(parar),
            hilo: Some(hilo),
            mdns,
        });
        drop(en_marcha);
        (self.ctx.avisar)();
        Ok(())
    }

    /// Apaga el servidor y espera a que su hilo termine.
    pub fn apagar(&self) {
        let Some(mut e) = self
            .en_marcha
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .take()
        else {
            return;
        };
        if let Some((daemon, nombre)) = e.mdns.take() {
            let _ = daemon.unregister(&nombre);
            let _ = daemon.shutdown();
        }
        if let Some(p) = e.parar.take() {
            let _ = p.send(());
        }
        if let Some(h) = e.hilo.take() {
            let _ = h.join();
        }
        self.ctx
            .emparejamiento
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .olvidar();
        tracing::info!("servidor móvil apagado");
        (self.ctx.avisar)();
    }

    /// La dirección en la que escucha, si está encendido.
    pub fn direccion(&self) -> Option<SocketAddr> {
        self.en_marcha
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .as_ref()
            .map(|e| e.direccion)
    }

    /// # Errors
    ///
    /// [`NsError::StorageFailure`] si no se puede leer la preferencia.
    pub fn estado(&self) -> NsResult<EstadoMovil> {
        Ok(EstadoMovil {
            activo: self.direccion().is_some(),
            direccion: self.direccion().map(|d| d.to_string()),
            al_arrancar: al_arrancar(&self.ctx.db)?,
        })
    }

    /// Un QR y un código nuevos para emparejar; los anteriores dejan de valer.
    /// Enciende el servidor si estaba apagado.
    ///
    /// # Errors
    ///
    /// Los de [`Self::encender`].
    pub fn emparejar(&self) -> NsResult<Emparejar> {
        self.encender()?;
        let (direccion, huella) = {
            let e = self
                .en_marcha
                .lock()
                .unwrap_or_else(PoisonError::into_inner);
            let e = e.as_ref().ok_or(NsError::ComponentUnavailable)?;
            (e.direccion, e.huella.clone())
        };
        let mut emp = self
            .ctx
            .emparejamiento
            .lock()
            .unwrap_or_else(PoisonError::into_inner);
        emp.regenerar()?;
        let (token, codigo, resta) = emp.actual().ok_or(NsError::Internal)?;
        let host = direccion.ip().to_string();
        let contenido = json::a_bytes(&emparejamiento::ContenidoQr {
            host: &host,
            puerto: direccion.port(),
            token,
            version: manifiesto::PROTOCOLO,
            tls: true,
            tls_fingerprint: &huella,
            servicio: NOMBRE,
        });
        Ok(Emparejar {
            qr: emparejamiento::qr(&contenido)?,
            codigo: codigo.to_owned(),
            segundos: resta.as_secs() as u32,
        })
    }

    /// El token del QR vigente. Lo usan las pruebas, que hacen de teléfono.
    pub fn token_vigente(&self) -> Option<String> {
        self.ctx
            .emparejamiento
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .actual()
            .map(|(t, _, _)| t.to_owned())
    }

    /// # Errors
    ///
    /// [`NsError::StorageFailure`] si la consulta falla.
    pub fn telefonos(&self) -> NsResult<Vec<Telefono>> {
        let controlando: HashSet<i64> = self
            .ctx
            .presencia
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .keys()
            .copied()
            .collect();
        repositorio::listar(&self.ctx.db, &controlando)
    }

    /// Quita un teléfono: su token deja de valer y su control remoto se cierra.
    ///
    /// # Errors
    ///
    /// [`NsError::StorageFailure`] si no se puede escribir.
    pub fn quitar(&self, id: i64) -> NsResult<()> {
        repositorio::revocar(&self.ctx.db, id)?;
        self.ctx.puente.expulsar(id);
        tracing::info!(dispositivo = id, "teléfono quitado");
        (self.ctx.avisar)();
        Ok(())
    }
}

impl Drop for ServidorMovil {
    fn drop(&mut self) {
        self.apagar();
    }
}

/// La preferencia de encender el servidor al abrir (la de la V1, importada).
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn al_arrancar(db: &BaseDeDatos) -> NsResult<bool> {
    use rusqlite::OptionalExtension;
    let v: Option<String> = db
        .conexion()?
        .query_row(
            "SELECT valor FROM preferencias WHERE clave = 'servidor_movil_al_arrancar'",
            [],
            |f| f.get(0),
        )
        .optional()
        .map_err(|_| NsError::StorageFailure)?;
    Ok(v.as_deref() == Some("true"))
}
