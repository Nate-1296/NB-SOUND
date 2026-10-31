//! El motor de audio (F2.1.1, ADR-003).
//!
//! Symphonia decodifica, una fuente propia encadena las pistas y Kira mezcla,
//! aplica los efectos y saca el sonido por cpal. La cadena de la pista de
//! reproducción es, en orden:
//!
//! ```text
//! fuente → preamplificación → 10 campanas → limitador → volumen → salida
//! ```
//!
//! Con el ecualizador plano y el volumen al máximo, cada etapa es la identidad
//! exacta: lo que sale es lo que había en el archivo, muestra a muestra, salvo los
//! picos por encima de −1 dBFS, que el limitador curva para que Kira no los
//! recorte en seco.
//!
//! El motor no sabe de colas, aleatorio ni repetición (F2.1.2): reproduce una
//! pista y, si se le dice cuál es la siguiente, la encadena sin hueco.

mod alimentador;
pub(crate) mod decodificador;
pub mod ecualizador;
mod fuente;
mod limitador;
#[cfg(test)]
pub(crate) mod pruebas;
pub mod remuestreo;
pub mod sonoridad;

use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::Arc;
use std::time::Duration;

use kira::backend::Backend;
use kira::effect::eq_filter::{EqFilterBuilder, EqFilterHandle, EqFilterKind};
use kira::effect::volume_control::{VolumeControlBuilder, VolumeControlHandle};
use kira::track::{TrackBuilder, TrackHandle, TrackPlaybackState};
use kira::{AudioManager, AudioManagerSettings, Decibels, Tween};

pub use self::alimentador::PistaEnCola;
use self::alimentador::{Alimentador, Orden};
use self::fuente::{Compartido, DatosFuente};
use crate::error::{NsError, NsResult};

/// Lo que el motor cuenta al resto de la aplicación.
#[derive(Debug, PartialEq)]
pub enum EventoMotor {
    /// Empezó a sonar una pista, la pedida o la siguiente encadenada.
    PistaEmpieza { ficha: u64 },
    /// Se acabó lo último que había que tocar.
    ColaTerminada,
    /// Una pista no se pudo abrir o dejó de poder leerse; el motor sigue con la
    /// siguiente si la tiene.
    PistaIlegible { ficha: u64, error: NsError },
}

/// Dónde está la reproducción.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Posicion {
    /// La ficha de la pista que suena, o 0 si ninguna.
    pub ficha: u64,
    pub segundos: f64,
    pub reproduciendo: bool,
}

/// Bloques de margen entre el alimentador y la fuente: unos 1,5 s a 44,1 kHz.
const BLOQUES_DE_MARGEN: usize = 16;
/// Transiciones de pausa y de volumen: sin clic, sin que se note espera.
const SUAVE: Duration = Duration::from_millis(30);

fn tween(duracion: Duration) -> Tween {
    Tween {
        duration: duracion,
        ..Default::default()
    }
}

/// Volumen lineal (0 a 1) en decibelios.
fn a_decibelios(lineal: f32) -> Decibels {
    if lineal >= 1.0 {
        Decibels::IDENTITY
    } else if lineal <= 0.001 {
        Decibels::SILENCE
    } else {
        Decibels(20.0 * lineal.log10())
    }
}

/// El motor. Genérico sobre la salida para poder probarlo sin tarjeta de sonido.
pub struct Motor<B: Backend = kira::DefaultBackend> {
    // Soltar el gestor cierra la salida: vive lo que vive el motor, aunque fuera de
    // las pruebas nadie lo lea.
    #[cfg_attr(not(test), allow(dead_code))]
    gestor: AudioManager<B>,
    pista: TrackHandle,
    campanas: Vec<EqFilterHandle>,
    preamp: VolumeControlHandle,
    ordenes: Sender<Orden>,
    compartido: Arc<Compartido>,
    generacion: u64,
    tasa_salida: Arc<AtomicU32>,
    eventos: Receiver<EventoMotor>,
}

impl Motor {
    /// Abre la salida de audio por defecto del sistema.
    ///
    /// # Errors
    ///
    /// [`NsError::ComponentUnavailable`] si no hay dispositivo de salida.
    pub fn nuevo() -> NsResult<Self> {
        Self::con(AudioManagerSettings::default())
    }
}

impl<B: Backend> Motor<B> {
    /// # Errors
    ///
    /// [`NsError::ComponentUnavailable`] si la salida no se puede abrir.
    pub fn con(ajustes: AudioManagerSettings<B>) -> NsResult<Self> {
        let mut gestor = AudioManager::<B>::new(ajustes).map_err(|_| {
            tracing::error!("no se pudo abrir la salida de audio");
            NsError::ComponentUnavailable
        })?;

        let mut constructor = TrackBuilder::new();
        let preamp = constructor.add_effect(VolumeControlBuilder::new(Decibels::IDENTITY));
        let campanas = ecualizador::BANDAS_HZ
            .iter()
            .map(|f| {
                constructor.add_effect(EqFilterBuilder::new(
                    EqFilterKind::Bell,
                    *f,
                    Decibels::IDENTITY,
                    ecualizador::Q,
                ))
            })
            .collect();
        let tasa_salida = Arc::new(AtomicU32::new(44_100));
        constructor.add_effect(limitador::Limitador {
            tasa: Arc::clone(&tasa_salida),
        });
        let mut pista = gestor
            .add_sub_track(constructor)
            .map_err(|_| NsError::Internal)?;

        let compartido = Arc::new(Compartido::default());
        let (tx_bloques, rx_bloques) = mpsc::sync_channel(BLOQUES_DE_MARGEN);
        let (tx_devueltos, rx_devueltos) = mpsc::sync_channel(BLOQUES_DE_MARGEN * 2 + 4);
        let (tx_ordenes, rx_ordenes) = mpsc::channel();
        let (tx_eventos, rx_eventos) = mpsc::channel();

        pista
            .play(DatosFuente {
                bloques: rx_bloques,
                devueltos: tx_devueltos,
                compartido: Arc::clone(&compartido),
                rampa_seg: 0.03,
            })
            .map_err(|_| NsError::Internal)?;

        let alimentador = Alimentador {
            ordenes: rx_ordenes,
            bloques: tx_bloques,
            devueltos: rx_devueltos,
            compartido: Arc::clone(&compartido),
            eventos: tx_eventos.clone(),
        };
        std::thread::Builder::new()
            .name("audio-alimentador".into())
            .spawn(move || alimentador.correr())
            .map_err(|_| NsError::Internal)?;
        vigilar(Arc::clone(&compartido), tx_eventos)?;

        Ok(Self {
            gestor,
            pista,
            campanas,
            preamp,
            ordenes: tx_ordenes,
            compartido,
            generacion: 0,
            tasa_salida,
            eventos: rx_eventos,
        })
    }

    fn nueva_generacion(&mut self) -> u64 {
        self.generacion += 1;
        self.compartido.terminado.store(false, Ordering::Release);
        // Antes de mandar la orden: desde este instante la fuente ya no reproduce
        // lo que había en la cola.
        self.compartido
            .generacion
            .store(self.generacion, Ordering::Release);
        self.generacion
    }

    /// Empieza a reproducir una pista, desde el principio o desde `desde_seg`.
    pub fn reproducir(&mut self, pista: PistaEnCola, desde_seg: f64) {
        let generacion = self.nueva_generacion();
        let _ = self.ordenes.send(Orden::Reproducir {
            generacion,
            pista,
            desde_seg,
        });
        self.pista.resume(tween(SUAVE));
    }

    /// La pista que sonará al acabar la actual, sin hueco. `None` para que la cola
    /// termine ahí.
    pub fn siguiente(&self, pista: Option<PistaEnCola>) {
        let _ = self.ordenes.send(Orden::Siguiente(pista));
    }

    pub fn buscar(&mut self, segundos: f64) {
        let generacion = self.nueva_generacion();
        let _ = self.ordenes.send(Orden::Buscar {
            generacion,
            segundos,
        });
    }

    pub fn pausar(&mut self) {
        self.pista.pause(tween(SUAVE));
    }

    pub fn reanudar(&mut self) {
        self.pista.resume(tween(SUAVE));
    }

    pub fn detener(&mut self) {
        let generacion = self.nueva_generacion();
        let _ = self.ordenes.send(Orden::Detener { generacion });
        // La próxima pista que empiece es nueva aunque sea la misma ficha.
        self.compartido.pista.store(0, Ordering::Relaxed);
        self.compartido.frame.store(0, Ordering::Relaxed);
    }

    /// Volumen lineal de 0 a 1.
    pub fn volumen(&mut self, lineal: f32) {
        self.pista
            .set_volume(a_decibelios(lineal.clamp(0.0, 1.0)), tween(SUAVE));
    }

    /// Las diez bandas y la preamplificación nominales, como las ve el usuario. El
    /// motor aplica la preamplificación con margen y las ganancias corregidas.
    pub fn ecualizador(&mut self, bandas_db: [f32; 10], preamp_db: f32) {
        let preamp = ecualizador::preamp_con_margen(preamp_db, &bandas_db);
        let tasa = f64::from(self.tasa_salida.load(Ordering::Relaxed));
        let ganancias = ecualizador::ganancias_corregidas(&bandas_db, tasa);
        self.preamp.set_volume(Decibels(preamp), tween(SUAVE));
        for (campana, g) in self.campanas.iter_mut().zip(ganancias) {
            campana.set_gain(Decibels(g), tween(SUAVE));
        }
    }

    /// Ecualizador desactivado: todas las etapas vuelven a la identidad exacta.
    pub fn sin_ecualizador(&mut self) {
        self.preamp.set_volume(Decibels::IDENTITY, tween(SUAVE));
        for campana in &mut self.campanas {
            campana.set_gain(Decibels::IDENTITY, tween(SUAVE));
        }
    }

    /// Añade a la pista que suena el instrumental que se acaba de preparar. Lo
    /// ya decodificado por delante (como mucho un segundo y medio) sigue sin él.
    pub fn instrumental_listo(&self, ficha: u64, ruta: std::path::PathBuf) {
        let _ = self
            .ordenes
            .send(alimentador::Orden::Instrumental { ficha, ruta });
    }

    /// Original o instrumental, con una transición de 30 ms.
    pub fn karaoke(&self, activo: bool) {
        self.compartido.karaoke(activo);
    }

    pub fn posicion(&self) -> Posicion {
        let ficha = self.compartido.pista.load(Ordering::Relaxed);
        let tasa = f64::from(self.compartido.tasa.load(Ordering::Relaxed).max(1));
        let frame = self.compartido.frame.load(Ordering::Relaxed);
        let reproduciendo = matches!(
            self.pista.state(),
            TrackPlaybackState::Playing | TrackPlaybackState::Resuming
        ) && ficha != 0
            && !self.compartido.terminado.load(Ordering::Acquire);
        Posicion {
            ficha,
            segundos: frame as f64 / tasa,
            reproduciendo,
        }
    }

    /// Los eventos pendientes, sin esperar.
    pub fn eventos(&self) -> impl Iterator<Item = EventoMotor> + '_ {
        self.eventos.try_iter()
    }

    #[cfg(test)]
    pub(crate) fn backend(&mut self) -> &mut B {
        self.gestor.backend_mut()
    }

    #[cfg(test)]
    pub(crate) fn compartido(&self) -> &Compartido {
        &self.compartido
    }
}

impl<B: Backend> Drop for Motor<B> {
    fn drop(&mut self) {
        self.compartido.cerrado.store(true, Ordering::Release);
    }
}

/// Cuenta como eventos lo que el hilo de audio apunta: él no puede mandar
/// mensajes, solo dejar marcas sin cerrojos.
fn vigilar(compartido: Arc<Compartido>, eventos: Sender<EventoMotor>) -> NsResult<()> {
    std::thread::Builder::new()
        .name("audio-vigia".into())
        .spawn(move || {
            let mut leidos = 0u64;
            while !compartido.cerrado.load(Ordering::Acquire) {
                let mut vivo = true;
                compartido.leer_sucesos(&mut leidos, &mut |suceso| {
                    let evento = if suceso == fuente::FIN {
                        EventoMotor::ColaTerminada
                    } else {
                        EventoMotor::PistaEmpieza { ficha: suceso }
                    };
                    vivo &= eventos.send(evento).is_ok();
                });
                if !vivo {
                    return;
                }
                std::thread::sleep(Duration::from_millis(15));
            }
        })
        .map(|_| ())
        .map_err(|_| NsError::Internal)
}
