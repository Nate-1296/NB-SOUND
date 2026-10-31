//! El hilo que decodifica por delante de lo que suena.
//!
//! Mantiene llena una cola corta de bloques (alrededor de un segundo y medio) para
//! que la fuente nunca espere, y conoce la pista actual y la siguiente: cuando la
//! actual se acaba, sigue con la siguiente en el mismo flujo, sin hueco. Es lo
//! único del motor que toca el disco.

use std::path::PathBuf;
use std::sync::atomic::Ordering;
use std::sync::mpsc::{Receiver, RecvTimeoutError, Sender, SyncSender, TrySendError};
use std::sync::Arc;
use std::time::Duration;

use kira::Frame;

use super::decodificador::Decodificador;
use super::fuente::{Bloque, Compartido};
use super::EventoMotor;

/// Frames por bloque: unos 93 ms a 44,1 kHz.
pub const FRAMES_POR_BLOQUE: usize = 4096;

/// Lo que el motor le pide al alimentador.
#[derive(Debug, Clone, PartialEq)]
pub struct PistaEnCola {
    /// Ficha de la pista en la cola: la pone quien la encola y vuelve en los eventos.
    pub ficha: u64,
    pub ruta: PathBuf,
    /// El instrumental del karaoke, si lo hay; se lee a la par que el original.
    pub instrumental: Option<PathBuf>,
    /// Normalización de volumen (F2.1.4).
    pub ganancia_db: f32,
}

pub enum Orden {
    Reproducir {
        generacion: u64,
        pista: PistaEnCola,
        desde_seg: f64,
    },
    Siguiente(Option<PistaEnCola>),
    Buscar {
        generacion: u64,
        segundos: f64,
    },
    Detener {
        generacion: u64,
    },
    /// El instrumental de la pista que suena acaba de prepararse (F5.2.2): se abre
    /// y se lleva al mismo frame que el original, sin cortar lo que suena.
    Instrumental {
        ficha: u64,
        ruta: PathBuf,
    },
}

struct Abierta {
    pista: PistaEnCola,
    original: Decodificador,
    instrumental: Option<Decodificador>,
    frame: u64,
}

fn abrir(pista: PistaEnCola, eventos: &Sender<EventoMotor>) -> Option<Abierta> {
    let original = match Decodificador::abrir(&pista.ruta, pista.ganancia_db) {
        Ok(d) => d,
        Err(error) => {
            let _ = eventos.send(EventoMotor::PistaIlegible {
                ficha: pista.ficha,
                error,
            });
            return None;
        }
    };
    // Un instrumental que no se puede abrir no impide escuchar el original.
    let instrumental = pista.instrumental.as_ref().and_then(|ruta| {
        Decodificador::abrir(ruta, pista.ganancia_db)
            .ok()
            .filter(|i| i.tasa == original.tasa)
    });
    Some(Abierta {
        pista,
        original,
        instrumental,
        frame: 0,
    })
}

pub struct Alimentador {
    pub ordenes: Receiver<Orden>,
    pub bloques: SyncSender<Bloque>,
    pub devueltos: Receiver<Vec<Frame>>,
    pub compartido: Arc<Compartido>,
    pub eventos: Sender<EventoMotor>,
}

impl Alimentador {
    fn vector(&self) -> Vec<Frame> {
        let mut v = self
            .devueltos
            .try_recv()
            .unwrap_or_else(|_| Vec::with_capacity(FRAMES_POR_BLOQUE));
        v.clear();
        v
    }

    /// Lee el siguiente bloque de la pista abierta. `None` si se acabó.
    fn leer(&self, abierta: &mut Abierta, generacion: u64) -> Option<Bloque> {
        let mut original = self.vector();
        let leidos = match abierta.original.leer(&mut original, FRAMES_POR_BLOQUE) {
            Ok(n) => n,
            Err(error) => {
                let _ = self.eventos.send(EventoMotor::PistaIlegible {
                    ficha: abierta.pista.ficha,
                    error,
                });
                0
            }
        };
        if leidos == 0 {
            return None;
        }
        let instrumental = abierta.instrumental.as_mut().map(|d| {
            let mut v = self.vector();
            let _ = d.leer(&mut v, leidos);
            // El instrumental puede ser unos frames más corto: se rellena con
            // silencio para que los dos índices sigan siendo el mismo.
            v.resize(leidos, Frame::ZERO);
            v
        });
        let bloque = Bloque {
            generacion,
            pista: abierta.pista.ficha,
            frame_inicial: abierta.frame,
            tasa: abierta.original.tasa,
            original,
            instrumental,
            fin: false,
        };
        abierta.frame += leidos as u64;
        Some(bloque)
    }

    fn fin(generacion: u64) -> Bloque {
        Bloque {
            generacion,
            pista: 0,
            frame_inicial: 0,
            tasa: 0,
            original: Vec::new(),
            instrumental: None,
            fin: true,
        }
    }

    /// El bucle del hilo. Termina cuando el motor desaparece.
    pub fn correr(self) {
        let mut generacion = 0u64;
        let mut actual: Option<Abierta> = None;
        let mut siguiente: Option<PistaEnCola> = None;
        let mut pendiente: Option<Bloque> = None;
        let mut fin_enviado = true;

        loop {
            // Sin trabajo, se espera a una orden; con trabajo, solo se mira.
            let espera = if pendiente.is_some() || !fin_enviado {
                Duration::from_millis(5)
            } else {
                Duration::from_millis(200)
            };
            match self.ordenes.recv_timeout(espera) {
                Ok(orden) => {
                    match orden {
                        Orden::Reproducir {
                            generacion: g,
                            pista,
                            desde_seg,
                        } => {
                            generacion = g;
                            pendiente = None;
                            fin_enviado = false;
                            actual = abrir(pista, &self.eventos);
                            if let Some(a) = actual.as_mut() {
                                if desde_seg > 0.0 {
                                    a.frame = a.original.buscar(desde_seg).unwrap_or(0);
                                    if let Some(i) = a.instrumental.as_mut() {
                                        let _ = i.buscar(desde_seg);
                                    }
                                }
                            }
                        }
                        Orden::Siguiente(p) => siguiente = p,
                        Orden::Buscar {
                            generacion: g,
                            segundos,
                        } => {
                            generacion = g;
                            pendiente = None;
                            fin_enviado = false;
                            if let Some(a) = actual.as_mut() {
                                match a.original.buscar(segundos) {
                                    Ok(frame) => a.frame = frame,
                                    Err(error) => {
                                        let _ = self.eventos.send(EventoMotor::PistaIlegible {
                                            ficha: a.pista.ficha,
                                            error,
                                        });
                                    }
                                }
                                if let Some(i) = a.instrumental.as_mut() {
                                    let _ = i.buscar(segundos);
                                }
                            }
                        }
                        Orden::Instrumental { ficha, ruta } => {
                            if let Some(a) = actual
                                .as_mut()
                                .filter(|a| a.pista.ficha == ficha && a.instrumental.is_none())
                            {
                                a.instrumental = Decodificador::abrir(&ruta, a.pista.ganancia_db)
                                    .ok()
                                    .filter(|i| i.tasa == a.original.tasa)
                                    .and_then(|mut i| i.buscar_frame(a.frame).ok().map(|_| i));
                                a.pista.instrumental = Some(ruta);
                            }
                        }
                        Orden::Detener { generacion: g } => {
                            generacion = g;
                            actual = None;
                            siguiente = None;
                            pendiente = None;
                            fin_enviado = true;
                        }
                    }
                    continue;
                }
                Err(RecvTimeoutError::Disconnected) => return,
                Err(RecvTimeoutError::Timeout) => {}
            }

            if pendiente.is_none() {
                pendiente = match actual.as_mut().and_then(|a| self.leer(a, generacion)) {
                    Some(b) => Some(b),
                    None => {
                        // La actual se acabó: sin hueco, la siguiente.
                        actual = None;
                        let mut bloque = None;
                        while let Some(p) = siguiente.take() {
                            if let Some(mut a) = abrir(p, &self.eventos) {
                                bloque = self.leer(&mut a, generacion);
                                actual = Some(a);
                                if bloque.is_some() {
                                    break;
                                }
                            }
                        }
                        match bloque {
                            Some(b) => Some(b),
                            None if !fin_enviado => {
                                fin_enviado = true;
                                Some(Self::fin(generacion))
                            }
                            None => None,
                        }
                    }
                };
            }
            if let Some(b) = pendiente.take() {
                let g = b.generacion;
                self.compartido.en_cola.fetch_add(1, Ordering::AcqRel);
                match self.bloques.try_send(b) {
                    Ok(()) => self.compartido.entregada.store(g, Ordering::Release),
                    Err(TrySendError::Full(b)) => {
                        self.compartido.en_cola.fetch_sub(1, Ordering::AcqRel);
                        pendiente = Some(b);
                    }
                    Err(TrySendError::Disconnected(_)) => return,
                }
            }
        }
    }
}
