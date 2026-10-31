//! El planificador de sesiones: `servicios/dj_privado/scheduler.py` y la carga de
//! candidatas de `persistencia.py`.
//!
//! Cada candidata se lleva a los ejes del DJ, se puntúa contra la intención (ejes,
//! focos y, con peso, el embedding), se filtra por las exclusiones y se elige una a
//! una siguiendo el arco narrativo: en cada hueco gana la que mejor combina su
//! puntuación (65 %) con lo que pide ese punto de la sesión (35 %). Un desempate de
//! una milésima sale del azar con semilla, que es el de Python (`azar.rs`) para que
//! la misma semilla dé la misma sesión que la V1.
//!
//! Sin el agregado de análisis, los ejes salen de los rasgos básicos y los que no se
//! pueden saber quedan neutros (0,5): ni favorecen ni hunden a la pista.

use std::collections::HashMap;

use super::azar::Azar;
use super::embeddings::RasgosPista;
use super::intencion::Intencion;
use super::narrativa;
use super::ontologia;
use crate::db::BaseDeDatos;
use crate::error::{NsError, NsResult};

const NEUTRO: f64 = 0.5;

/// `PistaCandidata`, con las columnas de la V2. Los comentarios dan el nombre de la
/// V1 cuando no es evidente.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct Candidata {
    pub id: i64,
    pub titulo: String,
    pub artista_nombre: String,
    pub album_titulo: String,
    pub artista_id: Option<i64>,
    pub album_id: Option<i64>,
    pub genero: String,
    pub duracion_seg: f64,
    pub favorita: bool,
    pub reproducciones: i64,
    pub bpm: Option<f64>,
    pub tonalidad: Option<String>,
    pub modo: Option<String>,
    pub energia: Option<f64>,
    /// `valence_proxy`.
    pub valencia: Option<f64>,
    /// `danceability_proxy`.
    pub bailabilidad: Option<f64>,
    /// `arousal_proxy`.
    pub activacion: Option<f64>,
    pub calma: Option<f64>,
    pub melancolia: Option<f64>,
    pub agresividad: Option<f64>,
    pub brillo: Option<f64>,
    pub oscuridad: Option<f64>,
    pub para_concentrarse: Option<f64>,
    pub para_entrenar: Option<f64>,
    pub para_fiesta: Option<f64>,
    pub para_la_noche: Option<f64>,
    /// Las cabezas del análisis profundo (`mood_*`).
    pub feliz: Option<f64>,
    pub triste: Option<f64>,
    pub relajada: Option<f64>,
    pub agresiva: Option<f64>,
    pub fiesta: Option<f64>,
    /// `danceability_model`.
    pub bailable_modelo: Option<f64>,
    /// `valence`, de DEAM.
    pub valencia_modelo: Option<f64>,
    /// Las etiquetas de estilo del análisis (`tags_json["tags_msd50"]`).
    pub etiquetas: Vec<(String, f64)>,
    /// Las etiquetas de ambiente con 0,4 o más (`vibe_tags`).
    pub ambiente: Vec<String>,
}

impl Candidata {
    /// `to_features_dict`, para el embedding: los rasgos con el nombre de la V1 y
    /// las etiquetas de ambiente, cada una con peso 1.
    #[must_use]
    pub fn rasgos(&self) -> RasgosPista {
        let numericos = [
            ("energy", self.energia),
            ("valence_proxy", self.valencia),
            ("danceability_proxy", self.bailabilidad),
            ("arousal_proxy", self.activacion),
            ("calmness_proxy", self.calma),
            ("melancholy_proxy", self.melancolia),
            ("aggressiveness_proxy", self.agresividad),
            ("brightness", self.brillo),
            ("darkness_proxy", self.oscuridad),
            ("focus_score_proxy", self.para_concentrarse),
            ("workout_score_proxy", self.para_entrenar),
            ("party_score_proxy", self.para_fiesta),
            ("night_score_proxy", self.para_la_noche),
            ("mood_happy", self.feliz),
            ("mood_sad", self.triste),
            ("mood_relaxed", self.relajada),
            ("mood_aggressive", self.agresiva),
            ("mood_party", self.fiesta),
            ("danceability_model", self.bailable_modelo),
            ("valence", self.valencia_modelo),
        ]
        .into_iter()
        .filter_map(|(k, v)| v.map(|v| (k, v)))
        .collect();
        RasgosPista {
            numericos,
            genero: Some(self.genero.clone()),
            etiquetas: self.ambiente.iter().map(|e| (e.clone(), 1.0)).collect(),
            titulo: self.titulo.clone(),
            artista: self.artista_nombre.clone(),
            album: self.album_titulo.clone(),
        }
    }
}

/// Los ejes de una pista, en el espacio de la intención; lo que falta vale 0,5.
#[derive(Debug, Clone, PartialEq)]
pub struct Ejes(Vec<(&'static str, f64)>);

impl Ejes {
    #[must_use]
    pub fn get(&self, eje: &str) -> f64 {
        self.0
            .iter()
            .find(|(k, _)| *k == eje)
            .map_or(NEUTRO, |(_, v)| *v)
    }
}

fn r01(v: f64) -> f64 {
    v.clamp(0.0, 1.0)
}

fn o_neutro(v: Option<f64>) -> f64 {
    v.map_or(NEUTRO, r01)
}

/// `extraer_ejes`. El modelo profundo gana a la aproximación por regla cuando hay
/// ambos; las voces, lo instrumental y los timbres salen de las etiquetas de estilo,
/// y sin ellas quedan neutros en vez de adivinarse.
#[must_use]
pub fn ejes(c: &Candidata) -> Ejes {
    let etiqueta = |claves: &[&str]| {
        let mut mejor = 0.0f64;
        for (nombre, puntuacion) in &c.etiquetas {
            let n = nombre.to_lowercase();
            if claves.iter().any(|k| n.contains(k)) && *puntuacion > mejor {
                mejor = *puntuacion;
            }
        }
        mejor
    };
    let o_etiqueta = |v: f64| if v == 0.0 { NEUTRO } else { r01(v) };
    let mut v = vec![
        ("energy", o_neutro(c.energia.or(c.activacion))),
        (
            "danceability",
            o_neutro(c.bailable_modelo.or(c.bailabilidad)),
        ),
        ("calmness", o_neutro(c.relajada.or(c.calma))),
        ("melancholy", o_neutro(c.triste.or(c.melancolia))),
        ("euphoria", o_neutro(c.feliz.or(c.valencia))),
        ("aggressiveness", o_neutro(c.agresiva.or(c.agresividad))),
        ("brightness", o_neutro(c.brillo)),
        ("darkness", o_neutro(c.oscuridad)),
        ("tension", o_neutro(c.agresividad)),
        ("focus_score", o_neutro(c.para_concentrarse)),
        ("workout_score", o_neutro(c.para_entrenar)),
        ("night_score", o_neutro(c.para_la_noche)),
        ("rhythmic_density", o_neutro(c.bailabilidad)),
        ("club_energy", o_neutro(c.fiesta.or(c.para_fiesta))),
        (
            "bass_weight",
            c.bailabilidad
                .zip(c.oscuridad)
                .map_or(NEUTRO, |(b, o)| (r01(b) + r01(o)) / 2.0),
        ),
    ];
    let femenina = etiqueta(&["female vocal"]);
    let masculina = etiqueta(&["male vocal"]);
    let instrumental = etiqueta(&["instrumental"]);
    if femenina > 0.0 || masculina > 0.0 || instrumental > 0.0 {
        let voz = femenina.max(masculina);
        if instrumental > 0.0 && voz == 0.0 {
            v.push(("vocal_focus", f64::max(0.0, 0.4 - instrumental * 0.4)));
            v.push(("instrumental_focus", r01(instrumental)));
        } else {
            v.push(("vocal_focus", r01(voz)));
            v.push(("instrumental_focus", f64::max(0.0, 1.0 - voz)));
        }
        v.push(("vocal_female", r01(femenina)));
        v.push(("vocal_male", r01(masculina)));
    } else {
        for e in [
            "vocal_focus",
            "instrumental_focus",
            "vocal_female",
            "vocal_male",
        ] {
            v.push((e, NEUTRO));
        }
    }
    v.push((
        "cinematic_level",
        o_etiqueta(etiqueta(&["classic", "soundtrack", "ambient"])),
    ));
    v.push(("orchestral_weight", o_etiqueta(etiqueta(&["classical"]))));
    v.push((
        "electronic_weight",
        o_etiqueta(etiqueta(&[
            "electronic",
            "electro",
            "house",
            "techno",
            "edm",
            "dance",
        ])),
    ));
    v.push((
        "acoustic_weight",
        o_etiqueta(etiqueta(&["acoustic", "folk"])),
    ));
    v.push(("storytelling", NEUTRO));
    Ejes(v)
}

/// `ScoreDetalle`.
#[derive(Debug, Clone)]
struct Detalle {
    indice: usize,
    ejes: Ejes,
    intencion: f64,
    total: f64,
    razones: Vec<String>,
}

/// `puntuar_pista`, con la similitud del embedding ya calculada.
fn puntuar(
    indice: usize,
    c: &Candidata,
    i: &Intencion,
    similitud: f64,
    peso_embedding: f64,
) -> Detalle {
    let ejes = ejes(c);
    let mut razones = Vec::new();
    let mut intencion = 0.0;
    if !i.axes.is_empty() {
        let norma = super::suma(i.axes.iter().map(|(_, v)| v.abs()));
        let norma = if norma == 0.0 { 1.0 } else { norma };
        for (eje, delta) in &i.axes {
            let aporte = (ejes.get(eje) - 0.5) * 2.0 * delta;
            intencion += aporte;
            if aporte.abs() >= 0.20 {
                let signo = if aporte > 0.0 { "+" } else { "-" };
                razones.push(format!("{signo}{eje}({aporte:+.2})"));
            }
        }
        intencion /= norma;
    }
    let mut bonus = 0.0;
    for foco in &i.focos {
        let Some(concepto) = ontologia::concepto(foco) else {
            continue;
        };
        let alineacion: f64 = concepto
            .ejes
            .iter()
            .map(|(e, d)| (ejes.get(e) - 0.5) * 2.0 * d)
            .fold(0.0, |a, x| a + x);
        if alineacion > 0.0 {
            let b = f64::min(0.15, alineacion / concepto.ejes.len().max(1) as f64);
            bonus += b;
            razones.push(format!("foco:{}(+{b:.2})", concepto.nombre));
        }
    }
    let total = (1.0 - peso_embedding) * (intencion + bonus) + peso_embedding * similitud;
    Detalle {
        indice,
        ejes,
        intencion: intencion + bonus,
        total,
        razones,
    }
}

/// `aplicar_exclusiones`: el género excluido, dicho o implícito en un concepto
/// negado, descarta; una etiqueta de ambiente que nombra lo negado divide entre dos.
fn excluir(detalles: Vec<Detalle>, candidatas: &[Candidata], i: &Intencion) -> Vec<Detalle> {
    let mut generos: Vec<String> = i
        .generos_excluidos
        .iter()
        .map(|g| g.to_lowercase())
        .collect();
    let negados: Vec<_> = i
        .exclusiones
        .iter()
        .filter_map(|n| ontologia::concepto(n))
        .collect();
    for c in &negados {
        generos.extend(c.generos.iter().map(|g| g.to_lowercase()));
    }
    detalles
        .into_iter()
        .filter_map(|mut d| {
            let c = &candidatas[d.indice];
            let genero = c.genero.to_lowercase();
            if !genero.is_empty() && generos.contains(&genero) {
                return None;
            }
            let ambiente: Vec<String> = c.ambiente.iter().map(|t| t.to_lowercase()).collect();
            for concepto in &negados {
                if concepto
                    .alias
                    .iter()
                    .any(|a| ambiente.contains(&a.to_lowercase()))
                {
                    d.total *= 0.5;
                    d.razones.push(format!("penalizado:{}", concepto.nombre));
                }
            }
            Some(d)
        })
        .collect()
}

/// `PistaSesionPlanificada`.
#[derive(Debug, Clone, PartialEq)]
pub struct Planificada {
    pub pista: Candidata,
    pub posicion: usize,
    pub puntuacion: f64,
    pub puntuacion_intencion: f64,
    pub puntuacion_curva: f64,
    pub razones: Vec<String>,
}

#[derive(Debug, Clone, Copy)]
pub struct Opciones {
    pub duracion_min: u32,
    pub peso_embedding: f64,
    pub max_por_artista: usize,
    pub semilla: Option<i64>,
    pub pool_top_k: usize,
}

/// `planificar_sesion`. `similitud` da el coseno entre el pedido y cada pista; solo
/// se llama si el embedding pesa.
pub fn planificar(
    candidatas: &[Candidata],
    i: &Intencion,
    o: &Opciones,
    similitud: &mut dyn FnMut(&Candidata) -> f64,
) -> Vec<Planificada> {
    let mut azar = o.semilla.map_or_else(Azar::sin_semilla, Azar::con_semilla);
    let detalles = candidatas
        .iter()
        .enumerate()
        .map(|(k, c)| {
            let s = if o.peso_embedding > 0.0 {
                similitud(c)
            } else {
                0.0
            };
            puntuar(k, c, i, s, o.peso_embedding)
        })
        .collect();
    let mut vivas = excluir(detalles, candidatas, i);
    // Estable, como `list.sort`: con la misma puntuación se queda el orden de carga.
    // `partial_cmp` y no `total_cmp`, que separaría 0 y -0 donde Python no lo hace.
    vivas.sort_by(|a, b| {
        b.total
            .partial_cmp(&a.total)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    vivas.truncate(o.pool_top_k.max(10));

    let perfil = narrativa::perfil(i);
    let objetivo = f64::from(o.duracion_min) * 60.0;
    let tolerancia = objetivo + objetivo * 0.05;
    let mut por_artista: HashMap<i64, usize> = HashMap::new();
    let mut acumulada = 0.0;
    let mut elegidas = Vec::new();
    while !vivas.is_empty() {
        let t = f64::min(1.0, acumulada / f64::max(1.0, objetivo));
        let meta = narrativa::objetivos(&perfil, t);
        if acumulada >= tolerancia {
            break;
        }
        let mut mejor: Option<(usize, f64)> = None;
        let mut mejor_puntaje = f64::NEG_INFINITY;
        for (k, d) in vivas.iter().enumerate() {
            let c = &candidatas[d.indice];
            if c.artista_id
                .is_some_and(|a| por_artista.get(&a).copied().unwrap_or(0) >= o.max_por_artista)
            {
                continue;
            }
            let e = &d.ejes;
            let distancia = (e.get("energy") - meta.energia).abs() * 0.40
                + (e.get("tension") - meta.tension).abs() * 0.20
                + (e.get("rhythmic_density") - meta.densidad).abs() * 0.15
                + (e.get("brightness") - meta.brillo).abs() * 0.10
                + (e.get("calmness") - meta.calma).abs() * 0.15;
            let puntaje = 0.65 * d.total + 0.35 * (1.0 - distancia) + azar.uniforme(-0.001, 0.001);
            if puntaje > mejor_puntaje {
                mejor_puntaje = puntaje;
                mejor = Some((k, distancia));
            }
        }
        let Some((k, distancia)) = mejor else {
            break;
        };
        let d = vivas.remove(k);
        let c = &candidatas[d.indice];
        if let Some(a) = c.artista_id {
            *por_artista.entry(a).or_insert(0) += 1;
        }
        let fase = perfil[narrativa::fase_en(&perfil, t)].nombre;
        let mut razones = d.razones;
        razones.push(format!("fase:{fase}"));
        razones.push(format!("d_perfil={distancia:.2}"));
        elegidas.push(Planificada {
            pista: c.clone(),
            posicion: elegidas.len(),
            puntuacion: d.total,
            puntuacion_intencion: d.intencion,
            puntuacion_curva: f64::max(0.0, 1.0 - distancia),
            razones,
        });
        acumulada += c.duracion_seg;
        if elegidas.len() >= 200 {
            break;
        }
    }
    elegidas
}

/// `cargar_candidatos`: las pistas de la biblioteca con sus rasgos, en orden de id
/// y hasta `limite`, sin las de `excluir`. Con `solo_analizadas`, solo las que
/// tienen rasgos básicos.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base falla.
pub fn cargar(
    db: &BaseDeDatos,
    limite: usize,
    excluir: &[i64],
    solo_analizadas: bool,
) -> NsResult<Vec<Candidata>> {
    let conn = db.conexion()?;
    let sql = format!(
        "SELECT p.id, p.titulo, p.artista_nombre, p.album_titulo, p.artista_id, p.album_id,
                COALESCE(p.genero, ''), COALESCE(p.duracion_seg, 0), p.favorita, p.reproducciones,
                r.bpm, r.tonalidad, r.modo, r.energia, r.valencia, r.bailabilidad, r.activacion,
                r.calma, r.melancolia, r.agresividad, r.brillo, r.oscuridad, r.para_concentrarse,
                r.para_entrenar, r.para_fiesta, r.para_la_noche,
                a.feliz, a.triste, a.relajada, a.agresiva, a.fiesta, a.bailable, a.valencia,
                a.etiquetas
         FROM pistas p
         LEFT JOIN rasgos r ON r.pista_id = p.id
         LEFT JOIN analisis_profundo a ON a.pista_id = p.id
         WHERE p.estado = 'biblioteca'
           AND p.id NOT IN (SELECT value FROM json_each(?1)) {}
         ORDER BY p.id LIMIT ?2",
        if solo_analizadas {
            "AND r.energia IS NOT NULL"
        } else {
            ""
        }
    );
    let excluir = serde_json::to_string(excluir).unwrap_or_else(|_| "[]".to_owned());
    let mut s = conn.prepare(&sql).map_err(|_| NsError::StorageFailure)?;
    let mut candidatas = s
        .query_map(rusqlite::params![excluir, limite as i64], |f| {
            let etiquetas: Option<String> = f.get(33)?;
            Ok(Candidata {
                id: f.get(0)?,
                titulo: f.get(1)?,
                artista_nombre: f.get(2)?,
                album_titulo: f.get(3)?,
                artista_id: f.get(4)?,
                album_id: f.get(5)?,
                genero: f.get(6)?,
                duracion_seg: f.get(7)?,
                favorita: f.get(8)?,
                reproducciones: f.get(9)?,
                bpm: f.get(10)?,
                tonalidad: f.get(11)?,
                modo: f.get(12)?,
                energia: f.get(13)?,
                valencia: f.get(14)?,
                bailabilidad: f.get(15)?,
                activacion: f.get(16)?,
                calma: f.get(17)?,
                melancolia: f.get(18)?,
                agresividad: f.get(19)?,
                brillo: f.get(20)?,
                oscuridad: f.get(21)?,
                para_concentrarse: f.get(22)?,
                para_entrenar: f.get(23)?,
                para_fiesta: f.get(24)?,
                para_la_noche: f.get(25)?,
                feliz: f.get(26)?,
                triste: f.get(27)?,
                relajada: f.get(28)?,
                agresiva: f.get(29)?,
                fiesta: f.get(30)?,
                bailable_modelo: f.get(31)?,
                valencia_modelo: f.get(32)?,
                etiquetas: etiquetas
                    .and_then(|e| serde_json::from_str(&e).ok())
                    .unwrap_or_default(),
                ambiente: Vec::new(),
            })
        })
        .map_err(|_| NsError::StorageFailure)?
        .collect::<rusqlite::Result<Vec<_>>>()
        .map_err(|_| NsError::StorageFailure)?;

    let mut s = conn
        .prepare(
            "SELECT pista_id, etiqueta FROM etiquetas_ambiente WHERE puntuacion >= 0.4
             ORDER BY pista_id, etiqueta, fuente",
        )
        .map_err(|_| NsError::StorageFailure)?;
    let mut ambiente: HashMap<i64, Vec<String>> = HashMap::new();
    for fila in s
        .query_map([], |f| Ok((f.get::<_, i64>(0)?, f.get::<_, String>(1)?)))
        .map_err(|_| NsError::StorageFailure)?
    {
        let (id, etiqueta) = fila.map_err(|_| NsError::StorageFailure)?;
        ambiente.entry(id).or_default().push(etiqueta);
    }
    for c in &mut candidatas {
        if let Some(a) = ambiente.remove(&c.id) {
            c.ambiente = a;
        }
    }
    Ok(candidatas)
}

#[cfg(test)]
mod pruebas {
    use super::*;

    #[test]
    fn la_carga_trae_rasgos_analisis_y_ambiente_y_respeta_las_excluidas() {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO pistas (id, titulo, ruta, genero, duracion_seg) VALUES
                     (1, 'a', 'a.mp3', 'Rock', 200), (2, 'b', 'b.mp3', NULL, NULL),
                     (3, 'c', 'c.mp3', 'Pop', 180);
                 INSERT INTO pistas (id, titulo, ruta, estado) VALUES (4, 'd', 'd.mp3', 'duplicado');
                 INSERT INTO rasgos (pista_id, version, bpm, tonalidad, modo, energia)
                     VALUES (1, 'v', 120, 'A', 'minor', 0.8);
                 INSERT INTO analisis_profundo (pista_id, version, feliz, etiquetas)
                     VALUES (1, 'v', 0.7, '[[\"rock\", 0.5]]');
                 INSERT INTO etiquetas_ambiente (pista_id, etiqueta, fuente, puntuacion, confianza, version)
                     VALUES (1, 'fiesta', 'basic_rules', 0.6, 0.6, 'v'),
                            (1, 'triste', 'basic_rules', 0.39, 0.39, 'v');",
            )
            .unwrap();
        let todas = cargar(&db, 10, &[3], false).unwrap();
        assert_eq!(todas.iter().map(|c| c.id).collect::<Vec<_>>(), vec![1, 2]);
        let a = &todas[0];
        assert_eq!(
            (a.bpm, a.tonalidad.as_deref(), a.energia),
            (Some(120.0), Some("A"), Some(0.8))
        );
        assert_eq!(a.feliz, Some(0.7));
        assert_eq!(a.etiquetas, vec![("rock".to_owned(), 0.5)]);
        assert_eq!(a.ambiente, vec!["fiesta".to_owned()]);
        assert_eq!((todas[1].genero.as_str(), todas[1].duracion_seg), ("", 0.0));
        let analizadas = cargar(&db, 10, &[], true).unwrap();
        assert_eq!(analizadas.len(), 1);
    }

    // Las propiedades de `tests/test_dj_privado_scheduler.py` de la V1.

    fn pista(id: i64, artista: i64, energia: f64) -> Candidata {
        Candidata {
            id,
            artista_id: Some(artista),
            genero: "pop".to_owned(),
            duracion_seg: 240.0,
            energia: Some(energia),
            ..Candidata::default()
        }
    }

    fn opciones(minutos: u32, semilla: i64) -> Opciones {
        Opciones {
            duracion_min: minutos,
            peso_embedding: 0.25,
            max_por_artista: 2,
            semilla: Some(semilla),
            pool_top_k: 200,
        }
    }

    fn determinista(i: &Intencion) -> impl FnMut(&Candidata) -> f64 {
        use crate::dj::embeddings::{Determinista, Proveedor};
        let pedido = Determinista.de_texto(&i.prompt);
        move |c| crate::dj::embeddings::coseno(&pedido, &Determinista.de_pista(&c.rasgos()))
    }

    #[test]
    fn la_pista_alineada_con_el_pedido_puntua_mas() {
        let i = crate::dj::intencion::interpretar("para concentrarme", 60);
        let tranquila = Candidata {
            energia: Some(0.2),
            calma: Some(0.95),
            para_concentrarse: Some(0.9),
            agresividad: Some(0.05),
            etiquetas: vec![
                ("ambient".to_owned(), 0.9),
                ("instrumental".to_owned(), 0.9),
            ],
            ..Candidata::default()
        };
        let fiesta = Candidata {
            energia: Some(0.95),
            calma: Some(0.1),
            para_concentrarse: Some(0.1),
            agresividad: Some(0.7),
            para_fiesta: Some(0.9),
            ..Candidata::default()
        };
        assert!(
            puntuar(0, &tranquila, &i, 0.0, 0.25).intencion
                > puntuar(1, &fiesta, &i, 0.0, 0.25).intencion
        );
    }

    #[test]
    fn sin_candidatas_no_hay_sesion_y_sin_pedido_si() {
        let i = crate::dj::intencion::interpretar("", 8);
        assert!(planificar(&[], &i, &opciones(8, 1), &mut |_| 0.0).is_empty());
        let pool: Vec<_> = (0..6).map(|k| pista(k, k % 3, 0.5)).collect();
        assert!(!planificar(&pool, &i, &opciones(8, 1), &mut determinista(&i)).is_empty());
    }

    #[test]
    fn un_artista_no_pasa_de_su_tope() {
        let i = crate::dj::intencion::interpretar("pop", 30);
        let pool: Vec<_> = (1..6).map(|k| pista(k, 7, 0.6)).collect();
        let s = planificar(&pool, &i, &opciones(30, 1), &mut determinista(&i));
        assert_eq!(s.len(), 2);
    }

    #[test]
    fn entrenar_favorece_las_pistas_energicas() {
        let i = crate::dj::intencion::interpretar("para entrenar duro", 14);
        let pool: Vec<_> = [(0.20, 0.3), (0.85, 0.85), (0.90, 0.9), (0.50, 0.5)]
            .iter()
            .enumerate()
            .map(|(k, (e, w))| Candidata {
                para_entrenar: Some(*w),
                ..pista(k as i64, k as i64, *e)
            })
            .collect();
        let s = planificar(&pool, &i, &opciones(14, 7), &mut determinista(&i));
        let media = s
            .iter()
            .map(|p| p.pista.energia.unwrap_or(0.5))
            .sum::<f64>()
            / s.len() as f64;
        assert!(media > 0.55, "{media}");
    }

    #[test]
    fn la_misma_semilla_da_la_misma_sesion() {
        let i = crate::dj::intencion::interpretar("algo energetico", 20);
        let pool: Vec<_> = (0..20)
            .map(|k| pista(k, k % 5, 0.5 + (k % 5) as f64 * 0.1))
            .collect();
        let ids = |semilla| {
            planificar(&pool, &i, &opciones(20, semilla), &mut determinista(&i))
                .iter()
                .map(|p| p.pista.id)
                .collect::<Vec<_>>()
        };
        assert_eq!(ids(123), ids(123));
    }

    #[test]
    fn sin_analisis_los_ejes_quedan_neutros() {
        let e = ejes(&Candidata::default());
        for eje in [
            "energy",
            "vocal_focus",
            "cinematic_level",
            "bass_weight",
            "storytelling",
        ] {
            assert_eq!(e.get(eje), NEUTRO, "{eje}");
        }
    }

    #[test]
    fn el_genero_negado_descarta_y_el_ambiente_negado_divide_entre_dos() {
        let i = crate::dj::intencion::interpretar("bailable sin reggaeton, sin tristeza", 30);
        let base = Candidata {
            duracion_seg: 200.0,
            energia: Some(0.7),
            ..Candidata::default()
        };
        let pool = vec![
            Candidata {
                id: 1,
                genero: "Reggaeton".to_owned(),
                ..base.clone()
            },
            Candidata {
                id: 2,
                ..base.clone()
            },
            Candidata {
                id: 3,
                ambiente: vec!["triste".to_owned()],
                ..base.clone()
            },
        ];
        let o = Opciones {
            duracion_min: 30,
            peso_embedding: 0.0,
            max_por_artista: 2,
            semilla: Some(1),
            pool_top_k: 250,
        };
        let s = planificar(&pool, &i, &o, &mut |_| 0.0);
        assert!(s.iter().all(|p| p.pista.id != 1));
        let (dos, tres) = (
            s.iter().find(|p| p.pista.id == 2).unwrap(),
            s.iter().find(|p| p.pista.id == 3).unwrap(),
        );
        assert!(tres.razones.iter().any(|r| r.starts_with("penalizado:")));
        assert!((tres.puntuacion - dos.puntuacion * 0.5).abs() < 1e-12);
    }
}
