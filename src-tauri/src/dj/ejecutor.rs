//! Quien aplica una mezcla al motor: `EjecutorMezcla` y la puerta de
//! `_tick_transicion_locked` de la V1.
//!
//! Se arma cargando la pista que entra en el plato libre, en silencio. La mezcla no
//! empieza hasta que esa pista suena de verdad (la **puerta**): en la V1, empezar el
//! fundido mientras VLC aún abría el archivo producía el bajón que se oía en cada
//! transición. Si en 2,5 s no suena, empieza igual para no bloquear la sesión.
//!
//! El avance se mide con el reloj del audio (los segundos que lleva sonando cada
//! plato), no con el de la pared: una pausa en mitad de la mezcla la congela, y el
//! render fuera de línea, que va más rápido que el tiempo real, la recorre igual.

use std::time::{Duration, Instant};

use super::mezcla::{self, Plan};
use crate::audio::{Motor, PistaEnCola};

/// Lo que el ejecutor necesita del motor. Existe para probar la puerta sin audio.
pub trait Platos {
    fn preparar_entrante(&mut self, pista: PistaEnCola, desde_seg: f64, instrumental: bool);
    /// Ficha y segundos de la pista que sale.
    fn saliente(&self) -> (u64, f64);
    /// Ficha y segundos de la pista que entra.
    fn entrante(&self) -> (u64, f64);
    fn mezclar(
        &mut self,
        volumenes: (f32, f32),
        bandas: (&[f32; 10], &[f32; 10]),
        instrumental: f32,
    );
    fn terminar(&mut self);
    fn cancelar(&mut self);
}

impl<B: kira::backend::Backend> Platos for Motor<B> {
    fn preparar_entrante(&mut self, pista: PistaEnCola, desde_seg: f64, instrumental: bool) {
        Self::preparar_entrante(self, pista, desde_seg, instrumental);
    }
    fn saliente(&self) -> (u64, f64) {
        let p = self.posicion();
        (p.ficha, p.segundos)
    }
    fn entrante(&self) -> (u64, f64) {
        self.posicion_entrante()
    }
    fn mezclar(
        &mut self,
        volumenes: (f32, f32),
        bandas: (&[f32; 10], &[f32; 10]),
        instrumental: f32,
    ) {
        Self::mezclar(self, volumenes, bandas, instrumental);
    }
    fn terminar(&mut self) {
        self.terminar_mezcla();
    }
    fn cancelar(&mut self) {
        self.cancelar_mezcla();
    }
}

/// Lo que la puerta espera antes de empezar igual.
pub const ESPERA_MAXIMA: Duration = Duration::from_millis(2500);

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Paso {
    /// La entrante aún no suena: la que sale sigue entera.
    Esperando,
    /// Mezclando, con el avance de 0 a 1.
    Mezclando(f64),
    /// La entrante es ya la pista actual.
    Terminada,
}

pub struct Ejecutor {
    plan: Plan,
    ficha: u64,
    armado: Instant,
    origen: Option<Origen>,
    /// Terminada o cancelada: ya no toca el motor.
    acabado: bool,
}

/// Los segundos de cada plato al abrirse la puerta: el origen del reloj. La
/// entrante puede no sonar aún si la puerta se abrió por tiempo.
#[derive(Debug, Clone, Copy)]
struct Origen {
    saliente: f64,
    entrante: Option<f64>,
}

impl Ejecutor {
    /// Carga la entrante y deja la que sale sonando entera.
    pub fn armar(
        motor: &mut dyn Platos,
        plan: Plan,
        entrante: PistaEnCola,
        ahora: Instant,
    ) -> Self {
        let ficha = entrante.ficha;
        motor.preparar_entrante(entrante, plan.entrada_b_seg, plan.instrumental_b);
        motor.mezclar(
            (1.0, 0.0),
            (&[0.0; 10], &[0.0; 10]),
            Self::instrumental(&plan, 0.0),
        );
        Self {
            plan,
            ficha,
            armado: ahora,
            origen: None,
            acabado: false,
        }
    }

    #[must_use]
    pub const fn plan(&self) -> &Plan {
        &self.plan
    }

    /// En las capas la entrante suena sin voz y la voz vuelve en el último cuarto,
    /// cuando la que sale ya se va.
    fn instrumental(plan: &Plan, p: f64) -> f32 {
        if !plan.instrumental_b {
            0.0
        } else if p <= 0.75 {
            1.0
        } else {
            ((1.0 - p) / 0.25) as f32
        }
    }

    /// `_tick_transicion_locked`: un paso. Se llama a menudo (cada pocas decenas de
    /// milisegundos); cada valor se suaviza en el motor hasta el siguiente.
    pub fn tic(&mut self, motor: &mut dyn Platos, ahora: Instant) -> Paso {
        if self.acabado {
            return Paso::Terminada;
        }
        let (_, sa) = motor.saliente();
        let (fb, sb) = motor.entrante();
        let suena = fb == self.ficha && sb > 0.0;
        if self.origen.is_none() {
            // Si la entrante debía empezar más adelante, se espera a que esté allí:
            // en la V1 el salto llegaba tarde. En la V2 se aplica antes del primer
            // bloque, pero la condición no cuesta nada.
            let en_su_punto = self.plan.entrada_b_seg <= 0.5 || sb >= self.plan.entrada_b_seg - 1.0;
            if !(suena && en_su_punto) && ahora.duration_since(self.armado) < ESPERA_MAXIMA {
                motor.mezclar(
                    (1.0, 0.0),
                    (&[0.0; 10], &[0.0; 10]),
                    Self::instrumental(&self.plan, 0.0),
                );
                return Paso::Esperando;
            }
            self.origen = Some(Origen {
                saliente: sa,
                entrante: None,
            });
        }
        let origen = self.origen.as_mut().expect("la puerta está abierta");
        if suena && origen.entrante.is_none() {
            origen.entrante = Some(sb);
        }
        // El plato que más ha avanzado manda: si uno no suena (la entrante no se pudo
        // abrir, o la saliente se acabó), el otro sigue llevando la mezcla.
        let mut transcurrido = sa - origen.saliente;
        if let (true, Some(ob)) = (suena, origen.entrante) {
            transcurrido = transcurrido.max(sb - ob);
        }
        let p = (transcurrido / self.plan.solapamiento_seg.max(0.05)).clamp(0.0, 1.0);
        let (va, vb) = mezcla::volumenes(self.plan.tecnica, p);
        let (ba, bb) = mezcla::bandas(self.plan.tecnica, p);
        motor.mezclar(
            (va as f32, vb as f32),
            (&ba, &bb),
            Self::instrumental(&self.plan, p),
        );
        if p >= 1.0 {
            motor.terminar();
            self.acabado = true;
            return Paso::Terminada;
        }
        Paso::Mezclando(p)
    }

    /// Deshace la mezcla: la que suena vuelve a sonar sola.
    pub fn cancelar(&mut self, motor: &mut dyn Platos) {
        if !self.acabado {
            motor.cancelar();
            self.acabado = true;
        }
    }
}

#[cfg(test)]
mod pruebas {
    //! La puerta, como `tests/test_dj_transicion_gate.py` de la V1.

    use std::path::PathBuf;

    use super::*;
    use crate::dj::mezcla::Tecnica;

    #[derive(Default)]
    struct Simulado {
        saliente: (u64, f64),
        entrante: (u64, f64),
        volumenes: Vec<(f32, f32)>,
        terminada: bool,
        cancelada: bool,
    }

    impl Platos for Simulado {
        fn preparar_entrante(&mut self, _: PistaEnCola, _: f64, _: bool) {}
        fn saliente(&self) -> (u64, f64) {
            self.saliente
        }
        fn entrante(&self) -> (u64, f64) {
            self.entrante
        }
        fn mezclar(&mut self, v: (f32, f32), _: (&[f32; 10], &[f32; 10]), _: f32) {
            self.volumenes.push(v);
        }
        fn terminar(&mut self) {
            self.terminada = true;
        }
        fn cancelar(&mut self) {
            self.cancelada = true;
        }
    }

    fn plan(entrada: f64) -> Plan {
        Plan {
            tecnica: Tecnica::Fundido,
            solapamiento_seg: 4.0,
            salida_a_seg: 120.0,
            entrada_b_seg: entrada,
            instrumental_b: false,
            usa_bandas: false,
            razones: Vec::new(),
        }
    }

    fn armado(entrada: f64) -> (Simulado, Ejecutor, Instant) {
        let mut m = Simulado {
            saliente: (1, 120.0),
            ..Simulado::default()
        };
        let ahora = Instant::now();
        let pista = PistaEnCola {
            ficha: 2,
            ruta: PathBuf::from("b.mp3"),
            instrumental: None,
            ganancia_db: 0.0,
        };
        let e = Ejecutor::armar(&mut m, plan(entrada), pista, ahora);
        (m, e, ahora)
    }

    #[test]
    fn mientras_la_entrante_no_suena_la_saliente_sigue_entera() {
        let (mut m, mut e, ahora) = armado(0.0);
        assert_eq!(
            e.tic(&mut m, ahora + Duration::from_millis(100)),
            Paso::Esperando
        );
        assert_eq!(m.volumenes.last(), Some(&(1.0, 0.0)));
        assert!(e.origen.is_none());
    }

    #[test]
    fn cuando_la_entrante_suena_empieza_la_mezcla() {
        let (mut m, mut e, ahora) = armado(0.0);
        m.entrante = (2, 0.3);
        assert_eq!(e.tic(&mut m, ahora), Paso::Mezclando(0.0));
        m.saliente.1 += 2.0;
        m.entrante.1 += 2.0;
        assert_eq!(e.tic(&mut m, ahora), Paso::Mezclando(0.5));
        m.saliente.1 += 2.0;
        m.entrante.1 += 2.0;
        assert_eq!(e.tic(&mut m, ahora), Paso::Terminada);
        assert!(m.terminada);
    }

    #[test]
    fn espera_a_que_la_entrante_este_en_su_punto_de_entrada() {
        let (mut m, mut e, ahora) = armado(30.0);
        m.entrante = (2, 1.0);
        assert_eq!(e.tic(&mut m, ahora), Paso::Esperando);
        m.entrante = (2, 30.0);
        assert_eq!(e.tic(&mut m, ahora), Paso::Mezclando(0.0));
    }

    #[test]
    fn si_la_entrante_no_llega_la_mezcla_empieza_igual_y_la_lleva_la_saliente() {
        let (mut m, mut e, ahora) = armado(0.0);
        let tarde = ahora + ESPERA_MAXIMA + Duration::from_millis(500);
        assert_eq!(e.tic(&mut m, tarde), Paso::Mezclando(0.0));
        m.saliente.1 += 1.0;
        assert_eq!(e.tic(&mut m, tarde), Paso::Mezclando(0.25));
    }

    #[test]
    fn otra_ficha_en_el_plato_libre_no_abre_la_puerta() {
        let (mut m, mut e, ahora) = armado(0.0);
        m.entrante = (9, 5.0);
        assert_eq!(e.tic(&mut m, ahora), Paso::Esperando);
    }

    #[test]
    fn cancelar_devuelve_la_saliente_y_no_termina() {
        let (mut m, mut e, ahora) = armado(0.0);
        m.entrante = (2, 0.3);
        let _ = e.tic(&mut m, ahora);
        e.cancelar(&mut m);
        assert!(m.cancelada && !m.terminada);
        assert_eq!(e.tic(&mut m, ahora), Paso::Terminada);
    }
}

#[cfg(test)]
mod render {
    //! Cada técnica renderizada fuera de línea con el motor real: ni clics, ni
    //! picos, ni saltos de sonoridad durante el solapamiento (criterio de la Fase 6).

    use std::f32::consts::TAU;
    use std::time::Instant;

    use super::*;
    use crate::audio::pruebas::{motor, renderizar, wav};
    use crate::audio::EventoMotor;
    use crate::dj::mezcla::{self, Tecnica};

    const TASA: u32 = 44_100;

    fn tono(graves: f32, medios: f32) -> impl Fn(usize, usize) -> f32 {
        move |i, _| {
            let t = i as f32 / TASA as f32;
            0.25 * (TAU * graves * t).sin() + 0.2 * (TAU * medios * t).sin()
        }
    }

    fn rms(x: &[f32]) -> f32 {
        (x.iter().map(|v| v * v).sum::<f32>() / x.len().max(1) as f32).sqrt()
    }

    /// Renderiza una mezcla completa y devuelve el canal izquierdo.
    fn mezclar(tecnica: Tecnica, dir: &std::path::Path) -> Vec<f32> {
        let a = dir.join("a.wav");
        let b = dir.join("b.wav");
        let sin_voz = dir.join("b-instrumental.wav");
        let _ = wav(&a, TASA, TASA as usize * 16, tono(60.0, 220.0));
        let _ = wav(&b, TASA, TASA as usize * 16, tono(80.0, 330.0));
        let _ = wav(&sin_voz, TASA, TASA as usize * 16, tono(80.0, 440.0));
        let mut m = motor(TASA);
        m.reproducir(
            PistaEnCola {
                ficha: 1,
                ruta: a,
                instrumental: None,
                ganancia_db: 0.0,
            },
            0.0,
        );
        let mut salida = renderizar(&mut m, TASA as usize * 2);
        let plan = Plan {
            tecnica,
            solapamiento_seg: mezcla::solapamiento(tecnica, 5.0),
            salida_a_seg: 2.0,
            entrada_b_seg: 1.0,
            instrumental_b: tecnica == Tecnica::Capas,
            usa_bandas: matches!(tecnica, Tecnica::SinGraves | Tecnica::Barrido),
            razones: Vec::new(),
        };
        let entrante = PistaEnCola {
            ficha: 2,
            ruta: b,
            instrumental: Some(sin_voz),
            ganancia_db: 0.0,
        };
        let mut e = Ejecutor::armar(&mut m, plan, entrante, Instant::now());
        let mut pasos = 0;
        while e.tic(&mut m, Instant::now()) != Paso::Terminada {
            salida.extend(renderizar(&mut m, 512));
            pasos += 1;
            assert!(pasos < 4000, "{tecnica:?}: la mezcla no termina");
        }
        salida.extend(renderizar(&mut m, TASA as usize * 2));
        assert_eq!(m.posicion().ficha, 2, "{tecnica:?}");
        let mut empezo = false;
        for _ in 0..200 {
            empezo |= m
                .eventos()
                .any(|ev| ev == EventoMotor::PistaEmpieza { ficha: 2 });
            if empezo {
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(5));
        }
        assert!(empezo, "{tecnica:?}: la entrante no se contó como empezada");
        salida.iter().step_by(2).copied().collect()
    }

    #[test]
    fn ninguna_tecnica_hace_clic_ni_salta_de_volumen() {
        let dir = std::env::temp_dir().join(format!("ns-mezcla-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        for tecnica in [
            Tecnica::Fundido,
            Tecnica::SinGraves,
            Tecnica::Barrido,
            Tecnica::Capas,
            Tecnica::Corte,
        ] {
            let x = mezclar(tecnica, &dir);
            let pico = x.iter().fold(0.0f32, |p, v| p.max(v.abs()));
            assert!(pico <= 1.0, "{tecnica:?}: pico {pico}");
            // La mayor pendiente de las señales es 0,25·2π·80/44 100 + 0,2·2π·440/44 100,
            // unas 0,015 por muestra; un clic la multiplica.
            let salto = x.windows(2).fold(0.0f32, |s, w| s.max((w[1] - w[0]).abs()));
            assert!(salto < 0.04, "{tecnica:?}: salto de {salto} entre muestras");

            // Ventanas de 50 ms: de una a la siguiente, menos de 1,5 dB.
            let ventanas: Vec<f32> = x.chunks(2205).map(rms).collect();
            let inicio = ventanas.iter().position(|v| *v > 1e-3).unwrap_or(0);
            for (k, w) in ventanas[inicio..ventanas.len() - 1].windows(2).enumerate() {
                let db = 20.0 * (w[1].max(1e-6) / w[0].max(1e-6)).log10();
                assert!(
                    db.abs() < 1.5,
                    "{tecnica:?}: {db:.2} dB en la ventana {}",
                    inicio + k
                );
            }

            // Sonoridad a corto plazo (3 s) cada 100 ms: sin escalones de más de 1 LU.
            let mut medidor = ebur128::EbuR128::new(1, TASA, ebur128::Mode::S).expect("medidor");
            let mut previa: Option<f64> = None;
            for (k, trozo) in x[inicio * 2205..].chunks(4410).enumerate() {
                medidor.add_frames_f32(trozo).expect("frames");
                let Ok(lufs) = medidor.loudness_shortterm() else {
                    continue;
                };
                if k >= 30 && lufs.is_finite() {
                    if let Some(p) = previa {
                        assert!((lufs - p).abs() < 1.0, "{tecnica:?}: {:.2} LU", lufs - p);
                    }
                    previa = Some(lufs);
                }
            }
        }
        let _ = std::fs::remove_dir_all(&dir);
    }
}
