//! Descubrir música por lo que se pide en palabras (F5.3.3):
//! `core/music_discovery_service.py` de la V1.
//!
//! "Algo triste", "para entrenar", "música de noche": la frase se lleva a pesos
//! por intención con las palabras y frases de la V1, cada pista con rasgos se
//! puntúa con las fórmulas de la V1 (rasgos básicos y, si los hay, los del análisis
//! con modelos), se quedan las que pasan de 0,35 y se reparten en secciones de
//! ocho sin repetir pistas.
//!
//! Dos diferencias con la V1, a propósito: las secciones viajan como
//! identificadores y la interfaz pone su título desde el diccionario (`check-i18n`),
//! y la activación del análisis solo cuenta si es de esta versión,
//! porque la de la V1 estaba recortada a 1 (ver `analisis.rs`).

use std::collections::BTreeMap;

use serde::Serialize;
use ts_rs::TS;

use crate::biblioteca::{self, PistaResumen};
use crate::catalogo::texto::para_comparacion;
use crate::db::BaseDeDatos;
use crate::error::{NsError, NsResult};

/// `MUSIC_DISCOVERY_MIN_CONFIDENCE` de la V1.
const CONFIANZA_MINIMA: f64 = 0.35;
/// Pistas por sección, como la V1.
const POR_SECCION: usize = 8;
/// Tope de lo que se pide: `MUSIC_DISCOVERY_DEFAULT_LIMIT` admite hasta 200.
pub const LIMITE_MAXIMO: u32 = 200;

/// Lo que se puede pedir.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub enum Intencion {
    Triste,
    Alegre,
    Fiesta,
    Entrenar,
    Concentrarse,
    Tranquila,
    Nocturna,
    Intensa,
    Suave,
    Rapida,
    Lenta,
}

use Intencion as I;

/// `KEYWORDS` de la V1, en su orden.
const PALABRAS: [(Intencion, &[&str]); 11] = [
    (
        I::Triste,
        &[
            "triste",
            "melanc",
            "bajon",
            "llorar",
            "sentimental",
            "nostalg",
            "sad",
            "blue",
        ],
    ),
    (
        I::Alegre,
        &[
            "feliz",
            "alegre",
            "positiva",
            "content",
            "happy",
            "uplifting",
            "animad",
            "animo",
            "optimista",
        ],
    ),
    (
        I::Fiesta,
        &[
            "fiesta", "party", "bail", "bailable", "dance", "club", "celebr", "limpiar",
        ],
    ),
    (
        I::Entrenar,
        &[
            "entren",
            "gym",
            "correr",
            "caminar",
            "energia",
            "energetic",
            "energetico",
            "energetica",
            "potente",
            "activo",
            "activa",
            "workout",
            "run",
            "running",
            "walk",
        ],
    ),
    (
        I::Concentrarse,
        &[
            "concentr",
            "estudi",
            "enfoque",
            "focus",
            "study",
            "trabajar",
            "trabajo",
            "productiv",
            "manejar",
            "conducir",
            "drive",
            "driving",
        ],
    ),
    (
        I::Tranquila,
        &[
            "chill", "tranquil", "relajad", "calma", "calm", "relax", "sueno", "dormir", "sleep",
            "cocinar", "romant",
        ],
    ),
    (
        I::Nocturna,
        &["oscur", "nocturn", "noche", "dark", "night", "sombr"],
    ),
    (
        I::Intensa,
        &["intens", "agresiv", "pesad", "fuerte", "hard", "aggressive"],
    ),
    (I::Suave, &["suave", "soft", "liger", "gentle"]),
    (
        I::Rapida,
        &["rapido", "veloz", "rapidas", "fast", "quick", "acelerad"],
    ),
    (I::Lenta, &["lento", "despacio", "slow", "pausad"]),
];

/// `PHRASE_HINTS` de la V1.
const FRASES: [(&str, Intencion, f64); 16] = [
    ("baja energia", I::Suave, 1.0),
    ("energia baja", I::Suave, 1.0),
    ("alta energia", I::Entrenar, 1.0),
    ("energia alta", I::Entrenar, 1.0),
    ("levantar animo", I::Alegre, 1.0),
    ("para manejar", I::Concentrarse, 0.95),
    ("para conducir", I::Concentrarse, 0.95),
    ("para caminar", I::Entrenar, 0.95),
    ("para trabajar", I::Concentrarse, 0.95),
    ("para estudiar", I::Concentrarse, 0.95),
    ("para dormir", I::Tranquila, 1.0),
    ("para cocinar", I::Tranquila, 0.9),
    ("para limpiar", I::Fiesta, 0.9),
    ("musica de noche", I::Nocturna, 1.0),
    ("musica para concentrarme", I::Concentrarse, 1.0),
    ("musica para fiesta", I::Fiesta, 1.0),
];

/// `parse_query`: los pesos de cada intención en la frase. Vacío si no se
/// entiende ninguna.
#[must_use]
pub fn interpretar(consulta: &str) -> BTreeMap<Intencion, f64> {
    let texto = para_comparacion(consulta);
    let mut pesos = BTreeMap::new();
    if texto.is_empty() {
        return pesos;
    }
    for (frase, i, peso) in FRASES {
        if texto.contains(frase) {
            let p = pesos.entry(i).or_insert(0.0f64);
            *p = p.max(peso);
        }
    }
    for (i, palabras) in PALABRAS {
        let aciertos = palabras.iter().filter(|p| texto.contains(**p)).count();
        if aciertos > 0 {
            pesos.insert(i, (0.75 + aciertos as f64 * 0.15).min(1.0));
        }
    }
    // "Baja energía" no es entrenar, salvo que se diga.
    if (texto.contains("baja energia") || texto.contains("energia baja"))
        && !["entren", "gym", "correr", "workout", "run", "caminar"]
            .iter()
            .any(|p| texto.contains(p))
    {
        pesos.remove(&I::Entrenar);
    }
    pesos
}

/// Lo que se mira de cada pista: los rasgos y, si los hay, los del análisis.
#[derive(Debug, Clone, Default)]
struct Metricas {
    energia: f64,
    melancolia: f64,
    valencia: f64,
    brillo: f64,
    fiesta: f64,
    bailable: f64,
    entrenar: f64,
    calma: f64,
    concentrarse: f64,
    noche: f64,
    oscuro: f64,
    agresiva: f64,
    bpm: f64,
    profundo: Option<Profundas>,
}

#[derive(Debug, Clone, Default)]
struct Profundas {
    triste: f64,
    feliz: f64,
    relajada: f64,
    agresiva: f64,
    fiesta: f64,
    bailable: f64,
    activacion: f64,
}

fn r01(v: f64) -> f64 {
    v.clamp(0.0, 1.0)
}

fn inv(v: f64) -> f64 {
    1.0 - r01(v)
}

impl Metricas {
    fn rapida(&self) -> f64 {
        r01(self.bpm / 180.0)
    }

    fn lenta(&self) -> f64 {
        inv(self.bpm / 160.0)
    }

    /// `_score_intent` de la V1.
    fn por_intencion(&self, i: Intencion) -> f64 {
        let d = self.profundo.clone().unwrap_or_default();
        match i {
            I::Triste => {
                0.45 * self.melancolia
                    + 0.25 * inv(self.valencia)
                    + 0.15 * self.calma
                    + 0.15 * d.triste
            }
            I::Alegre => {
                0.45 * self.valencia + 0.20 * self.energia + 0.20 * d.feliz + 0.15 * self.brillo
            }
            I::Fiesta => {
                0.35 * self.fiesta
                    + 0.25 * self.bailable
                    + 0.20 * self.energia
                    + 0.20 * d.fiesta.max(d.bailable)
            }
            I::Entrenar => {
                0.40 * self.entrenar
                    + 0.30 * self.energia
                    + 0.20 * r01(self.bpm / 170.0)
                    + 0.10 * d.activacion
            }
            I::Concentrarse | I::Tranquila => {
                0.35 * self.calma
                    + 0.30 * self.concentrarse
                    + 0.20 * d.relajada
                    + 0.15 * inv(self.agresiva)
            }
            I::Nocturna => 0.45 * self.noche + 0.35 * self.oscuro + 0.20 * self.melancolia,
            I::Intensa => {
                0.35 * self.agresiva + 0.30 * self.energia + 0.20 * d.agresiva + 0.15 * d.activacion
            }
            I::Suave => 0.45 * inv(self.energia) + 0.30 * self.calma + 0.25 * inv(self.agresiva),
            I::Rapida => 0.70 * self.rapida() + 0.30 * self.energia,
            I::Lenta => 0.65 * self.lenta() + 0.35 * self.calma,
        }
    }

    /// La media de las intenciones, cada una con su peso.
    fn puntuacion(&self, pesos: &BTreeMap<Intencion, f64>) -> f64 {
        let total: f64 = pesos
            .values()
            .map(|p| r01(*p))
            .sum::<f64>()
            .max(f64::MIN_POSITIVE);
        r01(pesos
            .iter()
            .map(|(i, p)| self.por_intencion(*i) * r01(*p) / total)
            .sum())
    }
}

/// Una sección de resultados. `id` es la clave de su título en el diccionario.
#[derive(Debug, Clone, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct Seccion {
    pub id: String,
    pub pistas: Vec<PistaResumen>,
}

#[derive(Debug, Clone, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct Descubrimiento {
    /// Se entendió una intención en la frase.
    pub entendida: bool,
    /// Lo que se entendió, en el orden del diccionario.
    pub intenciones: Vec<Intencion>,
    pub secciones: Vec<Seccion>,
    /// Cuántas pistas tienen rasgos: con cero, no hay con qué recomendar.
    pub analizadas: u32,
}

type Puntuador = fn(&Metricas) -> f64;

/// `_section_specs` de la V1: las secciones de cada intención, sin repetir.
fn secciones_de(intenciones: &[Intencion]) -> Vec<(&'static str, Puntuador)> {
    let mut v: Vec<(&'static str, Puntuador)> = Vec::new();
    let mut anadir = |id: &'static str, f: Puntuador| {
        if !v.iter().any(|(i, _)| *i == id) {
            v.push((id, f));
        }
    };
    for i in intenciones {
        match i {
            I::Fiesta => {
                anadir("masFiesteras", |m| m.fiesta);
                anadir("masBailables", |m| m.bailable);
                anadir("masRapidas", Metricas::rapida);
                anadir("energiaAlta", |m| m.energia);
            }
            I::Triste => {
                anadir("masMelancolicas", |m| m.melancolia);
                anadir("tristesSuaves", |m| m.melancolia * 0.65 + m.calma * 0.35);
                anadir("tristesConEnergia", |m| {
                    m.melancolia * 0.55 + m.energia * 0.45
                });
            }
            I::Entrenar => {
                anadir("masIntensas", |m| m.entrenar * 0.60 + m.energia * 0.40);
                anadir("ritmoAlto", Metricas::rapida);
                anadir("energiaParaMoverse", |m| {
                    m.energia * 0.55 + m.bailable * 0.45
                });
            }
            I::Concentrarse => {
                anadir("masEnfocadas", |m| m.concentrarse);
                anadir("tranquilasParaTrabajar", |m| {
                    m.concentrarse * 0.45 + m.calma * 0.45 + (1.0 - m.agresiva) * 0.10
                });
                anadir("bajaDistraccion", |m| {
                    m.calma * 0.55 + (1.0 - m.agresiva) * 0.45
                });
            }
            I::Nocturna => {
                anadir("masNocturnas", |m| m.noche);
                anadir("oscurasYCalmadas", |m| m.oscuro * 0.55 + m.calma * 0.45);
                anadir("suavesDeNoche", |m| {
                    m.noche * 0.45 + m.calma * 0.40 + (1.0 - m.energia) * 0.15
                });
            }
            I::Tranquila => {
                anadir("masTranquilas", |m| m.calma);
                anadir("suavesParaBajarRitmo", |m| {
                    m.calma * 0.55 + (1.0 - m.energia) * 0.45
                });
            }
            I::Alegre => {
                anadir("paraLevantarAnimo", |m| {
                    m.valencia * 0.60 + m.energia * 0.25 + m.brillo * 0.15
                });
                anadir("alegresYLigeras", |m| {
                    m.valencia * 0.65 + (1.0 - m.agresiva) * 0.35
                });
            }
            I::Intensa => {
                anadir("masIntensas", |m| m.agresiva * 0.55 + m.energia * 0.45);
                anadir("energiaAlta", |m| m.energia);
            }
            I::Suave => {
                anadir("masSuaves", |m| {
                    (1.0 - m.energia) * 0.45 + m.calma * 0.35 + (1.0 - m.agresiva) * 0.20
                });
                anadir("bajaEnergia", |m| 1.0 - m.energia);
            }
            I::Rapida => {
                anadir("masRapidas", Metricas::rapida);
                anadir("ritmoAlto", |m| m.rapida() * 0.70 + m.energia * 0.30);
            }
            I::Lenta => {
                anadir("masLentas", Metricas::lenta);
                anadir("bajaVelocidad", |m| m.lenta() * 0.70 + m.calma * 0.30);
            }
        }
    }
    v
}

fn filas(db: &BaseDeDatos) -> NsResult<Vec<(i64, Metricas)>> {
    let conn = db.conexion()?;
    let mut s = conn
        .prepare(
            "SELECT p.id, r.energia, r.melancolia, r.valencia, r.brillo, r.para_fiesta, r.bailabilidad,
                    r.para_entrenar, r.calma, r.para_concentrarse, r.para_la_noche, r.oscuridad,
                    r.agresividad, r.bpm,
                    a.feliz IS NOT NULL, a.triste, a.feliz, a.relajada, a.agresiva, a.fiesta, a.bailable,
                    CASE WHEN a.version = ?1 THEN a.activacion END
             FROM rasgos r
             JOIN pistas p ON p.id = r.pista_id AND p.estado = 'biblioteca'
             LEFT JOIN analisis_profundo a ON a.pista_id = p.id
             WHERE r.bpm IS NOT NULL OR r.energia IS NOT NULL",
        )
        .map_err(|_| NsError::StorageFailure)?;
    let v = |f: &rusqlite::Row<'_>, i: usize| -> rusqlite::Result<f64> {
        Ok(r01(f.get::<_, Option<f64>>(i)?.unwrap_or(0.0)))
    };
    let filas = s
        .query_map([crate::analisis::VERSION], |f| {
            let profundo = if f.get::<_, bool>(14)? {
                Some(Profundas {
                    triste: v(f, 15)?,
                    feliz: v(f, 16)?,
                    relajada: v(f, 17)?,
                    agresiva: v(f, 18)?,
                    fiesta: v(f, 19)?,
                    bailable: v(f, 20)?,
                    activacion: v(f, 21)?,
                })
            } else {
                None
            };
            Ok((
                f.get::<_, i64>(0)?,
                Metricas {
                    energia: v(f, 1)?,
                    melancolia: v(f, 2)?,
                    valencia: v(f, 3)?,
                    brillo: v(f, 4)?,
                    fiesta: v(f, 5)?,
                    bailable: v(f, 6)?,
                    entrenar: v(f, 7)?,
                    calma: v(f, 8)?,
                    concentrarse: v(f, 9)?,
                    noche: v(f, 10)?,
                    oscuro: v(f, 11)?,
                    agresiva: v(f, 12)?,
                    bpm: f.get::<_, Option<f64>>(13)?.unwrap_or(0.0),
                    profundo,
                },
            ))
        })
        .map_err(|_| NsError::StorageFailure)?
        .collect::<rusqlite::Result<Vec<_>>>()
        .map_err(|_| NsError::StorageFailure)?;
    Ok(filas)
}

/// Los `id` de las pistas que alcanzan `confianza_minima` para la frase, de mayor
/// a menor puntuación y hasta `limite`. Alimenta las playlists automáticas por
/// ánimo (`auto:mood:*`, con umbral 0,45 como en la V1).
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn candidatos_con_confianza(
    db: &BaseDeDatos,
    consulta: &str,
    confianza_minima: f64,
    limite: usize,
) -> NsResult<Vec<i64>> {
    let pesos = interpretar(consulta);
    if pesos.is_empty() {
        return Ok(Vec::new());
    }
    let mut candidatas: Vec<(f64, i64)> = filas(db)?
        .into_iter()
        .map(|(id, m)| (m.puntuacion(&pesos), id))
        .filter(|(p, _)| *p >= confianza_minima)
        .collect();
    candidatas.sort_by(|a, b| b.0.total_cmp(&a.0).then(a.1.cmp(&b.1)));
    Ok(candidatas
        .into_iter()
        .take(limite)
        .map(|(_, id)| id)
        .collect())
}

/// `discover`: las secciones para una frase, con `limite` pistas como mucho entre
/// todas las candidatas.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn descubrir(db: &BaseDeDatos, consulta: &str, limite: u32) -> NsResult<Descubrimiento> {
    let pesos = interpretar(consulta);
    let intenciones: Vec<Intencion> = pesos.keys().copied().collect();
    let todas = filas(db)?;
    let analizadas = u32::try_from(todas.len()).unwrap_or(u32::MAX);
    if pesos.is_empty() {
        return Ok(Descubrimiento {
            entendida: false,
            intenciones,
            secciones: Vec::new(),
            analizadas,
        });
    }
    let mut candidatas: Vec<(f64, i64, Metricas)> = todas
        .into_iter()
        .map(|(id, m)| (m.puntuacion(&pesos), id, m))
        .filter(|(p, _, _)| *p >= CONFIANZA_MINIMA)
        .collect();
    candidatas.sort_by(|a, b| b.0.total_cmp(&a.0).then(a.1.cmp(&b.1)));
    candidatas.truncate(limite.clamp(1, LIMITE_MAXIMO) as usize);

    let mut usadas = std::collections::HashSet::new();
    let mut secciones = Vec::new();
    for (id, puntuar) in secciones_de(&intenciones) {
        let mut orden: Vec<(f64, f64, i64)> = candidatas
            .iter()
            .map(|(p, pista, m)| (puntuar(m), *p, *pista))
            .filter(|(v, _, _)| *v > 0.0)
            .collect();
        orden.sort_by(|a, b| b.0.total_cmp(&a.0).then(b.1.total_cmp(&a.1)));
        let ids: Vec<i64> = orden
            .into_iter()
            .map(|(_, _, p)| p)
            .filter(|p| usadas.insert(*p))
            .take(POR_SECCION)
            .collect();
        if !ids.is_empty() {
            secciones.push(Seccion {
                id: id.to_owned(),
                pistas: biblioteca::resumenes(db, &ids)?,
            });
        }
    }
    if secciones.is_empty() && !candidatas.is_empty() {
        let ids: Vec<i64> = candidatas.iter().take(POR_SECCION).map(|c| c.1).collect();
        secciones.push(Seccion {
            id: "seleccionSugerida".to_owned(),
            pistas: biblioteca::resumenes(db, &ids)?,
        });
    }
    Ok(Descubrimiento {
        entendida: true,
        intenciones,
        secciones,
        analizadas,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn la_frase_se_entiende_como_en_la_v1() {
        let p = interpretar("Algo TRISTE y melancólico");
        assert_eq!(
            p.get(&I::Triste).copied(),
            Some(1.0),
            "dos palabras: 0,75 + 2·0,15, tope 1"
        );
        let p = interpretar("música para estudiar");
        assert_eq!(p.get(&I::Concentrarse).copied(), Some(0.9));
        let p = interpretar("algo de baja energía");
        assert!(p.contains_key(&I::Suave) && !p.contains_key(&I::Entrenar));
        let p = interpretar("baja energía para correr");
        assert!(p.contains_key(&I::Entrenar), "si se dice entrenar, cuenta");
        assert!(interpretar("Shakira").is_empty());
        assert!(interpretar("").is_empty());
    }

    fn base(pistas: &[(i64, f64, f64, f64)]) -> BaseDeDatos {
        let db = BaseDeDatos::en_memoria().unwrap();
        let conn = db.conexion().unwrap();
        for (id, energia, melancolia, bpm) in pistas {
            conn.execute(
                "INSERT INTO pistas (id, titulo, ruta) VALUES (?1, 't', ?1 || '.mp3')",
                [id],
            )
            .unwrap();
            conn.execute(
                "INSERT INTO rasgos (pista_id, version, bpm, energia, melancolia, valencia, calma,
                                     para_fiesta, bailabilidad, para_entrenar)
                 VALUES (?1, 'v', ?4, ?2, ?3, 1 - ?3, 1 - ?2, ?2, ?2, ?2)",
                rusqlite::params![id, energia, melancolia, bpm],
            )
            .unwrap();
        }
        drop(conn);
        db
    }

    #[test]
    fn las_tristes_salen_primero_y_ninguna_se_repite_entre_secciones() {
        let db = base(&[
            (1, 0.2, 0.95, 70.0),
            (2, 0.9, 0.05, 150.0),
            (3, 0.3, 0.80, 80.0),
            (4, 0.4, 0.70, 90.0),
        ]);
        let d = descubrir(&db, "algo triste", 25).unwrap();
        assert!(d.entendida);
        assert_eq!(d.intenciones, [I::Triste]);
        assert_eq!(d.secciones[0].id, "masMelancolicas");
        assert_eq!(d.secciones[0].pistas[0].id, 1);
        let mut vistas: Vec<i64> = d
            .secciones
            .iter()
            .flat_map(|s| s.pistas.iter().map(|p| p.id))
            .collect();
        assert!(!vistas.contains(&2), "la alegre no pasa de 0,35");
        let n = vistas.len();
        vistas.sort_unstable();
        vistas.dedup();
        assert_eq!(vistas.len(), n);
        assert_eq!(d.analizadas, 4);
    }

    #[test]
    fn sin_intencion_no_se_inventa_nada() {
        let db = base(&[(1, 0.5, 0.5, 100.0)]);
        let d = descubrir(&db, "los beatles", 25).unwrap();
        assert!(!d.entendida && d.secciones.is_empty());
    }

    #[test]
    fn la_activacion_del_analisis_de_la_v1_no_cuenta() {
        let db = base(&[(1, 0.5, 0.5, 100.0)]);
        db.conexion()
            .unwrap()
            .execute(
                "INSERT INTO analisis_profundo (pista_id, version, feliz, valencia, activacion)
                 VALUES (1, 'audio_intel_essentia_v2', 0.4, 1.0, 1.0)",
                [],
            )
            .unwrap();
        let m = filas(&db).unwrap().remove(0).1;
        let p = m.profundo.unwrap();
        assert_eq!((p.feliz, p.activacion), (0.4, 0.0));
    }
}
