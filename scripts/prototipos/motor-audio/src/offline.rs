//! Un backend de Kira que renderiza fuera de línea y entrega lo que produce.
//!
//! El `MockBackend` de Kira procesa pero no deja leer la salida; este sí, y es lo
//! que permite medir el motor muestra a muestra sin tarjeta de sonido.

use kira::backend::{Backend, Renderer};

pub struct Offline {
    tasa: u32,
    renderer: Option<Renderer>,
    bloque: usize,
}

#[derive(Clone, Copy)]
pub struct AjustesOffline {
    pub tasa: u32,
}

impl Default for AjustesOffline {
    fn default() -> Self {
        Self { tasa: 44_100 }
    }
}

impl Backend for Offline {
    type Settings = AjustesOffline;
    type Error = ();

    fn setup(ajustes: Self::Settings, internal_buffer_size: usize) -> Result<(Self, u32), ()> {
        Ok((
            Self {
                tasa: ajustes.tasa,
                renderer: None,
                bloque: internal_buffer_size,
            },
            ajustes.tasa,
        ))
    }

    fn start(&mut self, renderer: Renderer) -> Result<(), ()> {
        self.renderer = Some(renderer);
        Ok(())
    }
}

impl Offline {
    pub fn tasa(&self) -> u32 {
        self.tasa
    }

    /// Renderiza un bloque de `self.bloque` frames y lo añade a `salida`.
    pub fn bloque(&mut self, salida: &mut Vec<f32>) {
        let renderer = self.renderer.as_mut().expect("el gestor ya arrancó");
        renderer.on_start_processing();
        let mut buffer = vec![0.0f32; self.bloque * 2];
        renderer.process(&mut buffer, 2);
        salida.extend_from_slice(&buffer);
    }

    /// Renderiza al menos `frames` frames.
    pub fn renderizar(&mut self, frames: usize) -> Vec<f32> {
        let mut salida = Vec::with_capacity((frames + self.bloque) * 2);
        while salida.len() / 2 < frames {
            self.bloque(&mut salida);
        }
        salida
    }

    pub fn tam_bloque(&self) -> usize {
        self.bloque
    }
}
