//! El fragmento a ciegas (F6.2.2): unos segundos de una canción sin decir cuál es.
//!
//! A ciegas toca un trozo de la canción del reto por el reproductor de siempre. La
//! V1 tapaba los datos de la barra con "???"; aquí la instantánea no lleva la pista
//! mientras suena el fragmento (`ciego`), así que nada en la barra, en los controles
//! del sistema ni en el móvil la delata. La cola del usuario espera en pausa, como
//! con el DJ, y vuelve al acabar el fragmento o al pedir cualquier otra cosa.

use std::time::{Duration, Instant};

use super::{Orden, Servicio, Sonando};
use crate::cola::{Estado, Fila};
use crate::error::NsError;

/// Lo que tarda el fundido de la pausa del motor, con margen, antes de cargar lo
/// que vuelve: así lo que vuelve no suena ni un instante.
const FUNDIDO: Duration = Duration::from_millis(60);

pub(super) struct Fragmento {
    sonando: Sonando,
    desde: f64,
    hasta: f64,
    cola_seg: f64,
    /// Ya se pidió la pausa: se espera al fundido para devolver la cola.
    acabando: Option<Instant>,
}

impl<B: kira::backend::Backend> Servicio<B> {
    /// Toca `segundos` de la pista desde `desde_seg`.
    pub(super) fn tocar_fragmento(&mut self, pista_id: i64, desde_seg: f64, segundos: f64) {
        let cola_seg = match self.fragmento.take() {
            Some(f) => f.cola_seg,
            None => {
                self.salir_dj();
                let pos = self.motor.posicion();
                let s = if self.actual.as_ref().is_some_and(|s| s.ficha == pos.ficha) {
                    pos.segundos
                } else {
                    self.cola_seg_restaurada
                };
                if self.cola.estado() == Estado::Reproduciendo {
                    let _ = self.cola.pausar_reanudar();
                }
                s
            }
        };
        self.actual = None;
        self.prevista = None;
        self.karaoke = false;
        let Some((pista, sonando)) = self.resolver(Fila { pista_id }) else {
            self.avisar(NsError::FileNotFound, None);
            self.cola_seg_restaurada = cola_seg;
            return;
        };
        self.motor.reproducir(pista, desde_seg);
        self.motor.siguiente(None);
        self.fragmento = Some(Fragmento {
            sonando,
            desde: desde_seg,
            hasta: desde_seg + segundos.max(0.0),
            cola_seg,
            acabando: None,
        });
    }

    /// Empieza a callar el fragmento; [`Self::tic_fragmento`] devuelve la cola
    /// cuando el fundido acaba.
    fn acabar_fragmento(&mut self) {
        if let Some(f) = self.fragmento.as_mut() {
            if f.acabando.is_none() {
                self.motor.pausar();
                f.acabando = Some(Instant::now());
            }
        }
    }

    /// Devuelve la cola ya, sin esperar al fundido: antes de que suene otra cosa.
    pub(super) fn cortar_fragmento(&mut self) {
        if let Some(f) = self.fragmento.take() {
            self.motor.detener();
            self.devolver_cola(f.cola_seg);
        }
    }

    /// Un paso del fragmento: lo acaba al llegar a su final. Devuelve si cambió
    /// algo que la interfaz deba ver.
    pub(super) fn tic_fragmento(&mut self, terminada: bool) -> bool {
        let Some(f) = self.fragmento.as_ref() else {
            return false;
        };
        if let Some(t) = f.acabando {
            if t.elapsed() >= FUNDIDO {
                self.cortar_fragmento();
                return true;
            }
            return false;
        }
        let pos = self.motor.posicion();
        let llego = pos.ficha == f.sonando.ficha && pos.segundos >= f.hasta;
        if llego || terminada {
            self.acabar_fragmento();
            return true;
        }
        false
    }

    /// Lo que la barra pide durante un fragmento. Pausar lo acaba; lo que mueve la
    /// cola la devuelve antes; el resto no hace nada que delate la canción.
    pub(super) fn interceptar_fragmento(&mut self, orden: &Orden) -> bool {
        if self.fragmento.is_none() {
            return false;
        }
        match orden {
            Orden::PausarReanudar => {
                self.acabar_fragmento();
                true
            }
            Orden::Siguiente | Orden::Anterior | Orden::Buscar(_) | Orden::Karaoke(_) => true,
            Orden::Fragmento { .. } | Orden::Volumen(_) | Orden::Ecualizador(_) => false,
            _ => {
                self.cortar_fragmento();
                false
            }
        }
    }

    pub(super) fn instantanea_fragmento(&self, i: &mut super::Instantanea) {
        let Some(f) = &self.fragmento else {
            return;
        };
        let pos = self.motor.posicion();
        i.pista_id = None;
        i.ciego = true;
        i.estado = if f.acabando.is_some() {
            "pausado"
        } else {
            "reproduciendo"
        }
        .to_owned();
        i.duracion_seg = f.hasta - f.desde;
        i.posicion_seg = if pos.ficha == f.sonando.ficha {
            (pos.segundos - f.desde).clamp(0.0, i.duracion_seg)
        } else {
            0.0
        };
        i.karaoke_disponible = false;
        i.karaoke_activo = false;
    }

    pub(super) fn cola_seg_fragmento(&self) -> Option<f64> {
        self.fragmento.as_ref().map(|f| f.cola_seg)
    }

    /// La cola del usuario vuelve en pausa donde estaba: cargada pero callada, para
    /// que "reanudar" siga desde ahí. Detenida, empezará de cero por su cuenta.
    pub(super) fn devolver_cola(&mut self, cola_seg: f64) {
        self.actual = None;
        self.prevista = None;
        if self.cola.estado() == Estado::Reproduciendo {
            let _ = self.cola.pausar_reanudar();
        }
        if self.cola.estado() == Estado::Pausado {
            if let Some((pista, sonando)) = self.cola.activa().and_then(|f| self.resolver(f)) {
                self.motor.pausar();
                self.motor.preparar(pista, cola_seg);
                self.actual = Some(sonando);
            }
        }
        self.cola_seg_restaurada = cola_seg;
    }
}
