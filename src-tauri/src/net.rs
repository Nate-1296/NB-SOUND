//! La única puerta de red.
//!
//! Contrato: docs/adr/decisions/ADR-009-configuracion-y-red.md y la regla 5 de la
//! Constitución. Toda petición saliente pasa por [`Red`], declara a qué servicio
//! va, y la puerta comprueba tres cosas antes de salir:
//!
//! 1. que el interruptor general esté encendido;
//! 2. que el usuario haya consentido ese servicio;
//! 3. que el anfitrión de la URL sea uno de los de ese servicio, para que una
//!    URL armada con datos de fuera (una respuesta de MusicBrainz, por ejemplo)
//!    no pueda sacar nada a otro sitio con el permiso de un servicio distinto.
//!
//! `scripts/check-network.mjs` rechaza cualquier uso del cliente HTTP fuera de
//! este archivo, así que esta lista es, literalmente, todo lo que la aplicación
//! puede contactar.

use std::collections::BTreeSet;
use std::io::Read as _;
use std::sync::RwLock;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use ts_rs::TS;

use crate::error::{NsError, NsResult};

/// Un servicio externo. El orden es el de Ajustes > Privacidad.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub enum Servicio {
    AcoustId,
    MusicBrainz,
    CoverArtArchive,
    Shazam,
    Itunes,
    Lrclib,
    LyricsOvh,
    Deezer,
    Wikipedia,
    TheAudioDb,
    ProveedorIa,
    Agregados,
    Actualizaciones,
}

impl Servicio {
    pub const TODOS: [Servicio; 13] = [
        Servicio::AcoustId,
        Servicio::MusicBrainz,
        Servicio::CoverArtArchive,
        Servicio::Shazam,
        Servicio::Itunes,
        Servicio::Lrclib,
        Servicio::LyricsOvh,
        Servicio::Deezer,
        Servicio::Wikipedia,
        Servicio::TheAudioDb,
        Servicio::ProveedorIa,
        Servicio::Agregados,
        Servicio::Actualizaciones,
    ];

    /// Los anfitriones a los que puede ir cada servicio. Un subdominio cuenta
    /// solo si se declara con el punto delante (`.wikipedia.org`).
    fn anfitriones(self) -> &'static [&'static str] {
        match self {
            Self::AcoustId => &["api.acoustid.org"],
            Self::MusicBrainz => &["musicbrainz.org"],
            Self::CoverArtArchive => &["coverartarchive.org", ".archive.org"],
            Self::Shazam => &["amp.shazam.com"],
            Self::Itunes => &["itunes.apple.com", ".mzstatic.com"],
            Self::Lrclib => &["lrclib.net"],
            Self::LyricsOvh => &["api.lyrics.ovh"],
            Self::Deezer => &["api.deezer.com", ".dzcdn.net"],
            Self::Wikipedia => &[".wikipedia.org", ".wikimedia.org"],
            Self::TheAudioDb => &["www.theaudiodb.com", "r2.theaudiodb.com"],
            Self::ProveedorIa => &["api.anthropic.com", "api.openai.com"],
            // El repositorio público de distribución se decide en F0.1.5.
            Self::Agregados => &["github.com", ".githubusercontent.com", "huggingface.co"],
            // El manifiesto `latest.json` y los instaladores de las publicaciones; GitHub
            // redirige las descargas a `objects.githubusercontent.com`.
            Self::Actualizaciones => &["github.com", ".githubusercontent.com"],
        }
    }

    fn admite(self, anfitrion: &str) -> bool {
        let anfitrion = anfitrion.to_ascii_lowercase();
        self.anfitriones()
            .iter()
            .any(|permitido| match permitido.strip_prefix('.') {
                Some(dominio) => anfitrion == dominio || anfitrion.ends_with(permitido),
                None => anfitrion == *permitido,
            })
    }
}

/// Lo que el usuario consintió. De fábrica **no sale nada**: el primer
/// arranque pregunta, y Ajustes lo cambia servicio a servicio.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct PoliticaDeRed {
    pub general: bool,
    pub servicios: BTreeSet<Servicio>,
}

impl PoliticaDeRed {
    fn comprobar(&self, servicio: Servicio) -> NsResult<()> {
        if !self.general {
            return Err(NsError::NetworkDisabled);
        }
        if !self.servicios.contains(&servicio) {
            return Err(NsError::ConsentRequired);
        }
        Ok(())
    }
}

/// Tope de una respuesta que se lee entera en memoria. Las descargas grandes
/// (agregados, audio) no pasan por aquí sino por una escritura a disco.
const TOPE_EN_MEMORIA: u64 = 16 * 1024 * 1024;

/// La puerta.
pub struct Red {
    politica: RwLock<PoliticaDeRed>,
    agente: ureq::Agent,
}

impl Red {
    pub fn new(politica: PoliticaDeRed) -> Self {
        let agente = ureq::Agent::config_builder()
            .timeout_global(Some(Duration::from_secs(30)))
            .user_agent(concat!(
                "NBSound/",
                env!("CARGO_PKG_VERSION"),
                " ( https://github.com/Nate-1296/NB-SOUND )"
            ))
            .http_status_as_error(false)
            .build()
            .into();
        Self {
            politica: RwLock::new(politica),
            agente,
        }
    }

    pub fn politica(&self) -> PoliticaDeRed {
        self.politica.read().map(|p| p.clone()).unwrap_or_default()
    }

    pub fn cambiar_politica(&self, nueva: PoliticaDeRed) {
        if let Ok(mut actual) = self.politica.write() {
            *actual = nueva;
        }
    }

    /// Comprueba si la petición podría salir, sin hacerla.
    ///
    /// # Errors
    ///
    /// [`NsError::NetworkDisabled`], [`NsError::ConsentRequired`] o
    /// [`NsError::PathNotAllowed`] si el anfitrión no es de ese servicio.
    pub fn autorizar(&self, servicio: Servicio, url: &str) -> NsResult<()> {
        self.politica().comprobar(servicio)?;
        let anfitrion = anfitrion_de(url).ok_or(NsError::PathNotAllowed)?;
        if !servicio.admite(anfitrion) {
            tracing::warn!(
                ?servicio,
                "se rechazó una URL fuera de los anfitriones del servicio"
            );
            return Err(NsError::PathNotAllowed);
        }
        Ok(())
    }

    /// `GET` que devuelve el cuerpo entero.
    ///
    /// # Errors
    ///
    /// Los de [`Red::autorizar`], y [`NsError::NetworkFailure`] si la petición
    /// falla, devuelve un estado que no es 2xx o pasa del tope en memoria.
    pub fn obtener(
        &self,
        servicio: Servicio,
        url: &str,
        cabeceras: &[(&str, &str)],
    ) -> NsResult<Vec<u8>> {
        let (estado, cuerpo) = self.obtener_con_estado(servicio, url, cabeceras)?;
        if !(200..300).contains(&estado) {
            tracing::debug!(?servicio, estado, "respuesta no 2xx");
            return Err(NsError::NetworkFailure);
        }
        Ok(cuerpo)
    }

    /// `GET` que devuelve también el estado, para los servicios en los que un 404
    /// es una respuesta ("no existe") y no un fallo (MusicBrainz).
    ///
    /// # Errors
    ///
    /// Los de [`Red::autorizar`], y [`NsError::NetworkFailure`] si la petición no
    /// se completa o pasa del tope en memoria.
    pub fn obtener_con_estado(
        &self,
        servicio: Servicio,
        url: &str,
        cabeceras: &[(&str, &str)],
    ) -> NsResult<(u16, Vec<u8>)> {
        self.autorizar(servicio, url)?;
        let mut peticion = self.agente.get(url);
        for (nombre, valor) in cabeceras {
            peticion = peticion.header(*nombre, *valor);
        }
        let respuesta = peticion.call().map_err(|e| {
            tracing::debug!(?servicio, error = %e, "la petición no se completó");
            NsError::NetworkFailure
        })?;
        let estado = respuesta.status().as_u16();
        let mut cuerpo = Vec::new();
        respuesta
            .into_body()
            .into_reader()
            .take(TOPE_EN_MEMORIA + 1)
            .read_to_end(&mut cuerpo)
            .map_err(|_| NsError::NetworkFailure)?;
        if cuerpo.len() as u64 > TOPE_EN_MEMORIA {
            return Err(NsError::NetworkFailure);
        }
        Ok((estado, cuerpo))
    }
}

impl Red {
    /// `POST` con un cuerpo JSON; devuelve el estado y el cuerpo (Shazam).
    ///
    /// # Errors
    ///
    /// Los de [`Red::autorizar`], y [`NsError::NetworkFailure`] si la petición no
    /// se completa o pasa del tope en memoria.
    pub fn enviar_json(
        &self,
        servicio: Servicio,
        url: &str,
        cabeceras: &[(&str, &str)],
        cuerpo: &[u8],
    ) -> NsResult<(u16, Vec<u8>)> {
        self.autorizar(servicio, url)?;
        let mut peticion = self
            .agente
            .post(url)
            .header("Content-Type", "application/json");
        for (nombre, valor) in cabeceras {
            peticion = peticion.header(*nombre, *valor);
        }
        let respuesta = peticion.send(cuerpo).map_err(|e| {
            tracing::debug!(?servicio, error = %e, "la petición no se completó");
            NsError::NetworkFailure
        })?;
        let estado = respuesta.status().as_u16();
        let mut leido = Vec::new();
        respuesta
            .into_body()
            .into_reader()
            .take(TOPE_EN_MEMORIA + 1)
            .read_to_end(&mut leido)
            .map_err(|_| NsError::NetworkFailure)?;
        if leido.len() as u64 > TOPE_EN_MEMORIA {
            return Err(NsError::NetworkFailure);
        }
        Ok((estado, leido))
    }
}

/// Adónde va una descarga. Antes del primer byte se le dice si el servidor
/// continúa lo que ya había (206) o lo manda entero desde el principio (200,
/// porque ignoró el `Range`), para que vacíe lo anterior en ese caso.
pub trait Destino {
    /// # Errors
    ///
    /// Los de entrada y salida del destino.
    fn empezar(&mut self, continuada: bool) -> std::io::Result<()>;
    /// # Errors
    ///
    /// Los de entrada y salida del destino.
    fn escribir(&mut self, bloque: &[u8]) -> std::io::Result<()>;
}

impl Red {
    /// `GET` que escribe el cuerpo en `destino` por bloques, sin pasar por
    /// memoria (los agregados pesan cientos de MB). Con `desde > 0` pide el resto
    /// con `Range` para reanudar. `progreso` recibe lo escrito en esta llamada.
    ///
    /// # Errors
    ///
    /// Los de [`Red::autorizar`], y [`NsError::NetworkFailure`] si la petición no
    /// se completa, el estado no es 200 ni 206, o se corta a mitad.
    pub fn descargar(
        &self,
        servicio: Servicio,
        url: &str,
        desde: u64,
        destino: &mut dyn Destino,
        progreso: &mut dyn FnMut(u64),
    ) -> NsResult<()> {
        self.autorizar(servicio, url)?;
        // Sin el tope global de 30 s del agente: un agregado tarda minutos. La
        // respuesta sí tiene que empezar a llegar a tiempo.
        let mut peticion = self
            .agente
            .get(url)
            .config()
            .timeout_global(None)
            .timeout_recv_response(Some(Duration::from_secs(30)))
            .build();
        if desde > 0 {
            peticion = peticion.header("Range", format!("bytes={desde}-"));
        }
        let respuesta = peticion.call().map_err(|e| {
            tracing::debug!(?servicio, error = %e, "la descarga no se completó");
            NsError::NetworkFailure
        })?;
        let estado = respuesta.status().as_u16();
        if estado != 200 && estado != 206 {
            tracing::debug!(?servicio, estado, "la descarga no empezó");
            return Err(NsError::NetworkFailure);
        }
        destino
            .empezar(estado == 206)
            .map_err(|_| NsError::StorageFailure)?;
        let mut lector = respuesta.into_body().into_reader();
        let mut buf = vec![0u8; 256 * 1024];
        let mut bytes = 0u64;
        loop {
            let n = lector.read(&mut buf).map_err(|_| NsError::NetworkFailure)?;
            if n == 0 {
                break;
            }
            destino
                .escribir(&buf[..n])
                .map_err(|_| NsError::StorageFailure)?;
            bytes += n as u64;
            progreso(bytes);
        }
        Ok(())
    }
}

// --- Actualizaciones de la aplicación (F7.2.2) -----------------------------------

/// El manifiesto de la última publicación, el mismo que fija `tauri.conf.json`.
/// Se repite aquí para comprobarlo en la puerta antes de que el plugin salga.
const MANIFIESTO: &str =
    "https://github.com/Nate-1296/NB-SOUND/releases/latest/download/latest.json";

/// El plugin de actualizaciones. Lleva su propio cliente HTTP, así que no se usa
/// fuera de este archivo: cada consulta y cada descarga pasa antes por
/// [`Red::autorizar`], como lo demás. Las redirecciones de GitHub las sigue el
/// plugin; lo que llega se comprueba con la firma de la publicación.
pub fn plugin_de_actualizaciones<R: tauri::Runtime>(
) -> tauri::plugin::TauriPlugin<R, tauri_plugin_updater::Config> {
    tauri_plugin_updater::Builder::new().build()
}

/// Una versión publicada más nueva que la instalada.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct Actualizacion {
    pub version: String,
    /// Las notas de la publicación, tal como se escribieron en GitHub.
    pub notas: Option<String>,
}

async fn consultar<R: tauri::Runtime>(
    app: &tauri::AppHandle<R>,
    red: &Red,
) -> NsResult<Option<tauri_plugin_updater::Update>> {
    use tauri_plugin_updater::UpdaterExt as _;
    red.autorizar(Servicio::Actualizaciones, MANIFIESTO)?;
    let manifiesto = MANIFIESTO.parse().map_err(|_| NsError::Internal)?;
    let actualizador = app
        .updater_builder()
        .endpoints(vec![manifiesto])
        .and_then(tauri_plugin_updater::UpdaterBuilder::build)
        .map_err(|_| {
            tracing::warn!("el actualizador no está disponible");
            NsError::ComponentUnavailable
        })?;
    // Los errores del plugin no se registran: pueden llevar la ruta del ejecutable.
    let nueva = actualizador.check().await.map_err(|e| {
        tracing::debug!("no se pudo consultar la última publicación");
        match e {
            // Un paquete del sistema (deb o rpm sin permisos, o un formato que el
            // plugin no sabe instalar) se actualiza con su gestor de paquetes.
            tauri_plugin_updater::Error::UnsupportedOs => NsError::ComponentUnavailable,
            _ => NsError::NetworkFailure,
        }
    })?;
    if let Some(n) = &nueva {
        red.autorizar(Servicio::Actualizaciones, n.download_url.as_str())?;
    }
    Ok(nueva)
}

/// Mira si hay una versión más nueva publicada.
///
/// # Errors
///
/// Los de [`Red::autorizar`]; [`NsError::NetworkFailure`] si la consulta falla y
/// [`NsError::ComponentUnavailable`] si esta instalación no se actualiza sola.
pub async fn buscar_actualizacion<R: tauri::Runtime>(
    app: &tauri::AppHandle<R>,
    red: &Red,
) -> NsResult<Option<Actualizacion>> {
    Ok(consultar(app, red).await?.map(|n| Actualizacion {
        version: n.version,
        notas: n.body,
    }))
}

/// Un destino de descarga en memoria, para lo que se verifica entero antes de
/// usarse (la actualización de un paquete del sistema).
#[cfg(target_os = "linux")]
#[derive(Default)]
struct EnMemoria(Vec<u8>);

#[cfg(target_os = "linux")]
impl Destino for EnMemoria {
    fn empezar(&mut self, continuada: bool) -> std::io::Result<()> {
        if !continuada {
            self.0.clear();
        }
        Ok(())
    }

    fn escribir(&mut self, bloque: &[u8]) -> std::io::Result<()> {
        self.0.extend_from_slice(bloque);
        Ok(())
    }
}

/// El texto de minisign que Tauri guarda otra vez en base64 (clave o firma).
#[cfg(target_os = "linux")]
fn texto_de_tauri(b64: &[u8]) -> Option<String> {
    let b = crate::identidad_movil::base64(std::str::from_utf8(b64).ok()?)?;
    String::from_utf8(b).ok()
}

/// La clave pública de `tauri.conf.json`, como la escribe `tauri signer`.
#[cfg(target_os = "linux")]
fn clave_de_tauri(b64: &str) -> Option<minisign_verify::PublicKey> {
    minisign_verify::PublicKey::decode(&texto_de_tauri(b64.as_bytes())?).ok()
}

/// Comprueba `contenido` con una firma de `tauri signer`. Las dos llegan como las
/// escribe Tauri: el texto de minisign (clave o firma) codificado otra vez en
/// base64. Es la misma comprobación que hace el plugin con lo que instala él.
///
/// # Errors
///
/// [`NsError::IntegrityMismatch`] si la clave o la firma no se entienden o no
/// corresponden al contenido.
#[cfg(target_os = "linux")]
fn verificar_firma(clave_publica: &str, firma: &[u8], contenido: &[u8]) -> NsResult<()> {
    let clave = clave_de_tauri(clave_publica).ok_or(NsError::IntegrityMismatch)?;
    let firma = texto_de_tauri(firma)
        .and_then(|t| minisign_verify::Signature::decode(&t).ok())
        .ok_or(NsError::IntegrityMismatch)?;
    clave
        .verify(contenido, &firma, false)
        .map_err(|_| NsError::IntegrityMismatch)
}

/// El archivo `.tar.gz` de la misma publicación que `descarga` (la URL del
/// paquete que eligió el plugin): se cambia solo el último tramo, para no repetir
/// aquí el repositorio.
#[cfg(target_os = "linux")]
fn url_hermana(descarga: &str, version: &str) -> Option<String> {
    let (base, _) = descarga.rsplit_once('/')?;
    Some(format!("{base}/NB.Sound_{version}_amd64.tar.gz"))
}

/// Si esta instalación es un paquete del sistema que su gestor no puede
/// actualizar: el `.tar.gz` de Linux se hace con el contenido del `.deb` (y el
/// binario dice ser un `.deb`), pero se instala en distribuciones sin `dpkg`,
/// como Arch. Ahí el plugin descargaría el `.deb` para fallar al instalarlo.
#[cfg(target_os = "linux")]
fn paquete_sin_gestor() -> bool {
    use tauri::utils::config::BundleType;
    let gestor = match tauri::utils::platform::bundle_type() {
        Some(BundleType::Deb) => "dpkg",
        Some(BundleType::Rpm) => "rpm",
        _ => return false,
    };
    let en_path = std::env::var_os("PATH")
        .is_some_and(|path| std::env::split_paths(&path).any(|d| d.join(gestor).is_file()));
    !en_path
}

/// Instala el `.tar.gz` firmado de la publicación sobre `/usr`. Se verifica en
/// memoria y se le pasa a `tar` por la entrada estándar: entre comprobar la firma
/// y extraer no hay ningún archivo que otro proceso pueda cambiar. Pide permisos
/// con `sudo -n` (sin contraseña, si el usuario lo configuró) o, si no, con
/// `pkexec`, que pregunta en una ventana del sistema.
#[cfg(target_os = "linux")]
fn instalar_tar(red: &Red, clave_publica: &str, descarga: &str, version: &str) -> NsResult<()> {
    use std::io::Write as _;
    use std::process::{Command, Stdio};

    let url = url_hermana(descarga, version).ok_or(NsError::Internal)?;
    let firma = red.obtener(Servicio::Actualizaciones, &format!("{url}.sig"), &[])?;
    let mut paquete = EnMemoria::default();
    red.descargar(
        Servicio::Actualizaciones,
        &url,
        0,
        &mut paquete,
        &mut |_| {},
    )?;
    verificar_firma(clave_publica, &firma, &paquete.0)?;

    // Solo lo que cuelga de `usr/`, y sin cambiar los permisos de las carpetas
    // que ya existen.
    let argumentos = ["tar", "--no-overwrite-dir", "-xzf", "-", "-C", "/", "usr"];
    let extraer = |programa: &str, previos: &[&str]| -> bool {
        let Ok(mut hijo) = Command::new(programa)
            .args(previos)
            .args(argumentos)
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
        else {
            return false;
        };
        let escrito = hijo
            .stdin
            .take()
            .is_some_and(|mut entrada| entrada.write_all(&paquete.0).is_ok());
        hijo.wait().is_ok_and(|s| s.success()) && escrito
    };
    if extraer("sudo", &["-n"]) || extraer("pkexec", &[]) {
        Ok(())
    } else {
        tracing::warn!("no se pudo instalar el paquete del sistema");
        Err(NsError::ComponentUnavailable)
    }
}

/// Descarga la versión más nueva, comprueba su firma y la instala. Quien llama
/// reinicia la aplicación. Devuelve `false` si ya no había nada que instalar.
///
/// # Errors
///
/// Los de [`buscar_actualizacion`], e [`NsError::IntegrityMismatch`] si la firma
/// no es la de NB Sound.
pub async fn instalar_actualizacion<R: tauri::Runtime>(
    app: &tauri::AppHandle<R>,
    red: &std::sync::Arc<Red>,
) -> NsResult<bool> {
    let Some(nueva) = consultar(app, red).await? else {
        return Ok(false);
    };

    #[cfg(target_os = "linux")]
    if paquete_sin_gestor() {
        let clave = app
            .config()
            .plugins
            .0
            .get("updater")
            .and_then(|u| u.get("pubkey"))
            .and_then(serde_json::Value::as_str)
            .ok_or(NsError::Internal)?
            .to_owned();
        let red = std::sync::Arc::clone(red);
        let descarga = nueva.download_url.to_string();
        let version = nueva.version.clone();
        tauri::async_runtime::spawn_blocking(move || {
            instalar_tar(&red, &clave, &descarga, &version)
        })
        .await
        .map_err(|_| NsError::Internal)??;
        return Ok(true);
    }

    nueva
        .download_and_install(|_, _| {}, || {})
        .await
        .map_err(|e| {
            tracing::warn!("no se pudo instalar la actualización");
            match e {
                tauri_plugin_updater::Error::Minisign(_)
                | tauri_plugin_updater::Error::SignatureUtf8(_)
                | tauri_plugin_updater::Error::SignedVersionMismatch { .. }
                | tauri_plugin_updater::Error::MissingSignedVersion => NsError::IntegrityMismatch,
                // Sin permisos para escribir donde está instalada.
                tauri_plugin_updater::Error::Io(_) => NsError::ComponentUnavailable,
                _ => NsError::NetworkFailure,
            }
        })?;
    Ok(true)
}

/// El anfitrión de una URL `https://`. Las demás no se admiten: nada sale en
/// claro.
fn anfitrion_de(url: &str) -> Option<&str> {
    let resto = url.strip_prefix("https://")?;
    let fin = resto.find(['/', '?', '#']).unwrap_or(resto.len());
    let autoridad = &resto[..fin];
    if autoridad.contains('@') {
        return None;
    }
    let anfitrion = autoridad.split(':').next()?;
    (!anfitrion.is_empty()).then_some(anfitrion)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(target_os = "linux")]
    #[test]
    fn la_clave_de_tauri_conf_se_entiende_y_rechaza_una_firma_ajena() {
        let conf: serde_json::Value =
            serde_json::from_str(include_str!("../tauri.conf.json")).unwrap();
        let clave = conf["plugins"]["updater"]["pubkey"].as_str().unwrap();
        assert!(clave_de_tauri(clave).is_some());
        assert_eq!(
            verificar_firma(clave, b"no es una firma", b"contenido"),
            Err(NsError::IntegrityMismatch)
        );
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn el_tar_se_busca_en_la_misma_publicacion_que_el_paquete() {
        assert_eq!(
            url_hermana(
                "https://github.com/x/y/releases/download/v2.1.0/NB.Sound_2.1.0_amd64.deb",
                "2.1.0"
            )
            .as_deref(),
            Some("https://github.com/x/y/releases/download/v2.1.0/NB.Sound_2.1.0_amd64.tar.gz")
        );
    }

    fn con(servicios: &[Servicio]) -> Red {
        Red::new(PoliticaDeRed {
            general: true,
            servicios: servicios.iter().copied().collect(),
        })
    }

    #[test]
    fn de_fabrica_no_sale_nada() {
        let red = Red::new(PoliticaDeRed::default());
        assert_eq!(
            red.autorizar(
                Servicio::MusicBrainz,
                "https://musicbrainz.org/ws/2/recording"
            ),
            Err(NsError::NetworkDisabled)
        );
    }

    #[test]
    fn con_la_red_encendida_cada_servicio_pide_su_consentimiento() {
        let red = con(&[Servicio::Lrclib]);
        assert_eq!(
            red.autorizar(Servicio::MusicBrainz, "https://musicbrainz.org/ws/2/x"),
            Err(NsError::ConsentRequired)
        );
        assert_eq!(
            red.autorizar(Servicio::Lrclib, "https://lrclib.net/api/get"),
            Ok(())
        );
    }

    #[test]
    fn el_interruptor_general_manda_sobre_los_consentimientos() {
        let red = con(&Servicio::TODOS);
        let mut politica = red.politica();
        politica.general = false;
        red.cambiar_politica(politica);
        assert_eq!(
            red.autorizar(Servicio::Lrclib, "https://lrclib.net/api/get"),
            Err(NsError::NetworkDisabled)
        );
    }

    /// Una URL que viene en una respuesta de un servicio no puede usar el
    /// permiso de ese servicio para ir a otro sitio.
    #[test]
    fn un_servicio_solo_alcanza_sus_anfitriones() {
        let red = con(&Servicio::TODOS);
        for url in [
            "https://evil.example/x",
            "https://musicbrainz.org.evil.example/x",
            "https://lrclib.net@evil.example/x",
            "http://lrclib.net/api/get",
            "lrclib.net/api/get",
        ] {
            assert_eq!(
                red.autorizar(Servicio::Lrclib, url),
                Err(NsError::PathNotAllowed),
                "{url}"
            );
        }
        assert_eq!(
            red.autorizar(Servicio::Wikipedia, "https://es.wikipedia.org/w/api.php"),
            Ok(())
        );
        assert_eq!(
            red.autorizar(Servicio::Wikipedia, "https://wikipedia.org:443/"),
            Ok(())
        );
    }

    #[test]
    fn todos_los_servicios_tienen_anfitriones() {
        for servicio in Servicio::TODOS {
            assert!(!servicio.anfitriones().is_empty(), "{servicio:?}");
        }
    }
    #[test]
    fn las_actualizaciones_piden_su_propio_consentimiento_y_solo_van_a_github() {
        let red = con(&[Servicio::Actualizaciones]);
        assert_eq!(red.autorizar(Servicio::Actualizaciones, MANIFIESTO), Ok(()));
        assert_eq!(
            red.autorizar(
                Servicio::Actualizaciones,
                "https://objects.githubusercontent.com/github-production-release-asset/x"
            ),
            Ok(())
        );
        assert_eq!(
            red.autorizar(Servicio::Actualizaciones, "https://huggingface.co/x"),
            Err(NsError::PathNotAllowed)
        );
        assert_eq!(
            con(&[Servicio::Agregados]).autorizar(Servicio::Actualizaciones, MANIFIESTO),
            Err(NsError::ConsentRequired)
        );
    }

    /// La puerta comprueba la URL que el plugin va a usar de verdad.
    #[test]
    fn el_manifiesto_es_el_de_la_configuracion() {
        let conf: serde_json::Value =
            serde_json::from_str(include_str!("../tauri.conf.json")).unwrap();
        assert_eq!(
            conf["plugins"]["updater"]["endpoints"],
            serde_json::json!([MANIFIESTO])
        );
    }
}
