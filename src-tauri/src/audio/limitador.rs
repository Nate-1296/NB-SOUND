//! Limitador suave de pico, el último efecto antes de la salida (ADR-003).
//!
//! Kira recorta en seco a ±1,0, y los MP3 del corpus llegan a 1,104 al
//! decodificarse (F0.4.1). Por debajo del umbral la señal pasa intacta, bit a bit;
//! por encima se curva con una tangente hiperbólica que se acerca a 1,0 sin
//! alcanzarlo, así que el recorte de Kira no actúa nunca. Es una saturación suave
//! y no un limitador con envolvente: no añade latencia, y con la normalización de
//! F2.1.4 activa casi nunca trabaja.

use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::Arc;

use kira::effect::{Effect, EffectBuilder};
use kira::info::Info;
use kira::Frame;

/// −1 dBFS.
pub const UMBRAL: f32 = 0.891;
/// A lo que tiende la curva. Por debajo de 1,0 con margen: en `f32` la tangente
/// hiperbólica vale 1,0 exacto a partir de 9, y la salida no puede tocar el techo.
const TECHO: f32 = 0.999;

/// La curva sobre una muestra.
pub fn limitar(x: f32) -> f32 {
    let a = x.abs();
    if a <= UMBRAL {
        return x;
    }
    let resto = TECHO - UMBRAL;
    (UMBRAL + resto * ((a - UMBRAL) / resto).tanh()).copysign(x)
}

/// De paso, el limitador apunta la tasa de la salida en `tasa`: Kira no la expone
/// y el ecualizador la necesita para corregir sus ganancias. Kira se la da a cada
/// efecto al arrancar y cada vez que cambia de dispositivo.
pub struct Limitador {
    pub tasa: Arc<AtomicU32>,
}

impl EffectBuilder for Limitador {
    type Handle = ();

    fn build(self) -> (Box<dyn Effect>, ()) {
        (Box::new(Efecto { tasa: self.tasa }), ())
    }
}

struct Efecto {
    tasa: Arc<AtomicU32>,
}

impl Effect for Efecto {
    fn init(&mut self, sample_rate: u32, _internal_buffer_size: usize) {
        self.tasa.store(sample_rate, Ordering::Relaxed);
    }

    fn on_change_sample_rate(&mut self, sample_rate: u32) {
        self.tasa.store(sample_rate, Ordering::Relaxed);
    }

    fn process(&mut self, input: &mut [Frame], _dt: f64, _info: &Info) {
        for frame in input {
            frame.left = limitar(frame.left);
            frame.right = limitar(frame.right);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn por_debajo_del_umbral_no_cambia_nada() {
        for x in [0.0, 0.1, -0.5, 0.891, -0.891] {
            assert_eq!(limitar(x).to_bits(), x.to_bits());
        }
    }

    #[test]
    fn por_encima_nunca_llega_a_1_y_conserva_el_signo() {
        for x in [0.9, 1.0, 1.104, 2.0, 10.0] {
            let y = limitar(x);
            assert!(y > UMBRAL && y < 1.0, "{x} -> {y}");
            assert_eq!(limitar(-x), -y);
        }
    }

    #[test]
    fn la_curva_es_continua_y_creciente() {
        let mut previo = 0.0;
        for i in 0..2000 {
            let y = limitar(i as f32 / 1000.0);
            assert!(y >= previo);
            assert!(y - previo <= 0.001 + f32::EPSILON, "sin saltos en {i}");
            previo = y;
        }
    }
}
