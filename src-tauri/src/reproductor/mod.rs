//! El servicio de reproducción (F2.1.7): une la cola, el motor y la base.
//!
//! La cola decide qué suena; el motor lo toca; este servicio traduce lo uno en lo
//! otro, guarda la sesión, apunta el historial y cuenta a la interfaz lo que pasa.
//! Vive en su propio hilo y se le habla con órdenes, así que ningún comando del
//! puente espera al disco ni al audio.
//!
//! Para encadenar sin hueco, el servicio le dice siempre al motor cuál es la pista
//! prevista ([`Cola::prevista`]). Cuando el motor la empieza por su cuenta, el
//! servicio avanza la cola y comprueba que coincide.

mod dj;
mod fragmento;
pub mod persistencia;
#[cfg(test)]
mod pruebas;

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::mpsc::{self, Receiver, RecvTimeoutError, Sender};
use std::sync::{Arc, RwLock};
use std::time::{Duration, Instant};

use kira::backend::Backend;
use serde::Serialize;
use ts_rs::TS;

use crate::audio::{ecualizador, EventoMotor, Motor, PistaEnCola};
use crate::cola::{Accion, Cola, Estado, Fila, Repeticion};
use crate::db::BaseDeDatos;
use crate::error::{NsError, NsResult};

pub use self::dj::{EstadoDj, MezclaVisible, OrdenDj};
pub use self::persistencia::{carpeta_musica, leer_ecualizador, AjustesEcualizador};

/// Lo que la interfaz puede pedir.
#[derive(Debug)]
pub enum Orden {
    ReproducirPistas {
        ids: Vec<i64>,
        desde: usize,
    },
    ReproducirPista(i64),
    ReproducirIndice(usize),
    PausarReanudar,
    Siguiente,
    Anterior,
    Buscar(f64),
    Volumen(f32),
    Aleatorio(bool),
    Repeticion(Repeticion),
    Agregar {
        ids: Vec<i64>,
        justo_despues: bool,
    },
    Quitar(usize),
    Mover {
        desde: usize,
        hasta: usize,
    },
    Vaciar {
        salvo_la_actual: bool,
    },
    Purgar(i64),
    Ecualizador(AjustesEcualizador),
    Normalizar(bool),
    Karaoke(bool),
    /// El karaoke terminó de preparar esta pista (F5.2.2): si es la que suena, el
    /// micrófono se puede usar sin esperar a la siguiente.
    InstrumentalListo(i64),
    /// Vuelve a leer la sesión y las preferencias: la primera vez que se abre la
    /// V2, el importador de la V1 termina con el reproductor ya en marcha.
    Recargar,
    /// Una sesión del DJ Privado (F6.1.6).
    Dj(OrdenDj),
    /// Unos segundos de una canción sin decir cuál es (A ciegas, F6.2.2).
    Fragmento {
        pista_id: i64,
        desde_seg: f64,
        segundos: f64,
    },
}

/// Lo que ve la interfaz. Se publica entera cada vez que cambia algo.
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct Instantanea {
    /// `detenido`, `reproduciendo`, `pausado` o `finalizada`.
    pub estado: String,
    #[ts(type = "number | null")]
    pub pista_id: Option<i64>,
    pub posicion_seg: f64,
    pub duracion_seg: f64,
    pub indice_cola: Option<u32>,
    #[ts(type = "number[]")]
    pub cola: Vec<i64>,
    pub aleatorio: bool,
    /// `ninguno`, `todo` o `uno`.
    pub repeticion: String,
    pub volumen: f32,
    pub normalizar: bool,
    pub karaoke_disponible: bool,
    pub karaoke_activo: bool,
    /// Con una sesión del DJ sonando: cuál, por dónde va y si está mezclando.
    pub dj: Option<EstadoDj>,
    /// Suena un fragmento a ciegas: la pista no se dice, y la posición y la
    /// duración son las del fragmento.
    pub ciego: bool,
}

/// Un aviso para la interfaz: el código canónico del error y la pista.
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct AvisoReproductor {
    pub codigo: String,
    #[ts(type = "number | null")]
    pub pista_id: Option<i64>,
}

/// A quién contarle los cambios: en la aplicación, el emisor de eventos de Tauri.
pub trait Oyente: Send {
    fn instantanea(&self, i: &Instantanea);
    fn aviso(&self, a: &AvisoReproductor);
}

fn texto_estado(e: Estado) -> &'static str {
    match e {
        Estado::Detenido => "detenido",
        Estado::Reproduciendo => "reproduciendo",
        Estado::Pausado => "pausado",
        Estado::Finalizada => "finalizada",
    }
}

fn texto_repeticion(r: Repeticion) -> &'static str {
    match r {
        Repeticion::Ninguno => "ninguno",
        Repeticion::Todo => "todo",
        Repeticion::Uno => "uno",
    }
}

/// Lo que el motor está tocando, por ficha.
#[derive(Debug, Clone)]
struct Sonando {
    ficha: u64,
    fila: Fila,
    duracion_seg: f64,
    karaoke: bool,
}

pub struct Servicio<B: Backend> {
    motor: Motor<B>,
    cola: Cola,
    db: BaseDeDatos,
    stems: PathBuf,
    musica: Option<PathBuf>,
    oyente: Box<dyn Oyente>,
    siguiente_ficha: u64,
    actual: Option<Sonando>,
    prevista: Option<Sonando>,
    fichas: HashMap<u64, Sonando>,
    volumen: f32,
    normalizar: bool,
    karaoke: bool,
    ultima: Option<Instantanea>,
    dj: Option<dj::ModoDj>,
    fragmento: Option<fragmento::Fragmento>,
    /// El perfil del equipo para mezclar por capas (F6.1.4).
    equipo: crate::dj::equipo::Equipo,
    /// La posición guardada de la cola, para devolverla tras una sesión del DJ que
    /// empezó antes de que la cola sonara.
    cola_seg_restaurada: f64,
}

impl<B: Backend> Servicio<B> {
    /// Abre el servicio sobre un motor y restaura la sesión guardada, sin empezar a
    /// sonar.
    ///
    /// # Errors
    ///
    /// [`NsError::StorageFailure`] si no se puede leer la base.
    pub fn nuevo(
        motor: Motor<B>,
        cola: Cola,
        db: BaseDeDatos,
        stems: PathBuf,
        oyente: Box<dyn Oyente>,
    ) -> NsResult<Self> {
        let mut s = Self {
            motor,
            cola,
            db,
            stems,
            musica: None,
            oyente,
            siguiente_ficha: 1,
            actual: None,
            prevista: None,
            fichas: HashMap::new(),
            volumen: 1.0,
            normalizar: true,
            karaoke: false,
            ultima: None,
            dj: None,
            fragmento: None,
            equipo: crate::dj::equipo::Equipo::default(),
            cola_seg_restaurada: 0.0,
        };
        s.restaurar()?;
        s.restaurar_dj();
        s.publicar();
        Ok(s)
    }

    /// Comparte la medida del equipo con quien la hace.
    #[must_use]
    pub fn con_equipo(mut self, equipo: crate::dj::equipo::Equipo) -> Self {
        self.equipo = equipo;
        self
    }

    /// Lee la sesión guardada y las preferencias y las aplica sin empezar a sonar.
    fn restaurar(&mut self) -> NsResult<()> {
        let (sesion, musica, eq) = {
            let conn = self.db.conexion()?;
            (
                persistencia::leer_sesion(&conn)?,
                persistencia::carpeta_musica(&conn)?,
                persistencia::leer_ecualizador(&conn)?,
            )
        };
        self.musica = musica;
        self.volumen = sesion.volumen;
        self.normalizar = sesion.normalizar;
        self.motor.volumen(sesion.volumen);
        self.aplicar_ecualizador(&eq);
        self.cola.fijar_repeticion(sesion.repeticion);
        self.cola_seg_restaurada = sesion.posicion_seg;
        self.cola
            .restaurar(sesion.cola, sesion.posicion_cola, sesion.posicion_seg);
        if sesion.aleatorio {
            // El orden guardado ya es el barajado: se marca sin volver a barajar.
            self.cola.marcar_aleatorio();
        }
        Ok(())
    }

    fn resolver(&mut self, fila: Fila) -> Option<(PistaEnCola, Sonando)> {
        let conn = self.db.conexion().ok()?;
        let pista = persistencia::resolver(
            &conn,
            fila.pista_id,
            self.musica.as_deref(),
            &self.stems,
            self.normalizar,
        )
        .ok()
        .flatten()?;
        let ficha = self.siguiente_ficha;
        self.siguiente_ficha += 1;
        let sonando = Sonando {
            ficha,
            fila,
            duracion_seg: pista.duracion_seg,
            karaoke: pista.instrumental.is_some(),
        };
        self.fichas.insert(ficha, sonando.clone());
        Some((
            PistaEnCola {
                ficha,
                ruta: pista.ruta,
                instrumental: pista.instrumental,
                ganancia_db: pista.ganancia_db,
            },
            sonando,
        ))
    }

    fn avisar(&self, error: NsError, pista_id: Option<i64>) {
        self.oyente.aviso(&AvisoReproductor {
            codigo: error.code().to_owned(),
            pista_id,
        });
    }

    /// Hace en el motor lo que la cola decidió.
    fn ejecutar(&mut self, accion: Accion) {
        match accion {
            Accion::Nada => {}
            Accion::Reproducir { fila, desde_seg } => match self.resolver(fila) {
                Some((pista, sonando)) => {
                    self.motor.reproducir(pista, desde_seg);
                    self.actual = Some(sonando);
                }
                None => {
                    // La pista ya no existe en la base: se dice y se sigue.
                    self.avisar(NsError::FileNotFound, Some(fila.pista_id));
                    let siguiente = self.cola.fin_de_pista();
                    if siguiente != accion {
                        self.ejecutar(siguiente);
                    }
                }
            },
            Accion::Pausar => self.motor.pausar(),
            Accion::Reanudar => self.motor.reanudar(),
            Accion::Detener => {
                self.motor.detener();
                self.actual = None;
            }
        }
    }

    /// Mantiene informado al motor de lo que viene después.
    fn preparar_siguiente(&mut self) {
        // En una sesión del DJ, lo siguiente lo decide la mezcla; en un fragmento,
        // no hay siguiente.
        if self.en_dj() || self.fragmento.is_some() {
            return;
        }
        // Las fichas viejas ya no van a volver en ningún evento que importe.
        let vivas = [&self.actual, &self.prevista].map(|s| s.as_ref().map(|s| s.ficha));
        self.fichas
            .retain(|f, _| vivas.contains(&Some(*f)) || *f + 8 > self.siguiente_ficha);
        let prevista = self.cola.prevista();
        if prevista.map(|f| f.pista_id) == self.prevista.as_ref().map(|s| s.fila.pista_id) {
            return;
        }
        match prevista.and_then(|f| self.resolver(f)) {
            Some((pista, sonando)) => {
                self.motor.siguiente(Some(pista));
                self.prevista = Some(sonando);
            }
            None => {
                self.motor.siguiente(None);
                self.prevista = None;
            }
        }
    }

    /// Atiende una orden de la interfaz.
    pub fn atender(&mut self, orden: Orden) {
        if self.interceptar_fragmento(&orden) {
            self.publicar();
            return;
        }
        if self.interceptar_dj(&orden) {
            self.guardar();
            self.publicar();
            return;
        }
        let accion = match orden {
            Orden::Dj(o) => {
                self.atender_dj(o);
                Accion::Nada
            }
            Orden::Fragmento {
                pista_id,
                desde_seg,
                segundos,
            } => {
                self.tocar_fragmento(pista_id, desde_seg, segundos);
                Accion::Nada
            }
            Orden::ReproducirPistas { ids, desde } => self.cola.reproducir_cola(
                ids.into_iter().map(|pista_id| Fila { pista_id }).collect(),
                desde,
            ),
            Orden::ReproducirPista(pista_id) => self.cola.reproducir_pista(Fila { pista_id }),
            Orden::ReproducirIndice(i) => self.cola.reproducir_indice(i).unwrap_or(Accion::Nada),
            Orden::PausarReanudar => self.cola.pausar_reanudar(),
            Orden::Siguiente => self.cola.siguiente(),
            Orden::Anterior => self.cola.anterior(),
            Orden::Buscar(segundos) => {
                let duracion = self.actual.as_ref().map_or(0.0, |s| s.duracion_seg);
                if duracion > 0.0 {
                    self.motor.buscar(segundos.clamp(0.0, duracion));
                }
                Accion::Nada
            }
            Orden::Volumen(v) => {
                self.volumen = v.clamp(0.0, 1.0);
                self.motor.volumen(self.volumen);
                Accion::Nada
            }
            Orden::Aleatorio(a) => {
                self.cola.fijar_aleatorio(a);
                Accion::Nada
            }
            Orden::Repeticion(r) => {
                self.cola.fijar_repeticion(r);
                Accion::Nada
            }
            Orden::Agregar { ids, justo_despues } => {
                let filas: Vec<Fila> = ids.into_iter().map(|pista_id| Fila { pista_id }).collect();
                if justo_despues {
                    // Una a una y en orden inverso, para que queden en el orden pedido.
                    for f in filas.iter().rev() {
                        self.cola.agregar(*f, true);
                    }
                } else {
                    self.cola.agregar_varias(&filas);
                }
                Accion::Nada
            }
            Orden::Quitar(i) => self.cola.quitar(i),
            Orden::Mover { desde, hasta } => {
                self.cola.mover(desde, hasta);
                Accion::Nada
            }
            Orden::Vaciar { salvo_la_actual } => {
                if salvo_la_actual {
                    self.cola.vaciar_salvo_la_actual()
                } else {
                    self.cola.limpiar();
                    Accion::Nada
                }
            }
            Orden::Purgar(id) => self.cola.purgar(id),
            Orden::Ecualizador(a) => {
                self.aplicar_ecualizador(&a);
                if let Err(e) = persistencia::guardar_ecualizador(&self.db, &a) {
                    self.avisar(e, None);
                }
                Accion::Nada
            }
            Orden::Normalizar(n) => {
                // Se aplica desde la próxima pista: cambiarla a mitad sería un salto.
                self.normalizar = n;
                self.prevista = None;
                Accion::Nada
            }
            Orden::Recargar => {
                // Solo si no suena nada: lo que el usuario ya eligió manda.
                if self.actual.is_none() && self.cola.filas().is_empty() {
                    if let Err(e) = self.restaurar() {
                        self.avisar(e, None);
                    }
                    self.publicar();
                    return;
                }
                Accion::Nada
            }
            Orden::Karaoke(k) => {
                self.karaoke = k && self.actual.as_ref().is_some_and(|s| s.karaoke);
                self.motor.karaoke(self.karaoke);
                Accion::Nada
            }
            Orden::InstrumentalListo(pista) => {
                let ruta = self
                    .actual
                    .as_ref()
                    .filter(|s| s.fila.pista_id == pista && !s.karaoke)
                    .and_then(|_| self.db.conexion().ok())
                    .and_then(|conn| {
                        persistencia::resolver(
                            &conn,
                            pista,
                            self.musica.as_deref(),
                            &self.stems,
                            self.normalizar,
                        )
                        .ok()
                        .flatten()
                    })
                    .and_then(|p| p.instrumental);
                if let (Some(ruta), Some(s)) = (ruta, self.actual.as_mut()) {
                    s.karaoke = true;
                    if let Some(f) = self.fichas.get_mut(&s.ficha) {
                        f.karaoke = true;
                    }
                    self.motor.instrumental_listo(s.ficha, ruta);
                }
                Accion::Nada
            }
        };
        self.ejecutar(accion);
        self.preparar_siguiente();
        self.guardar();
        self.publicar();
    }

    fn aplicar_ecualizador(&mut self, a: &AjustesEcualizador) {
        if !a.activo {
            self.motor.sin_ecualizador();
            return;
        }
        match a
            .preseleccion
            .and_then(|i| ecualizador::PRESELECCIONES.get(i as usize))
        {
            Some(p) => self.motor.ecualizador(p.bandas_db, p.preamp_db),
            None => self.motor.ecualizador(a.bandas, a.preamp),
        }
    }

    /// Atiende lo que contó el motor. Se llama a menudo desde el hilo del servicio.
    pub fn atender_motor(&mut self) {
        let eventos: Vec<EventoMotor> = self.motor.eventos().collect();
        if self.fragmento.is_some() {
            let terminada = eventos.iter().any(|e| {
                matches!(
                    e,
                    EventoMotor::ColaTerminada | EventoMotor::PistaIlegible { .. }
                )
            });
            if self.tic_fragmento(terminada) {
                self.guardar();
            }
            self.publicar();
            return;
        }
        if self.en_dj() {
            let hubo = !eventos.is_empty();
            self.eventos_dj(eventos);
            if self.tic_dj() || hubo {
                self.guardar();
            }
            self.publicar();
            return;
        }
        let mut cambio = false;
        for evento in eventos {
            cambio = true;
            match evento {
                EventoMotor::PistaEmpieza { ficha } => {
                    if self.actual.as_ref().is_some_and(|s| s.ficha == ficha) {
                        continue;
                    }
                    // El motor encadenó la prevista: la anterior acabó entera.
                    if let Some(anterior) = self.actual.take() {
                        let _ = persistencia::registrar_escucha(
                            &self.db,
                            anterior.fila.pista_id,
                            anterior.duracion_seg,
                        );
                    }
                    let accion = self.cola.fin_de_pista();
                    let empezada = self.fichas.get(&ficha).cloned();
                    match (accion, empezada) {
                        (Accion::Reproducir { fila, .. }, Some(s)) if fila == s.fila => {
                            self.actual = Some(s);
                            self.prevista = None;
                        }
                        // La cola cambió después de preparar la siguiente: manda la cola.
                        (otra, _) => self.ejecutar(otra),
                    }
                    self.karaoke = false;
                    self.motor.karaoke(false);
                }
                EventoMotor::ColaTerminada => {
                    if let Some(anterior) = self.actual.take() {
                        let _ = persistencia::registrar_escucha(
                            &self.db,
                            anterior.fila.pista_id,
                            anterior.duracion_seg,
                        );
                    }
                    let accion = self.cola.fin_de_pista();
                    self.ejecutar(accion);
                }
                EventoMotor::PistaIlegible { ficha, error } => {
                    let pista = self.fichas.get(&ficha).map(|s| s.fila.pista_id);
                    self.avisar(error, pista);
                    if self.actual.as_ref().is_some_and(|s| s.ficha == ficha) {
                        // El motor sigue con la prevista si la tiene; la cola, también.
                        self.actual = None;
                    }
                }
            }
        }
        if cambio {
            self.preparar_siguiente();
            self.guardar();
        }
        self.publicar();
    }

    fn guardar(&self) {
        let pos = self.motor.posicion();
        // Con una sesión del DJ, lo que suena no es la cola: la cola guarda donde se
        // quedó, y la sesión, por dónde va.
        let posicion_seg = self
            .cola_seg_fragmento()
            .or_else(|| self.guardar_dj())
            .unwrap_or(pos.segundos);
        let sesion = persistencia::Sesion {
            cola: self.cola.filas().to_vec(),
            posicion_cola: self.cola.indice().unwrap_or(0),
            posicion_seg,
            volumen: self.volumen,
            aleatorio: self.cola.aleatorio(),
            repeticion: self.cola.repeticion(),
            normalizar: self.normalizar,
        };
        if let Err(e) =
            persistencia::guardar_sesion(&self.db, &sesion, self.cola.activa().map(|f| f.pista_id))
        {
            self.avisar(e, None);
        }
    }

    /// Guarda la posición exacta: al cerrar, para volver al mismo segundo.
    pub fn guardar_al_cerrar(&mut self) {
        self.guardar();
        self.motor.detener();
    }

    pub fn instantanea(&self) -> Instantanea {
        let pos = self.motor.posicion();
        let actual = self.actual.as_ref();
        let mut i = Instantanea {
            estado: texto_estado(self.cola.estado()).to_owned(),
            pista_id: self.cola.activa().map(|f| f.pista_id),
            posicion_seg: if actual.is_some_and(|s| s.ficha == pos.ficha) {
                pos.segundos
            } else {
                0.0
            },
            duracion_seg: actual.map_or(0.0, |s| s.duracion_seg),
            indice_cola: self.cola.indice().map(|i| i as u32),
            cola: self.cola.filas().iter().map(|f| f.pista_id).collect(),
            aleatorio: self.cola.aleatorio(),
            repeticion: texto_repeticion(self.cola.repeticion()).to_owned(),
            volumen: self.volumen,
            normalizar: self.normalizar,
            karaoke_disponible: actual.is_some_and(|s| s.karaoke),
            karaoke_activo: self.karaoke,
            dj: None,
            ciego: false,
        };
        self.instantanea_dj(&mut i);
        self.instantanea_fragmento(&mut i);
        i
    }

    fn publicar(&mut self) {
        let i = self.instantanea();
        if self.ultima.as_ref() != Some(&i) {
            self.oyente.instantanea(&i);
            self.ultima = Some(i);
        }
    }

    #[cfg(test)]
    fn motor(&mut self) -> &mut Motor<B> {
        &mut self.motor
    }
}

/// El hilo del servicio y su buzón. Es lo que guarda el estado de Tauri.
pub struct Reproductor {
    ordenes: Sender<Mensaje>,
    instantanea: Arc<RwLock<Option<Instantanea>>>,
}

/// Un buzón clonable del reproductor.
#[derive(Clone)]
pub struct Buzon(Sender<Mensaje>);

impl Buzon {
    pub fn enviar(&self, orden: Orden) {
        let _ = self.0.send(Mensaje::Orden(orden));
    }
}

enum Mensaje {
    Orden(Orden),
    Cerrar(Sender<()>),
}

/// Reenvía al oyente de verdad y se queda con la última instantánea para quien
/// la pida.
struct Guardian {
    interior: Box<dyn Oyente>,
    ultima: Arc<RwLock<Option<Instantanea>>>,
}

impl Oyente for Guardian {
    fn instantanea(&self, i: &Instantanea) {
        if let Ok(mut u) = self.ultima.write() {
            *u = Some(i.clone());
        }
        self.interior.instantanea(i);
    }

    fn aviso(&self, a: &AvisoReproductor) {
        self.interior.aviso(a);
    }
}

impl Reproductor {
    /// Arranca el hilo del reproductor con la salida de audio del sistema.
    ///
    /// # Errors
    ///
    /// [`NsError::ComponentUnavailable`] si no hay salida de audio;
    /// [`NsError::StorageFailure`] si no se puede leer la sesión.
    pub fn arrancar(
        db: BaseDeDatos,
        stems: PathBuf,
        oyente: Box<dyn Oyente>,
        equipo: crate::dj::equipo::Equipo,
    ) -> NsResult<Self> {
        let instantanea = Arc::new(RwLock::new(None));
        let guardian = Guardian {
            interior: oyente,
            ultima: Arc::clone(&instantanea),
        };
        let (tx, rx) = mpsc::channel::<Mensaje>();
        let (listo_tx, listo_rx) = mpsc::channel::<NsResult<()>>();
        std::thread::Builder::new()
            .name("reproductor".into())
            .spawn(move || {
                // El motor se crea en su hilo: el de Kira no es `Sync`, y así nunca
                // cruza entre hilos.
                let servicio = Motor::nuevo().and_then(|motor| {
                    Servicio::nuevo(motor, Cola::default(), db, stems, Box::new(guardian))
                        .map(|s| s.con_equipo(equipo))
                });
                match servicio {
                    Ok(s) => {
                        let _ = listo_tx.send(Ok(()));
                        bucle(s, &rx);
                    }
                    Err(e) => {
                        let _ = listo_tx.send(Err(e));
                    }
                }
            })
            .map_err(|_| NsError::Internal)?;
        listo_rx.recv().map_err(|_| NsError::Internal)??;
        Ok(Self {
            ordenes: tx,
            instantanea,
        })
    }

    pub fn enviar(&self, orden: Orden) {
        let _ = self.ordenes.send(Mensaje::Orden(orden));
    }

    /// Un buzón para mandar órdenes desde otro hilo.
    pub fn buzon(&self) -> Buzon {
        Buzon(self.ordenes.clone())
    }

    pub fn instantanea(&self) -> Option<Instantanea> {
        self.instantanea.read().ok().and_then(|i| i.clone())
    }

    /// Guarda la sesión, detiene el audio y espera a que el hilo lo confirme. Es la
    /// prueba de cierre de F2.1.6: cerrar no deja audio sonando.
    pub fn cerrar(&self) {
        let (tx, rx) = mpsc::channel();
        if self.ordenes.send(Mensaje::Cerrar(tx)).is_ok() {
            let _ = rx.recv_timeout(Duration::from_secs(2));
        }
    }
}

fn bucle<B: Backend>(mut s: Servicio<B>, rx: &Receiver<Mensaje>) {
    let mut ultima_vez = Instant::now();
    loop {
        match rx.recv_timeout(Duration::from_millis(40)) {
            Ok(Mensaje::Orden(o)) => s.atender(o),
            Ok(Mensaje::Cerrar(confirmar)) => {
                s.guardar_al_cerrar();
                let _ = confirmar.send(());
                return;
            }
            Err(RecvTimeoutError::Disconnected) => {
                s.guardar_al_cerrar();
                return;
            }
            Err(RecvTimeoutError::Timeout) => {}
        }
        s.atender_motor();
        // La posición se guarda cada pocos segundos, por si la aplicación muere sin
        // cerrarse: al volver, se pierde como mucho eso.
        if ultima_vez.elapsed() > Duration::from_secs(5) {
            s.guardar();
            ultima_vez = Instant::now();
        }
    }
}
