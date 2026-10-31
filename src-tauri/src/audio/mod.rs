//! El motor de audio (F2.1.1, ADR-003).
//!
//! Symphonia decodifica, una fuente propia encadena las pistas y Kira mezcla,
//! aplica los efectos y saca el sonido por cpal. Hay dos platos, cada uno con su
//! fuente, y los dos desembocan en la pista maestra:
//!
//! ```text
//! plato 1: fuente → 10 bandas → volumen ┐
//!                                       ├→ preamplificación → 10 campanas → limitador → volumen → salida
//! plato 2: fuente → 10 bandas → volumen ┘
//! ```
//!
//! La reproducción normal usa un plato; el DJ mezcla con los dos (F6.1.3), y al
//! acabar cada mezcla el otro pasa a ser el activo. Con el ecualizador plano, las
//! bandas de los platos a 0 dB y los volúmenes al máximo, cada etapa es la
//! identidad exacta: lo que sale es lo que había en el archivo, muestra a muestra, salvo los
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

use std::sync::atomic::{AtomicU32, AtomicUsize, Ordering};
use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::Arc;
use std::time::Duration;

use kira::backend::Backend;
use kira::effect::eq_filter::{EqFilterBuilder, EqFilterHandle, EqFilterKind};
use kira::effect::volume_control::{VolumeControlBuilder, VolumeControlHandle};
use kira::track::{TrackBuilder, TrackHandle, TrackPlaybackState};
use kira::{AudioManager, AudioManagerSettings, Decibels, Easing, Tween};

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

/// Un plato: una fuente con su alimentador, colgada de la pista maestra con sus
/// diez bandas y su volumen. La reproducción normal usa uno; el DJ mezcla con los
/// dos (F6.1.3). En reposo las bandas están a 0 dB y el volumen a la identidad, que
/// son exactos: un plato no cambia ninguna muestra de lo que reproduce.
struct Plato {
    pista: TrackHandle,
    /// El último volumen pedido, lineal.
    volumen: f32,
    bandas: Vec<EqFilterHandle>,
    ordenes: Sender<Orden>,
    compartido: Arc<Compartido>,
    generacion: u64,
}

impl Plato {
    fn nuevo(
        maestra: &mut TrackHandle,
        indice: usize,
        activo: &Arc<AtomicUsize>,
        eventos: &Sender<EventoMotor>,
    ) -> NsResult<Self> {
        let mut constructor = TrackBuilder::new();
        let bandas = ecualizador::BANDAS_HZ
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
        let mut pista = maestra
            .add_sub_track(constructor)
            .map_err(|_| NsError::Internal)?;

        let compartido = Arc::new(Compartido::default());
        // Sin nada que tocar: así el plato en reposo no cuenta como pendiente.
        compartido.terminado.store(true, Ordering::Release);
        let (tx_bloques, rx_bloques) = mpsc::sync_channel(BLOQUES_DE_MARGEN);
        let (tx_devueltos, rx_devueltos) = mpsc::sync_channel(BLOQUES_DE_MARGEN * 2 + 4);
        let (tx_ordenes, rx_ordenes) = mpsc::channel();
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
            eventos: eventos.clone(),
        };
        std::thread::Builder::new()
            .name(format!("audio-alimentador-{indice}"))
            .spawn(move || alimentador.correr())
            .map_err(|_| NsError::Internal)?;
        vigilar(
            Arc::clone(&compartido),
            indice,
            Arc::clone(activo),
            eventos.clone(),
        )?;
        Ok(Self {
            pista,
            volumen: 1.0,
            bandas,
            ordenes: tx_ordenes,
            compartido,
            generacion: 0,
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

    fn reproducir(&mut self, pista: PistaEnCola, desde_seg: f64) {
        let generacion = self.nueva_generacion();
        let _ = self.ordenes.send(Orden::Reproducir {
            generacion,
            pista,
            desde_seg,
        });
    }

    fn detener(&mut self) {
        let generacion = self.nueva_generacion();
        let _ = self.ordenes.send(Orden::Detener { generacion });
        // La próxima pista que empiece es nueva aunque sea la misma ficha.
        self.compartido.pista.store(0, Ordering::Relaxed);
        self.compartido.frame.store(0, Ordering::Relaxed);
    }

    fn posicion(&self) -> (u64, f64) {
        let ficha = self.compartido.pista.load(Ordering::Relaxed);
        let tasa = f64::from(self.compartido.tasa.load(Ordering::Relaxed).max(1));
        let frame = self.compartido.frame.load(Ordering::Relaxed);
        (ficha, frame as f64 / tasa)
    }

    /// Kira interpola el volumen en decibelios: con dos rampas rectas que se cruzan,
    /// a mitad las dos van 30 dB abajo y el corte deja un hueco de 3 dB. La que baja
    /// lo hace tarde y la que sube pronto, y el cruce queda casi a potencia constante.
    fn volumen(&mut self, lineal: f32, duracion: Duration) {
        let lineal = lineal.clamp(0.0, 1.0);
        let easing = if lineal < self.volumen {
            Easing::InPowi(4)
        } else if lineal > self.volumen {
            Easing::OutPowi(4)
        } else {
            Easing::Linear
        };
        self.volumen = lineal;
        self.pista.set_volume(
            a_decibelios(lineal),
            Tween {
                duration: duracion,
                easing,
                ..Default::default()
            },
        );
    }

    fn bandas(&mut self, bandas_db: &[f32; 10], tasa: f64, duracion: Duration) {
        let ganancias = ecualizador::ganancias_corregidas(bandas_db, tasa);
        for (banda, g) in self.bandas.iter_mut().zip(ganancias) {
            banda.set_gain(Decibels(g), tween(duracion));
        }
    }

    fn sin_bandas(&mut self, duracion: Duration) {
        for banda in &mut self.bandas {
            banda.set_gain(Decibels::IDENTITY, tween(duracion));
        }
    }
}

/// Las bandas de un plato vuelven a plano despacio al acabar una mezcla: tras quitar
/// graves, la entrante termina con los bajos 3 dB arriba, y devolverlos de golpe se
/// oiría.
const REPOSO_BANDAS: Duration = Duration::from_millis(1500);

/// El motor. Genérico sobre la salida para poder probarlo sin tarjeta de sonido.
pub struct Motor<B: Backend = kira::DefaultBackend> {
    // Soltar el gestor cierra la salida: vive lo que vive el motor, aunque fuera de
    // las pruebas nadie lo lea.
    #[cfg_attr(not(test), allow(dead_code))]
    gestor: AudioManager<B>,
    /// El ecualizador del usuario, el limitador y el volumen general.
    maestra: TrackHandle,
    campanas: Vec<EqFilterHandle>,
    preamp: VolumeControlHandle,
    platos: [Plato; 2],
    /// El plato que suena como "la pista actual"; el otro solo entra en una mezcla.
    activo: Arc<AtomicUsize>,
    tasa_salida: Arc<AtomicU32>,
    avisos: Sender<EventoMotor>,
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
        let mut maestra = gestor
            .add_sub_track(constructor)
            .map_err(|_| NsError::Internal)?;

        let (tx_eventos, rx_eventos) = mpsc::channel();
        let activo = Arc::new(AtomicUsize::new(0));
        let platos = [
            Plato::nuevo(&mut maestra, 0, &activo, &tx_eventos)?,
            Plato::nuevo(&mut maestra, 1, &activo, &tx_eventos)?,
        ];

        Ok(Self {
            gestor,
            maestra,
            campanas,
            preamp,
            platos,
            activo,
            tasa_salida,
            avisos: tx_eventos,
            eventos: rx_eventos,
        })
    }

    fn indice_activo(&self) -> usize {
        self.activo.load(Ordering::Acquire)
    }

    fn plato(&mut self) -> &mut Plato {
        let i = self.indice_activo();
        &mut self.platos[i]
    }

    fn plato_activo(&self) -> &Plato {
        &self.platos[self.indice_activo()]
    }

    /// Empieza a reproducir una pista, desde el principio o desde `desde_seg`.
    pub fn reproducir(&mut self, pista: PistaEnCola, desde_seg: f64) {
        self.cancelar_mezcla();
        self.plato().reproducir(pista, desde_seg);
        self.maestra.resume(tween(SUAVE));
    }

    /// La pista que sonará al acabar la actual, sin hueco. `None` para que la cola
    /// termine ahí.
    pub fn siguiente(&self, pista: Option<PistaEnCola>) {
        let _ = self.plato_activo().ordenes.send(Orden::Siguiente(pista));
    }

    pub fn buscar(&mut self, segundos: f64) {
        let plato = self.plato();
        let generacion = plato.nueva_generacion();
        let _ = plato.ordenes.send(Orden::Buscar {
            generacion,
            segundos,
        });
    }

    pub fn pausar(&mut self) {
        self.maestra.pause(tween(SUAVE));
    }

    pub fn reanudar(&mut self) {
        self.maestra.resume(tween(SUAVE));
    }

    pub fn detener(&mut self) {
        self.cancelar_mezcla();
        self.plato().detener();
    }

    /// Volumen lineal de 0 a 1.
    pub fn volumen(&mut self, lineal: f32) {
        self.maestra
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
            .plato_activo()
            .ordenes
            .send(alimentador::Orden::Instrumental { ficha, ruta });
    }

    /// Original o instrumental, con una transición de 30 ms.
    pub fn karaoke(&self, activo: bool) {
        self.plato_activo().compartido.karaoke(activo);
    }

    pub fn posicion(&self) -> Posicion {
        let plato = self.plato_activo();
        let (ficha, segundos) = plato.posicion();
        let reproduciendo = matches!(
            self.maestra.state(),
            TrackPlaybackState::Playing | TrackPlaybackState::Resuming
        ) && ficha != 0
            && !plato.compartido.terminado.load(Ordering::Acquire);
        Posicion {
            ficha,
            segundos,
            reproduciendo,
        }
    }

    // --- La mezcla del DJ (F6.1.3) ----------------------------------------------------

    /// Carga en el plato libre, en silencio, la pista que va a entrar, desde
    /// `desde_seg` y, si `instrumental`, sonando su instrumental. Empieza a
    /// decodificar y a avanzar en cuanto llega; la mezcla la sube con
    /// [`Self::mezclar`].
    pub fn preparar_entrante(&mut self, pista: PistaEnCola, desde_seg: f64, instrumental: bool) {
        let tasa = f64::from(self.tasa_salida.load(Ordering::Relaxed));
        let libre = &mut self.platos[1 - self.indice_activo()];
        libre.volumen(0.0, Duration::ZERO);
        libre.bandas(&[0.0; 10], tasa, Duration::ZERO);
        libre.compartido.karaoke(instrumental);
        libre.reproducir(pista, desde_seg);
    }

    /// Dónde va la pista que entra: ficha y segundos de esa pista.
    pub fn posicion_entrante(&self) -> (u64, f64) {
        self.platos[1 - self.indice_activo()].posicion()
    }

    /// Un paso de la mezcla: el volumen lineal y las diez bandas en dB de la que
    /// sale y de la que entra, y cuánto suena del instrumental de la que entra.
    /// Kira lleva cada valor al nuevo en 30 ms, así que los pasos no hacen clic.
    pub fn mezclar(
        &mut self,
        volumenes: (f32, f32),
        bandas: (&[f32; 10], &[f32; 10]),
        instrumental_entrante: f32,
    ) {
        let tasa = f64::from(self.tasa_salida.load(Ordering::Relaxed));
        let i = self.indice_activo();
        for (k, volumen, banda) in [(i, volumenes.0, bandas.0), (1 - i, volumenes.1, bandas.1)] {
            let plato = &mut self.platos[k];
            plato.volumen(volumen, SUAVE);
            plato.bandas(banda, tasa, SUAVE);
        }
        self.platos[1 - i].compartido.mezcla.store(
            instrumental_entrante.clamp(0.0, 1.0).to_bits(),
            Ordering::Relaxed,
        );
    }

    /// La mezcla acabó: la que entró pasa a ser la pista actual y la que salió se
    /// detiene. Cuenta que empezó la entrante, como si el motor la hubiera
    /// encadenado.
    pub fn terminar_mezcla(&mut self) {
        let i = self.indice_activo();
        let saliente = &mut self.platos[i];
        saliente.detener();
        saliente.compartido.terminado.store(true, Ordering::Release);
        saliente.sin_bandas(Duration::ZERO);
        saliente.volumen(0.0, Duration::ZERO);
        let entrante = &mut self.platos[1 - i];
        entrante.volumen(1.0, SUAVE);
        entrante.sin_bandas(REPOSO_BANDAS);
        entrante.compartido.karaoke(false);
        let (ficha, _) = entrante.posicion();
        self.activo.store(1 - i, Ordering::Release);
        if ficha != 0 {
            let _ = self.avisos.send(EventoMotor::PistaEmpieza { ficha });
        }
    }

    /// Deshace una mezcla a medias: la entrante se calla y la actual vuelve a
    /// sonar entera. Sin mezcla en curso no cambia nada que se oiga.
    pub fn cancelar_mezcla(&mut self) {
        let i = self.indice_activo();
        let libre = &mut self.platos[1 - i];
        if !libre.compartido.terminado.load(Ordering::Acquire) {
            libre.detener();
            libre.compartido.terminado.store(true, Ordering::Release);
        }
        libre.volumen(0.0, SUAVE);
        libre.sin_bandas(SUAVE);
        let activo = &mut self.platos[i];
        activo.volumen(1.0, SUAVE);
        activo.sin_bandas(SUAVE);
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
        &self.plato_activo().compartido
    }

    #[cfg(test)]
    pub(crate) fn compartidos(&self) -> [&Compartido; 2] {
        [&self.platos[0].compartido, &self.platos[1].compartido]
    }
}

impl<B: Backend> Drop for Motor<B> {
    fn drop(&mut self) {
        for plato in &self.platos {
            plato.compartido.cerrado.store(true, Ordering::Release);
        }
    }
}

/// Cuenta como eventos lo que el hilo de audio apunta: él no puede mandar
/// mensajes, solo dejar marcas sin cerrojos. Solo cuenta lo del plato activo: la
/// pista que entra en una mezcla "empieza" cuando la mezcla acaba
/// ([`Motor::terminar_mezcla`]), y la que sale no "termina la cola".
fn vigilar(
    compartido: Arc<Compartido>,
    indice: usize,
    activo: Arc<AtomicUsize>,
    eventos: Sender<EventoMotor>,
) -> NsResult<()> {
    std::thread::Builder::new()
        .name(format!("audio-vigia-{indice}"))
        .spawn(move || {
            let mut leidos = 0u64;
            while !compartido.cerrado.load(Ordering::Acquire) {
                let mut vivo = true;
                let es_activo = activo.load(Ordering::Acquire) == indice;
                compartido.leer_sucesos(&mut leidos, &mut |suceso| {
                    if !es_activo {
                        return;
                    }
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
