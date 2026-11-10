//! Diez campanas que no cuestan nada mientras están planas (P20).
//!
//! Las campanas de Kira calculan cada muestra aunque estén a 0 dB. Con diez en
//! cada plato y diez en la maestra, eran casi todo lo que gastaba el motor: el 3,9
//! de 4,3 % de un núcleo, y el criterio de ADR-003 es el 2 %. Se siguen usando los
//! filtros de Kira, porque las ganancias corregidas del ecualizador están
//! calculadas para su respuesta exacta (`ecualizador.rs`), pero dentro de este
//! efecto, que solo los procesa mientras alguna banda no está a 0 dB o una
//! transición hacia plano no ha terminado. A 0 dB una campana de Simper devuelve la
//! entrada tal cual, así que saltarla no cambia el sonido.

use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;

use kira::effect::eq_filter::{EqFilterBuilder, EqFilterHandle, EqFilterKind};
use kira::effect::{Effect, EffectBuilder};
use kira::info::Info;
use kira::{Decibels, Frame};

/// Lo que el motor le dice al banco: si está plano y hasta qué muestra seguir
/// procesando mientras vuelve a plano.
#[derive(Default)]
pub struct Estado {
    plano: AtomicBool,
    /// Muestras que aún hay que procesar tras pedir plano (la transición).
    gracia: AtomicU64,
}

impl Estado {
    /// Alguna banda va a sonar distinta de 0 dB.
    pub fn activar(&self) {
        self.plano.store(false, Ordering::Release);
    }

    /// Todas vuelven a 0 dB en `segundos`: se procesa hasta que acabe la
    /// transición, con margen.
    pub fn a_plano(&self, segundos: f64, tasa: u32) {
        let muestras = ((segundos + 0.1) * f64::from(tasa)).ceil() as u64;
        self.gracia.store(muestras, Ordering::Release);
        self.plano.store(true, Ordering::Release);
    }
}

pub struct Banco {
    pub filtros: Vec<EqFilterBuilder>,
    pub estado: Arc<Estado>,
}

/// El banco con sus campanas a 0 dB, y el estado con que el motor lo enciende.
pub fn banco(frecuencias: &[f64], q: f64) -> (Banco, Arc<Estado>) {
    let estado = Arc::new(Estado::default());
    estado.plano.store(true, Ordering::Release);
    let filtros = frecuencias
        .iter()
        .map(|f| EqFilterBuilder::new(EqFilterKind::Bell, *f, Decibels::IDENTITY, q))
        .collect();
    let banco = Banco {
        filtros,
        estado: Arc::clone(&estado),
    };
    (banco, estado)
}

impl EffectBuilder for Banco {
    type Handle = Vec<EqFilterHandle>;

    fn build(self) -> (Box<dyn Effect>, Self::Handle) {
        let (efectos, manejadores): (Vec<_>, Vec<_>) =
            self.filtros.into_iter().map(EffectBuilder::build).unzip();
        (
            Box::new(Efecto {
                efectos,
                estado: self.estado,
            }),
            manejadores,
        )
    }
}

struct Efecto {
    efectos: Vec<Box<dyn Effect>>,
    estado: Arc<Estado>,
}

impl Effect for Efecto {
    fn init(&mut self, sample_rate: u32, internal_buffer_size: usize) {
        for e in &mut self.efectos {
            e.init(sample_rate, internal_buffer_size);
        }
    }

    fn on_change_sample_rate(&mut self, sample_rate: u32) {
        for e in &mut self.efectos {
            e.on_change_sample_rate(sample_rate);
        }
    }

    fn on_start_processing(&mut self) {
        // Siempre: así las órdenes de ganancia llegan aunque esté saltándose.
        for e in &mut self.efectos {
            e.on_start_processing();
        }
    }

    fn process(&mut self, input: &mut [Frame], dt: f64, info: &Info) {
        if self.estado.plano.load(Ordering::Acquire) {
            let n = input.len() as u64;
            let quedan = self.estado.gracia.load(Ordering::Acquire);
            if quedan == 0 {
                return;
            }
            self.estado
                .gracia
                .store(quedan.saturating_sub(n), Ordering::Release);
        }
        for e in &mut self.efectos {
            e.process(input, dt, info);
        }
    }
}

#[cfg(test)]
mod tests {
    use kira::effect::EffectBuilder;
    use kira::info::MockInfoBuilder;
    use kira::{Decibels, Frame, Tween};

    use super::*;

    fn senal() -> Vec<Frame> {
        (0..512)
            .map(|i| {
                let x = ((i as f32) * 0.07).sin() * 0.4;
                Frame { left: x, right: -x }
            })
            .collect()
    }

    #[test]
    fn plano_no_toca_la_senal_y_con_ganancia_si() {
        let (banco, estado) = banco(
            &crate::audio::ecualizador::BANDAS_HZ,
            crate::audio::ecualizador::Q,
        );
        let (mut efecto, mut manejadores) = banco.build();
        efecto.init(48_000, 128);
        let info = MockInfoBuilder::new().build();
        // Plano: sale exactamente lo que entra, sin procesar.
        let mut x = senal();
        efecto.on_start_processing();
        efecto.process(&mut x, 1.0 / 48_000.0, &info);
        assert_eq!(x, senal());
        // Con una banda arriba, cambia.
        estado.activar();
        manejadores[5].set_gain(
            Decibels(9.0),
            Tween {
                duration: std::time::Duration::ZERO,
                ..Default::default()
            },
        );
        let mut y = senal();
        efecto.on_start_processing();
        efecto.process(&mut y, 1.0 / 48_000.0, &info);
        assert_ne!(y, senal());
        // De vuelta a plano: procesa la transición y luego deja de hacerlo.
        for m in &mut manejadores {
            m.set_gain(
                Decibels::IDENTITY,
                Tween {
                    duration: std::time::Duration::ZERO,
                    ..Default::default()
                },
            );
        }
        estado.a_plano(0.0, 48_000);
        efecto.on_start_processing();
        for _ in 0..20 {
            let mut z = senal();
            efecto.process(&mut z, 1.0 / 48_000.0, &info);
        }
        let mut z = senal();
        efecto.process(&mut z, 1.0 / 48_000.0, &info);
        assert_eq!(z, senal());
    }
}
