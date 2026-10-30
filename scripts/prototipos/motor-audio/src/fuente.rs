//! Una fuente propia para Kira: la cola de reproducción.
//!
//! Kira se queda con lo que hace bien (pistas de mezcla, efectos, transiciones y
//! la salida por cpal) y la fuente la ponemos nosotros, porque es lo que decide la
//! exactitud:
//!
//! * **Sin cortes por construcción**: la cola entrega los frames de una pista y,
//!   en el mismo bloque, los de la siguiente. No hay dos sonidos que coordinar.
//! * **Karaoke sin deriva por construcción**: el original y el instrumental son
//!   dos lecturas del mismo índice; no pueden separarse ni una muestra.
//! * **Sin interpolación**: el índice es entero. A la tasa nativa, la salida es la
//!   entrada muestra a muestra.

use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::Arc;

use kira::info::Info;
use kira::sound::{Sound, SoundData};
use kira::Frame;

pub struct Pista {
    pub original: Arc<[Frame]>,
    pub instrumental: Option<Arc<[Frame]>>,
}

/// Control compartido con el hilo de la interfaz.
pub struct Control {
    /// 0 = original, 1 = instrumental, en bits de `f32`.
    mezcla_objetivo: AtomicU32,
}

impl Control {
    pub fn karaoke(&self, activo: bool) {
        let v: f32 = if activo { 1.0 } else { 0.0 };
        self.mezcla_objetivo.store(v.to_bits(), Ordering::Relaxed);
    }
}

pub struct Cola {
    pub pistas: Vec<Pista>,
    /// Duración de la transición de karaoke, en frames.
    pub rampa: u32,
}

impl SoundData for Cola {
    type Error = ();
    type Handle = Arc<Control>;

    fn into_sound(self) -> Result<(Box<dyn Sound>, Self::Handle), ()> {
        let control = Arc::new(Control {
            mezcla_objetivo: AtomicU32::new(0f32.to_bits()),
        });
        Ok((
            Box::new(FuenteCola {
                pistas: self.pistas,
                actual: 0,
                pos: 0,
                mezcla: 0.0,
                paso: 1.0 / self.rampa.max(1) as f32,
                control: control.clone(),
            }),
            control,
        ))
    }
}

struct FuenteCola {
    pistas: Vec<Pista>,
    actual: usize,
    pos: usize,
    mezcla: f32,
    paso: f32,
    control: Arc<Control>,
}

impl Sound for FuenteCola {
    fn process(&mut self, out: &mut [Frame], _dt: f64, _info: &Info) {
        let objetivo = f32::from_bits(self.control.mezcla_objetivo.load(Ordering::Relaxed));
        for frame in out.iter_mut() {
            // Pasa a la siguiente pista en el mismo frame en que acaba la anterior.
            while let Some(p) = self.pistas.get(self.actual) {
                if self.pos < p.original.len() {
                    break;
                }
                self.actual += 1;
                self.pos = 0;
            }
            let Some(pista) = self.pistas.get(self.actual) else {
                *frame = Frame::ZERO;
                continue;
            };
            if self.mezcla < objetivo {
                self.mezcla = (self.mezcla + self.paso).min(objetivo);
            } else if self.mezcla > objetivo {
                self.mezcla = (self.mezcla - self.paso).max(objetivo);
            }
            let o = pista.original[self.pos];
            *frame = match &pista.instrumental {
                Some(inst) if self.mezcla > 0.0 => {
                    let i = inst.get(self.pos).copied().unwrap_or(Frame::ZERO);
                    o * (1.0 - self.mezcla) + i * self.mezcla
                }
                _ => o,
            };
            self.pos += 1;
        }
    }

    fn finished(&self) -> bool {
        self.actual >= self.pistas.len()
    }
}
