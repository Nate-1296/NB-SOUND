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
}

impl Servicio {
    pub const TODOS: [Servicio; 12] = [
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
}
