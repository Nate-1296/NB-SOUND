//! La sesión del DJ en el reproductor (F6.1.6): `reproductor_sesion.py` de la V1.
//!
//! La V1 tenía un reproductor propio para el DJ, con dos decks de VLC, y un gestor
//! que pausaba el reproductor normal mientras sonaba. En la V2 hay un solo motor y
//! una sola barra: el DJ es un modo del servicio de reproducción. Mientras dura, la
//! cola del usuario queda en pausa donde estaba, y el servicio toca las pistas de la
//! sesión y dirige cada mezcla desde su bucle: cuando la que suena llega a su punto
//! de salida, arma la siguiente con la técnica que decide `dj::mezcla` y la lleva
//! con `dj::ejecutor`. Al acabar la sesión, o al pedir otra cosa, la cola vuelve tal
//! como estaba, en pausa.
//!
//! La sesión que sonaba se recuerda en `dj_en_curso` y vuelve en pausa al abrir la
//! aplicación, como en la V1.

use std::collections::HashSet;
use std::time::Instant;

use serde::Serialize;
use ts_rs::TS;

use super::{Servicio, Sonando};
use crate::audio::PistaEnCola;
use crate::cola::{Estado, Fila};
use crate::dj::ejecutor::{Ejecutor, Paso};
use crate::dj::mezcla::{self, Lado, Plan, Tecnica};
use crate::dj::sesiones::{self, EnCurso, Evento};
use crate::dj::transiciones::Transicion;
use crate::dj::{narrativa, suma};
use crate::error::{NsError, NsResult};

/// Lo que el DJ le pide al reproductor.
#[derive(Debug, Clone, PartialEq)]
pub enum OrdenDj {
    /// Toca una sesión desde la pista en `posicion` (la de la sesión).
    Reproducir {
        sesion: i64,
        posicion: u32,
        desde_seg: f64,
    },
    /// La sesión creció (un bloque nuevo): se vuelven a leer sus pistas.
    Recargar(i64),
    /// Deja la sesión: vuelve la cola, en pausa.
    Salir,
}

/// Lo que la barra y la vista del DJ saben de la sesión que suena.
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct EstadoDj {
    #[ts(type = "number")]
    pub sesion_id: i64,
    /// La posición en la sesión de la pista que suena.
    pub posicion: u32,
    pub total: u32,
    pub mezcla: Option<MezclaVisible>,
}

/// La mezcla en curso: con qué técnica y cuánto lleva, en pasos de un 5 % para no
/// publicar una instantánea por cada paso del ejecutor.
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct MezclaVisible {
    pub tecnica: Tecnica,
    pub progreso: f32,
}

#[derive(Debug, Clone)]
struct PistaDj {
    posicion: u32,
    pista_id: i64,
    duracion_seg: f64,
    bpm: Option<f64>,
    /// La transición que la trae, como la planificó el constructor.
    transicion: Transicion,
}

/// La mezcla que viene, preparada al empezar cada pista: la técnica fija el
/// solapamiento y, con él, el punto de salida.
struct Proxima {
    desde: usize,
    plan: Plan,
    indice: usize,
    pista: PistaEnCola,
    sonando: Sonando,
}

struct Mezcla {
    ejecutor: Ejecutor,
    indice: usize,
    sonando: Sonando,
    tecnica: Tecnica,
    progreso: f32,
}

pub(super) struct ModoDj {
    sesion: i64,
    pistas: Vec<PistaDj>,
    perfil: Vec<narrativa::Fase>,
    indice: usize,
    sonando: Option<Sonando>,
    pausado: bool,
    proxima: Option<Proxima>,
    mezcla: Option<Mezcla>,
    /// Las que no se pudieron abrir: no se vuelven a intentar en esta sesión.
    ilegibles: HashSet<usize>,
    /// Dónde estaba la cola del usuario al entrar.
    cola_seg: f64,
}

impl ModoDj {
    fn siguiente(&self, desde: usize) -> Option<usize> {
        (desde + 1..self.pistas.len()).find(|i| !self.ilegibles.contains(i))
    }

    /// `_fase_narrativa_actual_locked`: la fase al acabar la pista `indice`.
    fn fase(&self, indice: usize) -> &'static str {
        let total = suma(self.pistas.iter().map(|p| p.duracion_seg));
        if self.perfil.is_empty() || total <= 0.0 {
            return "groove";
        }
        let hecho = suma(self.pistas[..=indice].iter().map(|p| p.duracion_seg));
        let t = (hecho / total).clamp(0.0, 1.0);
        self.perfil[narrativa::fase_en(&self.perfil, t)].nombre
    }
}

fn cargar(
    db: &crate::db::BaseDeDatos,
    sesion: i64,
) -> NsResult<(Vec<PistaDj>, Vec<narrativa::Fase>)> {
    let s = sesiones::una(db, sesion)?.ok_or(NsError::InvalidInput)?;
    let intencion: crate::dj::intencion::Intencion =
        serde_json::from_str(&s.intencion).unwrap_or_default();
    let conn = db.conexion()?;
    let mut q = conn
        .prepare(
            "SELECT s.posicion, s.pista_id, COALESCE(p.duracion_seg, 0), r.bpm, s.transicion
             FROM dj_sesion_pistas s JOIN pistas p ON p.id = s.pista_id
             LEFT JOIN rasgos r ON r.pista_id = s.pista_id
             WHERE s.sesion_id = ?1 ORDER BY s.posicion",
        )
        .map_err(|_| NsError::StorageFailure)?;
    let pistas = q
        .query_map([sesion], |f| {
            let t: String = f.get(4)?;
            Ok(PistaDj {
                posicion: f.get(0)?,
                pista_id: f.get(1)?,
                duracion_seg: f.get(2)?,
                bpm: f.get(3)?,
                transicion: Transicion::desde_json(&serde_json::from_str(&t).unwrap_or_default()),
            })
        })
        .map_err(|_| NsError::StorageFailure)?
        .collect::<rusqlite::Result<Vec<_>>>()
        .map_err(|_| NsError::StorageFailure)?;
    Ok((pistas, narrativa::perfil(&intencion)))
}

impl<B: kira::backend::Backend> Servicio<B> {
    pub(super) fn atender_dj(&mut self, orden: OrdenDj) {
        match orden {
            OrdenDj::Reproducir {
                sesion,
                posicion,
                desde_seg,
            } => {
                if let Err(e) = self.entrar_dj(sesion, posicion, desde_seg, false) {
                    self.avisar(e, None);
                }
            }
            OrdenDj::Recargar(sesion) => {
                if self.dj.as_ref().is_some_and(|d| d.sesion == sesion) {
                    self.recargar_dj();
                }
            }
            OrdenDj::Salir => self.salir_dj(),
        }
    }

    /// Entra en una sesión. `pausado` deja la pista lista sin sonar: así vuelve la
    /// sesión que sonaba al cerrar.
    pub(super) fn entrar_dj(
        &mut self,
        sesion: i64,
        posicion: u32,
        desde_seg: f64,
        pausado: bool,
    ) -> NsResult<()> {
        let (pistas, perfil) = cargar(&self.db, sesion)?;
        let indice = pistas
            .iter()
            .position(|p| p.posicion == posicion)
            .unwrap_or(0);
        if pistas.is_empty() {
            return Err(NsError::InvalidInput);
        }
        let cola_seg = match self.dj.take() {
            Some(d) => d.cola_seg,
            None => {
                let pos = self.motor.posicion();
                let segundos = if self.actual.as_ref().is_some_and(|s| s.ficha == pos.ficha) {
                    pos.segundos
                } else {
                    self.cola_seg_restaurada
                };
                if self.cola.estado() == Estado::Reproduciendo {
                    let _ = self.cola.pausar_reanudar();
                }
                segundos
            }
        };
        self.motor.detener();
        self.actual = None;
        self.prevista = None;
        self.karaoke = false;
        self.dj = Some(ModoDj {
            sesion,
            pistas,
            perfil,
            indice,
            sonando: None,
            pausado,
            proxima: None,
            mezcla: None,
            ilegibles: HashSet::new(),
            cola_seg,
        });
        self.tocar_dj(indice, desde_seg);
        if pausado {
            self.motor.pausar();
        }
        Ok(())
    }

    /// Toca la pista `indice` desde `desde_seg`; si no se puede abrir, la siguiente.
    fn tocar_dj(&mut self, mut indice: usize, desde_seg: f64) {
        let mut desde = desde_seg;
        loop {
            let Some(d) = self.dj.as_ref() else {
                return;
            };
            let Some(p) = d.pistas.get(indice).cloned() else {
                self.terminar_dj();
                return;
            };
            if let Some((pista, sonando)) = self.resolver(Fila {
                pista_id: p.pista_id,
            }) {
                self.motor.reproducir(pista, desde);
                self.motor.siguiente(None);
                let d = self.dj.as_mut().expect("modo DJ");
                d.indice = indice;
                d.sonando = Some(sonando);
                return;
            }
            self.avisar(NsError::FileNotFound, Some(p.pista_id));
            let d = self.dj.as_mut().expect("modo DJ");
            d.ilegibles.insert(indice);
            match d.siguiente(indice) {
                Some(i) => {
                    indice = i;
                    desde = 0.0;
                }
                None => {
                    self.terminar_dj();
                    return;
                }
            }
        }
    }

    fn recargar_dj(&mut self) {
        let Some(sesion) = self.dj.as_ref().map(|d| d.sesion) else {
            return;
        };
        let Ok((pistas, perfil)) = cargar(&self.db, sesion) else {
            return;
        };
        let d = self.dj.as_mut().expect("modo DJ");
        let posicion = d.pistas.get(d.indice).map(|p| p.posicion);
        let posicion_b = d.mezcla.as_ref().map(|m| d.pistas[m.indice].posicion);
        let indice = |posicion: Option<u32>| {
            posicion.and_then(|x| pistas.iter().position(|p| p.posicion == x))
        };
        if let Some(i) = indice(posicion) {
            d.indice = i;
        }
        if let (Some(m), Some(i)) = (d.mezcla.as_mut(), indice(posicion_b)) {
            m.indice = i;
        }
        d.pistas = pistas;
        d.perfil = perfil;
    }

    /// La sesión acabó de sonar: queda finalizada y vuelve la cola.
    fn terminar_dj(&mut self) {
        if let Some(d) = &self.dj {
            if let Some(p) = d.pistas.get(d.indice) {
                let _ = sesiones::registrar(
                    &self.db,
                    d.sesion,
                    Some(p.posicion),
                    Some(p.pista_id),
                    Evento::Reproducida,
                    &serde_json::json!({}),
                );
            }
            let _ = sesiones::cambiar_estado(&self.db, d.sesion, "finalizada", true);
        }
        self.salir_dj();
    }

    /// Deja el modo DJ: la cola del usuario vuelve en pausa donde estaba.
    pub(super) fn salir_dj(&mut self) {
        let Some(d) = self.dj.take() else {
            return;
        };
        self.motor.detener();
        let _ = sesiones::guardar_en_curso(&self.db, None);
        self.actual = None;
        self.prevista = None;
        if self.cola.estado() == Estado::Reproduciendo {
            let _ = self.cola.pausar_reanudar();
        }
        // En pausa, "reanudar" sigue desde donde estaba: se deja cargada. Detenida,
        // empezará de cero por su cuenta.
        if self.cola.estado() == Estado::Pausado {
            if let Some((pista, sonando)) = self.cola.activa().and_then(|f| self.resolver(f)) {
                self.motor.reproducir(pista, d.cola_seg);
                self.motor.pausar();
                self.actual = Some(sonando);
            }
        }
    }

    /// Lo que la barra pide con una sesión sonando. Devuelve si lo atendió; lo
    /// demás (volumen, ecualizador, la cola) sigue su camino normal, y pedir que
    /// suene otra cosa deja antes la sesión.
    pub(super) fn interceptar_dj(&mut self, orden: &super::Orden) -> bool {
        use super::Orden as O;
        let Some(d) = self.dj.as_mut() else {
            return false;
        };
        match orden {
            O::PausarReanudar => {
                d.pausado = !d.pausado;
                if d.pausado {
                    self.motor.pausar();
                } else {
                    self.motor.reanudar();
                }
                true
            }
            O::Siguiente => {
                // Saltar: la pista cuenta como saltada y la mezcla empieza ya.
                if d.mezcla.is_none() {
                    if let Some(p) = d.pistas.get(d.indice) {
                        let _ = sesiones::registrar(
                            &self.db,
                            d.sesion,
                            Some(p.posicion),
                            Some(p.pista_id),
                            Evento::Saltada,
                            &serde_json::json!({}),
                        );
                    }
                    self.armar_mezcla();
                }
                true
            }
            O::Anterior => {
                let previa = d.indice.checked_sub(1);
                if let Some(m) = d.mezcla.as_mut() {
                    m.ejecutor.cancelar(&mut self.motor);
                }
                let d = self.dj.as_mut().expect("modo DJ");
                d.mezcla = None;
                let i = previa.unwrap_or(d.indice);
                self.tocar_dj(i, 0.0);
                true
            }
            O::Buscar(segundos) => {
                if let Some(mut m) = d.mezcla.take() {
                    m.ejecutor.cancelar(&mut self.motor);
                }
                let d = self.dj.as_ref().expect("modo DJ");
                let duracion = d.pistas.get(d.indice).map_or(0.0, |p| p.duracion_seg);
                if duracion > 0.0 {
                    self.motor.buscar(segundos.clamp(0.0, duracion));
                }
                true
            }
            // El micrófono no se usa en una sesión: la mezcla ya maneja el
            // instrumental de la que entra.
            O::Karaoke(_) | O::InstrumentalListo(_) => true,
            O::ReproducirPistas { .. } | O::ReproducirPista(_) | O::ReproducirIndice(_) => {
                self.salir_dj();
                false
            }
            _ => false,
        }
    }

    /// El plan de la mezcla de la que suena a la siguiente, con la siguiente ya
    /// resuelta para el motor. `None` si no queda ninguna que se pueda abrir.
    fn proxima_dj(&mut self) -> Option<Proxima> {
        loop {
            let d = self.dj.as_ref()?;
            let b = d.siguiente(d.indice)?;
            let (pa, pb) = (d.pistas[d.indice].clone(), d.pistas[b].clone());
            let (desde, fase) = (d.indice, d.fase(d.indice));
            let Some((pista, sonando)) = self.resolver(Fila {
                pista_id: pb.pista_id,
            }) else {
                self.avisar(NsError::FileNotFound, Some(pb.pista_id));
                self.dj.as_mut()?.ilegibles.insert(b);
                continue;
            };
            let plan = mezcla::preparar(
                &pb.transicion,
                self.equipo.perfil(),
                fase,
                Lado {
                    duracion_seg: pa.duracion_seg,
                    bpm: pa.bpm,
                },
                Lado {
                    duracion_seg: pb.duracion_seg,
                    bpm: pb.bpm,
                },
                pista.instrumental.is_some(),
            );
            return Some(Proxima {
                desde,
                plan,
                indice: b,
                pista,
                sonando,
            });
        }
    }

    /// Arma la mezcla hacia la siguiente, ya.
    fn armar_mezcla(&mut self) {
        let proxima = match self.dj.as_mut().and_then(|d| d.proxima.take()) {
            Some(p) if self.dj.as_ref().is_some_and(|d| d.indice == p.desde) => Some(p),
            _ => self.proxima_dj(),
        };
        let Some(p) = proxima else {
            return;
        };
        let tecnica = p.plan.tecnica;
        let ejecutor = Ejecutor::armar(&mut self.motor, p.plan, p.pista, Instant::now());
        if let Some(d) = self.dj.as_mut() {
            d.mezcla = Some(Mezcla {
                ejecutor,
                indice: p.indice,
                sonando: p.sonando,
                tecnica,
                progreso: 0.0,
            });
        }
    }

    /// Un paso del DJ: se llama en cada vuelta del bucle del servicio. Devuelve si
    /// cambió algo que la interfaz deba ver.
    pub(super) fn tic_dj(&mut self) -> bool {
        let Some(d) = self.dj.as_mut() else {
            return false;
        };
        if let Some(m) = d.mezcla.as_mut() {
            match m.ejecutor.tic(&mut self.motor, Instant::now()) {
                Paso::Terminada => {
                    let m = d.mezcla.take().expect("hay mezcla");
                    let anterior = d.pistas.get(d.indice).cloned();
                    d.indice = m.indice;
                    d.sonando = Some(m.sonando);
                    if let Some(p) = anterior {
                        let _ = sesiones::registrar(
                            &self.db,
                            d.sesion,
                            Some(p.posicion),
                            Some(p.pista_id),
                            Evento::Reproducida,
                            &serde_json::json!({}),
                        );
                    }
                    return true;
                }
                Paso::Mezclando(p) => {
                    let visible = ((p * 20.0).floor() / 20.0) as f32;
                    let cambio = visible != m.progreso;
                    m.progreso = visible;
                    return cambio;
                }
                Paso::Esperando => return false,
            }
        }
        if d.pausado {
            return false;
        }
        let pos = self.motor.posicion();
        if d.sonando.as_ref().is_none_or(|s| s.ficha != pos.ficha) {
            return false;
        }
        if d.proxima.as_ref().is_none_or(|p| p.desde != d.indice) {
            let proxima = self.proxima_dj();
            match self.dj.as_mut() {
                Some(d) => d.proxima = proxima,
                None => return false,
            }
        }
        let salida = self
            .dj
            .as_ref()
            .and_then(|d| d.proxima.as_ref())
            .map(|p| p.plan.salida_a_seg);
        if salida.is_some_and(|s| pos.segundos >= s) {
            self.armar_mezcla();
            return true;
        }
        false
    }

    /// Los eventos del motor con una sesión sonando.
    pub(super) fn eventos_dj(&mut self, eventos: Vec<crate::audio::EventoMotor>) {
        use crate::audio::EventoMotor as E;
        for evento in eventos {
            match evento {
                // La entrante se anuncia al acabar la mezcla, y eso ya lo sabe el DJ.
                E::PistaEmpieza { .. } => {}
                E::ColaTerminada => {
                    if self.dj.as_ref().is_some_and(|d| d.mezcla.is_none()) {
                        self.terminar_dj();
                    }
                }
                E::PistaIlegible { ficha, error } => {
                    let Some(d) = self.dj.as_mut() else {
                        continue;
                    };
                    let pista = self.fichas.get(&ficha).map(|s| s.fila.pista_id);
                    if d.mezcla.as_ref().is_some_and(|m| m.sonando.ficha == ficha) {
                        let mut m = d.mezcla.take().expect("hay mezcla");
                        m.ejecutor.cancelar(&mut self.motor);
                        d.ilegibles.insert(m.indice);
                    } else if d.sonando.as_ref().is_some_and(|s| s.ficha == ficha) {
                        d.ilegibles.insert(d.indice);
                        if let Some(i) = d.siguiente(d.indice) {
                            self.tocar_dj(i, 0.0);
                        } else {
                            self.terminar_dj();
                        }
                    }
                    self.avisar(error, pista);
                }
            }
        }
    }

    /// Lo que el DJ pone en la instantánea: la pista, su posición y el estado.
    pub(super) fn instantanea_dj(&self, i: &mut super::Instantanea) {
        let Some(d) = &self.dj else {
            return;
        };
        let pos = self.motor.posicion();
        let p = d.pistas.get(d.indice);
        i.pista_id = p.map(|p| p.pista_id);
        i.duracion_seg = p.map_or(0.0, |p| p.duracion_seg);
        i.posicion_seg = if d.sonando.as_ref().is_some_and(|s| s.ficha == pos.ficha) {
            pos.segundos
        } else {
            0.0
        };
        i.estado = if d.pausado {
            "pausado"
        } else {
            "reproduciendo"
        }
        .to_owned();
        i.karaoke_disponible = false;
        i.karaoke_activo = false;
        i.dj = Some(EstadoDj {
            sesion_id: d.sesion,
            posicion: p.map_or(0, |p| p.posicion),
            total: d.pistas.len() as u32,
            mezcla: d.mezcla.as_ref().map(|m| MezclaVisible {
                tecnica: m.tecnica,
                progreso: m.progreso,
            }),
        });
    }

    /// Dónde va la sesión, para volver a ella al abrir.
    pub(super) fn guardar_dj(&self) -> Option<f64> {
        let d = self.dj.as_ref()?;
        let pos = self.motor.posicion();
        let p = d.pistas.get(d.indice)?;
        let segundos = if d.sonando.as_ref().is_some_and(|s| s.ficha == pos.ficha) {
            pos.segundos
        } else {
            0.0
        };
        let global = suma(d.pistas[..d.indice].iter().map(|p| p.duracion_seg)) + segundos;
        let _ = sesiones::guardar_en_curso(
            &self.db,
            Some(&EnCurso {
                sesion: d.sesion,
                posicion: p.posicion,
                segundos,
                segundos_global: global,
                volumen: f64::from(self.volumen),
            }),
        );
        Some(d.cola_seg)
    }

    /// Al abrir: la sesión que sonaba, en pausa, si sigue viva.
    pub(super) fn restaurar_dj(&mut self) {
        let Ok(Some(e)) = sesiones::en_curso(&self.db) else {
            return;
        };
        let viva = sesiones::una(&self.db, e.sesion)
            .ok()
            .flatten()
            .is_some_and(|s| s.estado == "lista" || s.estado == "construyendo");
        if !viva
            || self
                .entrar_dj(e.sesion, e.posicion, e.segundos, true)
                .is_err()
        {
            let _ = sesiones::guardar_en_curso(&self.db, None);
        }
    }

    pub(super) const fn en_dj(&self) -> bool {
        self.dj.is_some()
    }
}
