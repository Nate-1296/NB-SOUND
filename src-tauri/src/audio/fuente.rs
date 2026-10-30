//! La fuente propia de Kira: la cola de reproducción (ADR-003).
//!
//! Kira se queda con lo que hace bien (pistas de mezcla, efectos, transiciones y la
//! salida por cpal) y la fuente la ponemos nosotros, porque es lo que decide la
//! exactitud:
//!
//! * **Sin cortes por construcción:** el alimentador entrega los bloques de una
//!   pista y, sin hueco, los de la siguiente. No hay dos sonidos que coordinar;
//!   F0.4.1 midió que encadenarlos con el reloj de Kira se desvía a los 8,4 s.
//! * **Karaoke sin deriva por construcción:** original e instrumental llegan en el
//!   mismo bloque, frame a frame.
//! * **Exacta a la tasa nativa:** si la pista y la salida tienen la misma tasa, la
//!   salida es la entrada muestra a muestra. Si no, se remuestrea con un Hermite
//!   de cuatro puntos, el mismo interpolador que usa Kira en sus sonidos.
//!
//! Corre en el hilo de audio: no bloquea, no reserva memoria y no libera la de
//! los bloques, que devuelve al alimentador para que los reutilice.

use std::sync::atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering};
use std::sync::mpsc::{Receiver, SyncSender};
use std::sync::Arc;

use kira::info::Info;
use kira::sound::{Sound, SoundData};
use kira::Frame;

/// Un trozo de audio decodificado.
pub struct Bloque {
    /// Los bloques de una generación anterior a la vigente se tiran: son de antes
    /// de una búsqueda o de un cambio de pista.
    pub generacion: u64,
    /// La pista a la que pertenece, por su ficha en la cola.
    pub pista: u64,
    /// Posición, en frames de la pista, del primero del bloque.
    pub frame_inicial: u64,
    pub tasa: u32,
    pub original: Vec<Frame>,
    pub instrumental: Option<Vec<Frame>>,
    /// Detrás de este bloque no viene nada: la cola se acabó.
    pub fin: bool,
}

/// Lo que la fuente comparte con el resto del motor, sin cerrojos.
#[derive(Default)]
pub struct Compartido {
    pub generacion: AtomicU64,
    /// Lo que está sonando ahora mismo: ficha de la pista y frame dentro de ella.
    pub pista: AtomicU64,
    pub frame: AtomicU64,
    pub tasa: AtomicU32,
    /// Original (0) o instrumental (1), en bits de `f32`.
    pub mezcla: AtomicU32,
    /// La fuente consumió el bloque de fin.
    pub terminado: AtomicBool,
    /// Bloques entregados que aún no se han oído.
    pub en_cola: AtomicU64,
    /// El motor se cerró: la fuente puede desaparecer.
    pub cerrado: AtomicBool,
    /// La generación del último bloque entregado. Las pruebas la usan para
    /// esperar a que haya datos de la vigente.
    pub entregada: AtomicU64,
    /// Lo que pasa en el hilo de audio, en orden: la ficha de cada pista que
    /// empieza, o [`FIN`]. Un anillo sin cerrojos que el vigía lee: con una sola
    /// marca, una pista que empezara y acabara entre dos lecturas se perdería, y
    /// el servicio creería que suena otra.
    sucesos: [AtomicU64; SUCESOS],
    escritos: AtomicU64,
}

/// Capacidad del anillo de sucesos. Hacen falta 32 pistas empezadas entre dos
/// lecturas del vigía (15 ms) para desbordarlo.
const SUCESOS: usize = 32;
/// La cola se acabó.
pub const FIN: u64 = u64::MAX;

impl Compartido {
    /// Solo lo llama el hilo de audio: un único escritor.
    fn apuntar(&self, suceso: u64) {
        let n = self.escritos.load(Ordering::Relaxed);
        self.sucesos[n as usize % SUCESOS].store(suceso, Ordering::Relaxed);
        self.escritos.store(n + 1, Ordering::Release);
    }

    /// Los sucesos desde `leidos`, que avanza.
    pub fn leer_sucesos(&self, leidos: &mut u64, cada: &mut impl FnMut(u64)) {
        let escritos = self.escritos.load(Ordering::Acquire);
        // Si el anillo dio la vuelta, lo más viejo se perdió: se salta a lo vigente.
        *leidos = (*leidos).max(escritos.saturating_sub(SUCESOS as u64));
        while *leidos < escritos {
            cada(self.sucesos[*leidos as usize % SUCESOS].load(Ordering::Relaxed));
            *leidos += 1;
        }
    }

    pub fn karaoke(&self, activo: bool) {
        let v: f32 = if activo { 1.0 } else { 0.0 };
        self.mezcla.store(v.to_bits(), Ordering::Relaxed);
    }
}

pub struct DatosFuente {
    pub bloques: Receiver<Bloque>,
    pub devueltos: SyncSender<Vec<Frame>>,
    pub compartido: Arc<Compartido>,
    /// Duración de la transición entre original e instrumental, en segundos. Más
    /// de 20 ms para que conmutar no haga clic (criterio de ADR-003).
    pub rampa_seg: f64,
}

impl SoundData for DatosFuente {
    type Error = ();
    type Handle = ();

    fn into_sound(self) -> Result<(Box<dyn Sound>, ()), ()> {
        Ok((
            Box::new(Fuente {
                bloques: self.bloques,
                devueltos: self.devueltos,
                compartido: self.compartido,
                rampa_seg: self.rampa_seg,
                actual: None,
                indice: 0,
                historia: [Frame::ZERO; 4],
                fraccion: 0.0,
                generacion: u64::MAX,
                mezcla: 0.0,
            }),
            (),
        ))
    }
}

struct Fuente {
    bloques: Receiver<Bloque>,
    devueltos: SyncSender<Vec<Frame>>,
    compartido: Arc<Compartido>,
    rampa_seg: f64,
    actual: Option<Bloque>,
    indice: usize,
    /// Los cuatro últimos frames de entrada, para interpolar.
    historia: [Frame; 4],
    fraccion: f64,
    generacion: u64,
    mezcla: f32,
}

impl Fuente {
    fn devolver(&mut self, bloque: Bloque) {
        // Si el alimentador no tiene sitio, el vector se libera aquí: es raro y
        // preferible a bloquear el hilo de audio.
        let _ = self.devueltos.try_send(bloque.original);
        if let Some(i) = bloque.instrumental {
            let _ = self.devueltos.try_send(i);
        }
    }

    /// El siguiente frame de entrada ya mezclado, o `None` si no hay datos.
    fn siguiente_entrada(&mut self, paso_mezcla: f32) -> Option<Frame> {
        let vigente = self.compartido.generacion.load(Ordering::Acquire);
        if vigente != self.generacion {
            // Tras una búsqueda o un cambio de pista, lo que había no vale.
            self.generacion = vigente;
            if let Some(b) = self.actual.take() {
                self.devolver(b);
            }
            self.historia = [Frame::ZERO; 4];
            self.fraccion = 0.0;
        }
        loop {
            if let Some(b) = &self.actual {
                if self.indice < b.original.len() {
                    break;
                }
                let b = self.actual.take().expect("hay bloque");
                self.devolver(b);
            }
            let bloque = self.bloques.try_recv().ok()?;
            self.compartido.en_cola.fetch_sub(1, Ordering::AcqRel);
            if bloque.generacion != vigente {
                self.devolver(bloque);
                continue;
            }
            if bloque.fin {
                self.compartido.terminado.store(true, Ordering::Release);
                self.compartido.apuntar(FIN);
                self.devolver(bloque);
                return None;
            }
            if self.compartido.pista.swap(bloque.pista, Ordering::Relaxed) != bloque.pista {
                self.compartido.apuntar(bloque.pista);
            }
            self.compartido.tasa.store(bloque.tasa, Ordering::Relaxed);
            self.indice = 0;
            self.actual = Some(bloque);
        }
        let b = self.actual.as_ref().expect("hay bloque");
        let objetivo = f32::from_bits(self.compartido.mezcla.load(Ordering::Relaxed));
        if self.mezcla < objetivo {
            self.mezcla = (self.mezcla + paso_mezcla).min(objetivo);
        } else if self.mezcla > objetivo {
            self.mezcla = (self.mezcla - paso_mezcla).max(objetivo);
        }
        let o = b.original[self.indice];
        let frame = match &b.instrumental {
            Some(inst) if self.mezcla > 0.0 => {
                let i = inst.get(self.indice).copied().unwrap_or(Frame::ZERO);
                o * (1.0 - self.mezcla) + i * self.mezcla
            }
            _ => o,
        };
        self.compartido
            .frame
            .store(b.frame_inicial + self.indice as u64 + 1, Ordering::Relaxed);
        self.indice += 1;
        Some(frame)
    }

    /// La tasa de lo que va a sonar. Si aún no hay bloque, el primero que llegue
    /// manda; sin ninguno, la de la salida, para no interpolar silencio.
    fn tasa_actual(&self, tasa_salida: f64) -> f64 {
        match &self.actual {
            Some(b) => f64::from(b.tasa),
            None => tasa_salida,
        }
    }
}

/// Hermite de cuatro puntos entre `y[1]` e `y[2]`.
fn hermite(y: &[Frame; 4], t: f32) -> Frame {
    let c0 = y[1];
    let c1 = (y[2] - y[0]) * 0.5;
    let c2 = y[0] - y[1] * 2.5 + y[2] * 2.0 - y[3] * 0.5;
    let c3 = (y[3] - y[0]) * 0.5 + (y[1] - y[2]) * 1.5;
    ((c3 * t + c2) * t + c1) * t + c0
}

impl Sound for Fuente {
    fn process(&mut self, out: &mut [Frame], dt: f64, _info: &Info) {
        let tasa_salida = 1.0 / dt;
        for frame in out.iter_mut() {
            let tasa = self.tasa_actual(tasa_salida);
            let paso_mezcla = (1.0 / (self.rampa_seg * tasa).max(1.0)) as f32;
            if (tasa - tasa_salida).abs() < 0.5 {
                // Misma tasa: la entrada tal cual, bit a bit.
                *frame = self.siguiente_entrada(paso_mezcla).unwrap_or(Frame::ZERO);
                continue;
            }
            let razon = tasa / tasa_salida;
            while self.fraccion >= 1.0 {
                let nuevo = self.siguiente_entrada(paso_mezcla).unwrap_or(Frame::ZERO);
                self.historia = [self.historia[1], self.historia[2], self.historia[3], nuevo];
                self.fraccion -= 1.0;
            }
            *frame = hermite(&self.historia, self.fraccion as f32);
            self.fraccion += razon;
        }
    }

    fn finished(&self) -> bool {
        self.compartido.cerrado.load(Ordering::Relaxed)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hermite_pasa_por_los_puntos() {
        let y = [
            Frame::from_mono(0.0),
            Frame::from_mono(1.0),
            Frame::from_mono(2.0),
            Frame::from_mono(3.0),
        ];
        assert_eq!(hermite(&y, 0.0).left, 1.0);
        assert!((hermite(&y, 1.0).left - 2.0).abs() < 1e-6);
        assert!(
            (hermite(&y, 0.5).left - 1.5).abs() < 1e-6,
            "una recta sigue siendo recta"
        );
    }
}
