//! El perfil del equipo para mezclar: `servicios/dj_privado/hardware_profile.py`.
//!
//! Mezclar por capas necesita el instrumental de la pista que entra, y prepararlo a
//! tiempo depende de lo rápido que el equipo separa la voz. Se mide una vez por
//! arranque, separando diez segundos de audio sintético con el modelo del agregado
//! de karaoke: hasta 1,5 veces el tiempo real es un equipo alto, hasta 5 uno medio y
//! más, o sin el agregado, uno bajo. Mientras no hay medida, el perfil es el bajo:
//! el DJ funciona entero con las otras cuatro técnicas.
//!
//! La V1 guardaba la medida en `config_ui`; la migración la descarta
//! (docs/engineering/migracion-v1.md) porque cambia con el equipo y con el modelo.

use std::sync::{Arc, Mutex};
use std::time::Duration;

use serde::{Deserialize, Serialize};

use super::mezcla::Tecnica;
use crate::error::NsResult;

/// `PerfilHardware`, con los nombres de la V1.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Perfil {
    #[serde(rename = "low")]
    Bajo,
    #[serde(rename = "mid")]
    Medio,
    #[serde(rename = "high")]
    Alto,
}

/// `tecnicas_habilitadas`: sin capas en el perfil bajo.
#[must_use]
pub fn tecnicas(perfil: Perfil) -> &'static [Tecnica] {
    use Tecnica as T;
    match perfil {
        Perfil::Bajo => &[T::Corte, T::Fundido, T::SinGraves, T::Barrido],
        Perfil::Medio | Perfil::Alto => &[T::Corte, T::Fundido, T::SinGraves, T::Barrido, T::Capas],
    }
}

const UMBRAL_ALTO: f64 = 1.5;
const UMBRAL_MEDIO: f64 = 5.0;
/// Una medida que tarda más que esto deja el perfil en bajo.
pub const LIMITE: Duration = Duration::from_secs(120);

/// `clasificar`: el factor es lo que se tarda en separar dividido entre lo que dura.
#[must_use]
pub fn clasificar(factor_tiempo_real: f64, separador: bool) -> Perfil {
    if !separador || factor_tiempo_real <= 0.0 || !factor_tiempo_real.is_finite() {
        Perfil::Bajo
    } else if factor_tiempo_real <= UMBRAL_ALTO {
        Perfil::Alto
    } else if factor_tiempo_real <= UMBRAL_MEDIO {
        Perfil::Medio
    } else {
        Perfil::Bajo
    }
}

/// `ResultadoBenchmark`, con sus claves.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Medida {
    pub perfil: Perfil,
    pub seg_para_10s: f64,
    pub factor_tiempo_real: f64,
    /// Lo que la V1 llamaba `demucs_disponible`: si hay modelo de separación.
    pub separador: bool,
    pub error: Option<&'static str>,
}

impl Medida {
    /// Convierte lo medido (o su fallo) en el perfil.
    #[must_use]
    pub fn de(separador: bool, tiempo: NsResult<Duration>) -> Self {
        match tiempo {
            Ok(t) if t > LIMITE => Self {
                perfil: Perfil::Bajo,
                seg_para_10s: t.as_secs_f64(),
                factor_tiempo_real: t.as_secs_f64() / 10.0,
                separador,
                error: Some("timeout"),
            },
            Ok(t) => {
                let seg = t.as_secs_f64();
                Self {
                    perfil: clasificar(seg / 10.0, separador),
                    seg_para_10s: super::redondear(seg, 3),
                    factor_tiempo_real: super::redondear(seg / 10.0, 3),
                    separador,
                    error: None,
                }
            }
            Err(_) => Self {
                perfil: Perfil::Bajo,
                seg_para_10s: 0.0,
                factor_tiempo_real: 0.0,
                separador,
                error: Some(if separador {
                    "forward"
                } else {
                    "sin_separador"
                }),
            },
        }
    }
}

#[derive(Default)]
struct Estado {
    medida: Option<Medida>,
    midiendo: bool,
}

/// La medida del equipo, compartida entre hilos.
#[derive(Clone, Default)]
pub struct Equipo {
    estado: Arc<Mutex<Estado>>,
}

impl Equipo {
    /// `perfil_efectivo`: el medido, o el bajo mientras no lo hay.
    #[must_use]
    pub fn perfil(&self) -> Perfil {
        self.medida().map_or(Perfil::Bajo, |m| m.perfil)
    }

    #[must_use]
    pub fn medida(&self) -> Option<Medida> {
        self.estado.lock().ok().and_then(|e| e.medida.clone())
    }

    /// `lanzar_benchmark_si_falta`: mide en un hilo aparte si no hay medida (o si
    /// `forzar`) y no hay otra en curso. Devuelve si lanzó una. `medir` es la
    /// separación de prueba; `None` si no hay modelo de separación.
    pub fn medir_si_falta<F>(&self, forzar: bool, medir: Option<F>) -> bool
    where
        F: FnOnce() -> NsResult<Duration> + Send + 'static,
    {
        {
            let Ok(mut e) = self.estado.lock() else {
                return false;
            };
            if e.midiendo || (!forzar && e.medida.is_some()) {
                return false;
            }
            e.midiendo = true;
        }
        let estado = Arc::clone(&self.estado);
        let lanzado = std::thread::Builder::new()
            .name("dj-equipo".into())
            .spawn(move || {
                let medida = match medir {
                    Some(m) => Medida::de(true, m()),
                    None => Medida::de(false, Ok(Duration::ZERO)),
                };
                tracing::info!(
                    perfil = ?medida.perfil,
                    factor = medida.factor_tiempo_real,
                    "perfil del equipo para mezclar"
                );
                if let Ok(mut e) = estado.lock() {
                    e.medida = Some(medida);
                    e.midiendo = false;
                }
            })
            .is_ok();
        if !lanzado {
            if let Ok(mut e) = self.estado.lock() {
                e.midiendo = false;
            }
        }
        lanzado
    }

    /// Con el modelo del agregado de karaoke, si está instalado.
    pub fn medir_con_karaoke(&self, rutas: &crate::paths::Rutas, forzar: bool) -> bool {
        let modelo = crate::karaoke::modelo_instalado(rutas);
        self.medir_si_falta(forzar, modelo.map(|m| move || crate::karaoke::medir(&m)))
    }

    #[must_use]
    pub fn midiendo(&self) -> bool {
        self.estado.lock().is_ok_and(|e| e.midiendo)
    }
}

#[cfg(test)]
mod pruebas {
    //! Las propiedades de `tests/test_dj_hardware_profile.py` de la V1.

    use std::sync::mpsc;
    use std::time::Instant;

    use super::*;
    use crate::error::NsError;

    #[test]
    fn el_factor_decide_el_perfil_y_sin_separador_siempre_es_bajo() {
        assert_eq!(clasificar(0.8, true), Perfil::Alto);
        assert_eq!(clasificar(1.5, true), Perfil::Alto);
        assert_eq!(clasificar(3.0, true), Perfil::Medio);
        assert_eq!(clasificar(8.0, true), Perfil::Bajo);
        assert_eq!(clasificar(0.8, false), Perfil::Bajo);
        assert_eq!(clasificar(0.0, true), Perfil::Bajo);
        assert_eq!(clasificar(-1.0, true), Perfil::Bajo);
    }

    #[test]
    fn solo_el_perfil_bajo_renuncia_a_las_capas() {
        assert!(!tecnicas(Perfil::Bajo).contains(&Tecnica::Capas));
        assert!(tecnicas(Perfil::Medio).contains(&Tecnica::Capas));
        assert_eq!(tecnicas(Perfil::Alto).len(), 5);
    }

    #[test]
    fn un_fallo_o_una_medida_eterna_dejan_el_perfil_bajo() {
        assert_eq!(
            Medida::de(true, Err(NsError::Internal)).perfil,
            Perfil::Bajo
        );
        let lenta = Medida::de(true, Ok(LIMITE + Duration::from_secs(1)));
        assert_eq!((lenta.perfil, lenta.error), (Perfil::Bajo, Some("timeout")));
        let rapida = Medida::de(true, Ok(Duration::from_secs(8)));
        assert_eq!(
            (rapida.perfil, rapida.factor_tiempo_real),
            (Perfil::Alto, 0.8)
        );
    }

    fn esperar(e: &Equipo) {
        let limite = Instant::now() + Duration::from_secs(5);
        while e.midiendo() && Instant::now() < limite {
            std::thread::sleep(Duration::from_millis(2));
        }
    }

    #[test]
    fn sin_medida_el_perfil_es_bajo_y_se_mide_una_sola_vez() {
        let e = Equipo::default();
        assert_eq!(e.perfil(), Perfil::Bajo);
        let (tx, rx) = mpsc::channel::<()>();
        assert!(e.medir_si_falta(
            false,
            Some(move || {
                let _ = rx.recv();
                Ok(Duration::from_secs(30))
            })
        ));
        // Mientras mide no se lanza otra, ni forzándola.
        assert!(!e.medir_si_falta(true, Some(|| Ok(Duration::from_secs(1)))));
        tx.send(()).unwrap();
        esperar(&e);
        assert_eq!(e.perfil(), Perfil::Medio);
        assert!(!e.medir_si_falta(false, Some(|| Ok(Duration::from_secs(1)))));
        assert!(e.medir_si_falta(true, Some(|| Ok(Duration::from_secs(1)))));
        esperar(&e);
        assert_eq!(e.perfil(), Perfil::Alto);
    }

    #[test]
    fn sin_agregado_de_karaoke_el_perfil_medido_es_bajo() {
        let e = Equipo::default();
        assert!(e.medir_si_falta(false, None::<fn() -> NsResult<Duration>>));
        esperar(&e);
        let m = e.medida().unwrap();
        assert_eq!((m.perfil, m.separador), (Perfil::Bajo, false));
    }

    #[test]
    fn la_separacion_de_prueba_son_diez_segundos_por_el_mismo_camino_que_una_pista() {
        // Un modelo que devuelve silencio: lo que se mide es el recorrido entero.
        let mut llamadas = 0;
        let t = crate::karaoke::medir_con(&mut |trozo| {
            llamadas += 1;
            Ok(vec![0.0; trozo.len() * 4])
        })
        .unwrap();
        assert!(t < Duration::from_secs(5));
        // 441 000 muestras en segmentos de 343 980 con un 25 % de solape.
        assert_eq!(llamadas, 2);
    }
}
