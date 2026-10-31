//! El constructor de sesiones: `servicios/dj_privado/constructor.py`.
//!
//! Una sesión se construye por bloques: el primero, de ocho pistas, para que suene
//! enseguida; los siguientes, de doce, hasta cubrir la duración pedida. Cada bloque
//! planifica sobre lo que queda del pool, reordena por transiciones y descuenta los
//! solapamientos de la duración. La sesión está completa al llegar al 97 %.

use std::collections::{HashMap, HashSet};

use serde_json::json;

use super::embeddings::{self, Proveedor};
use super::intencion::Intencion;
use super::narrativa;
use super::planificador::{self, Candidata, Opciones, Planificada};
use super::transiciones::{self, Transicion};

/// `OpcionesConstructor`, con los valores de la V1.
#[derive(Debug, Clone, Copy)]
pub struct Ajustes {
    pub bloque_inicial: usize,
    pub bloque_siguiente: usize,
    pub max_por_artista: usize,
    pub peso_embedding: f64,
    pub pool_top_k: usize,
    pub refinar_transiciones: bool,
    pub semilla: Option<i64>,
}

impl Default for Ajustes {
    fn default() -> Self {
        Self {
            bloque_inicial: 8,
            bloque_siguiente: 12,
            max_por_artista: 2,
            peso_embedding: 0.20,
            pool_top_k: 250,
            refinar_transiciones: true,
            semilla: None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Corte {
    ObjetivoCumplido,
    PoolAgotado,
    BloqueLleno,
}

impl Corte {
    #[must_use]
    pub const fn como_v1(self) -> &'static str {
        match self {
            Self::ObjetivoCumplido => "objetivo_cumplido",
            Self::PoolAgotado => "pool_agotado",
            Self::BloqueLleno => "bloque_lleno",
        }
    }
}

/// `BloqueConstruido`. `transiciones[k]` va de `pistas[k]` a `pistas[k + 1]`.
#[derive(Debug, Clone)]
pub struct Bloque {
    pub pistas: Vec<Planificada>,
    pub transiciones: Vec<Transicion>,
    pub duracion_seg: f64,
    pub completado: bool,
    pub corte: Corte,
}

pub struct Constructor {
    intencion: Intencion,
    ajustes: Ajustes,
    pool: Vec<Candidata>,
    consumidas: HashSet<i64>,
    posicion: usize,
    acumulada: f64,
    estilo: String,
    proveedor: Box<dyn Proveedor + Send>,
    /// El embedding del pedido y la similitud de cada pista, que no cambian en toda
    /// la sesión: la V1 los recalculaba en cada bloque, y con MiniLM eso es una
    /// inferencia por pista y bloque.
    pedido: Option<Vec<f64>>,
    similitudes: HashMap<i64, f64>,
}

impl Constructor {
    #[must_use]
    pub fn new(
        intencion: Intencion,
        ajustes: Ajustes,
        pool: Vec<Candidata>,
        proveedor: Box<dyn Proveedor + Send>,
    ) -> Self {
        let estilo = transiciones::estilo(&intencion.estilo_transicion);
        Self {
            intencion,
            ajustes,
            pool,
            consumidas: HashSet::new(),
            posicion: 0,
            acumulada: 0.0,
            estilo,
            proveedor,
            pedido: None,
            similitudes: HashMap::new(),
        }
    }

    /// `marcar_consumidos`: para retomar una sesión sin repetir lo ya planificado.
    pub fn marcar_consumidas(&mut self, ids: impl IntoIterator<Item = i64>) {
        self.consumidas.extend(ids);
    }

    #[must_use]
    pub const fn duracion_acumulada_seg(&self) -> f64 {
        self.acumulada
    }

    #[must_use]
    pub fn proveedor_real(&self) -> bool {
        self.proveedor.es_real()
    }

    /// `construir_bloque`.
    pub fn bloque(&mut self, inicial: bool) -> Bloque {
        let maximo = if inicial {
            self.ajustes.bloque_inicial
        } else {
            self.ajustes.bloque_siguiente
        };
        let objetivo = f64::from(self.intencion.duracion_minutos) * 60.0;
        let restante = f64::max(0.0, objetivo - self.acumulada);
        let vacio = |completado, corte| Bloque {
            pistas: Vec::new(),
            transiciones: Vec::new(),
            duracion_seg: 0.0,
            completado,
            corte,
        };
        if restante <= 0.0 && !inicial {
            return vacio(true, Corte::ObjetivoCumplido);
        }
        let disponibles: Vec<Candidata> = self
            .pool
            .iter()
            .filter(|c| !self.consumidas.contains(&c.id))
            .cloned()
            .collect();
        if disponibles.is_empty() {
            return vacio(false, Corte::PoolAgotado);
        }
        // `int(round(...))` de Python redondea a la mitad par.
        let minutos = f64::min(restante / 60.0, maximo as f64 * 4.0).round_ties_even();
        let opciones = Opciones {
            duracion_min: (minutos as u32).max(1),
            peso_embedding: self.ajustes.peso_embedding,
            max_por_artista: self.ajustes.max_por_artista,
            semilla: self.ajustes.semilla,
            pool_top_k: self.ajustes.pool_top_k,
        };
        let pedido = self
            .pedido
            .get_or_insert_with(|| self.proveedor.de_texto(&self.intencion.prompt))
            .clone();
        let (proveedor, similitudes) = (&mut self.proveedor, &mut self.similitudes);
        let mut similitud = |c: &Candidata| {
            *similitudes
                .entry(c.id)
                .or_insert_with(|| embeddings::coseno(&pedido, &proveedor.de_pista(&c.rasgos())))
        };
        let mut planificadas =
            planificador::planificar(&disponibles, &self.intencion, &opciones, &mut similitud);
        planificadas.truncate(maximo);

        let transiciones = if self.ajustes.refinar_transiciones && planificadas.len() >= 3 {
            let mut orden: Vec<Candidata> = planificadas.iter().map(|p| p.pista.clone()).collect();
            let t = transiciones::refinar(&mut orden, &self.estilo);
            let mut previas: HashMap<i64, Planificada> =
                planificadas.drain(..).map(|p| (p.pista.id, p)).collect();
            planificadas = orden.iter().filter_map(|c| previas.remove(&c.id)).collect();
            t
        } else {
            let orden: Vec<Candidata> = planificadas.iter().map(|p| p.pista.clone()).collect();
            transiciones::entre(&orden, &self.estilo)
        };
        for (k, p) in planificadas.iter_mut().enumerate() {
            p.posicion = self.posicion + k;
        }

        let bruta = super::suma(planificadas.iter().map(|p| p.pista.duracion_seg));
        let solapes = super::suma(transiciones.iter().map(|t| t.solapamiento_seg));
        let duracion = f64::max(0.0, bruta - solapes);
        self.acumulada += duracion;
        self.consumidas
            .extend(planificadas.iter().map(|p| p.pista.id));
        self.posicion += planificadas.len();
        let completado = self.acumulada >= objetivo * 0.97;
        let corte = if planificadas.is_empty() {
            Corte::PoolAgotado
        } else if completado {
            Corte::ObjetivoCumplido
        } else {
            Corte::BloqueLleno
        };
        Bloque {
            pistas: planificadas,
            transiciones,
            duracion_seg: duracion,
            completado,
            corte,
        }
    }
}

/// `resumen_sesion`: lo que guarda `dj_sesiones.resumen`, con las claves de la V1.
#[must_use]
pub fn resumen(bloques: &[Bloque], i: &Intencion) -> serde_json::Value {
    let pistas: Vec<&Planificada> = bloques.iter().flat_map(|b| &b.pistas).collect();
    let duracion = super::suma(bloques.iter().map(|b| b.duracion_seg));
    let mut artistas: Vec<&str> = Vec::new();
    let (mut inicial, mut final_) = (None, None);
    let mut suma = 0.0;
    for p in &pistas {
        suma += p.puntuacion;
        let nombre = p.pista.artista_nombre.as_str();
        if !nombre.is_empty() && !artistas.contains(&nombre) {
            artistas.push(nombre);
        }
        if let Some(e) = p.pista.energia {
            inicial.get_or_insert(e);
            final_ = Some(e);
        }
    }
    let promedio = if pistas.is_empty() {
        0.0
    } else {
        suma / pistas.len() as f64
    };
    let transiciones: Vec<&Transicion> = bloques.iter().flat_map(|b| &b.transiciones).collect();
    json!({
        "total_pistas": pistas.len(),
        "duracion_seg": super::redondear(duracion, 1),
        "duracion_min": super::redondear(duracion / 60.0, 1),
        "artistas_distintos": artistas.len(),
        "artistas_muestra": artistas.iter().take(10).collect::<Vec<_>>(),
        "energia_inicial": inicial,
        "energia_final": final_,
        "score_promedio": super::redondear(promedio, 3),
        "transiciones_buenas": transiciones.iter().filter(|t| t.puntuacion >= 0.7).count(),
        "transiciones_total": transiciones.len(),
        "curva_energia": i.curva_energia,
        "estilo_transicion": serde_json::to_value(OrdenV1(&i.estilo_transicion)).unwrap_or_default(),
        "focos": i.focos,
        "exclusiones": i.exclusiones,
        "perfil_narrativo": narrativa::a_json(&narrativa::perfil(i)),
    })
}

/// El mapa de estilos con el serializador de la intención.
struct OrdenV1<'a>(&'a super::ontologia::Mapa);

impl serde::Serialize for OrdenV1<'_> {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        super::ontologia::objeto::serialize(self.0, s)
    }
}

#[cfg(test)]
mod pruebas {
    use super::*;
    use crate::dj::embeddings::Determinista;
    use crate::dj::intencion;

    fn doradas() -> serde_json::Value {
        serde_json::from_str(include_str!("doradas_sesion.json")).expect("doradas")
    }

    fn opt(v: &serde_json::Value) -> Option<f64> {
        v.as_f64()
    }

    /// Las candidatas sintéticas de las doradas, con los nombres de la V1.
    fn candidatas(d: &serde_json::Value) -> Vec<Candidata> {
        d["pistas"]
            .as_array()
            .expect("pistas")
            .iter()
            .map(|p| {
                let tags: serde_json::Value =
                    serde_json::from_str(p["tags_json"].as_str().unwrap_or("{}")).expect("tags");
                Candidata {
                    id: p["id"].as_i64().expect("id"),
                    titulo: p["titulo"].as_str().unwrap_or_default().to_owned(),
                    artista_nombre: p["artista_nombre"].as_str().unwrap_or_default().to_owned(),
                    album_titulo: p["album_titulo"].as_str().unwrap_or_default().to_owned(),
                    artista_id: p["artista_id"].as_i64(),
                    album_id: p["album_id"].as_i64(),
                    genero: p["genero"].as_str().unwrap_or_default().to_owned(),
                    duracion_seg: p["duracion_seg"].as_f64().unwrap_or(0.0),
                    favorita: p["favorita"].as_bool().unwrap_or(false),
                    reproducciones: p["veces_reproducida"].as_i64().unwrap_or(0),
                    bpm: opt(&p["bpm"]),
                    tonalidad: p["key_name"].as_str().map(str::to_owned),
                    modo: p["mode"].as_str().map(str::to_owned),
                    energia: opt(&p["energy"]),
                    valencia: opt(&p["valence_proxy"]),
                    bailabilidad: opt(&p["danceability_proxy"]),
                    activacion: opt(&p["arousal_proxy"]),
                    calma: opt(&p["calmness_proxy"]),
                    melancolia: opt(&p["melancholy_proxy"]),
                    agresividad: opt(&p["aggressiveness_proxy"]),
                    brillo: opt(&p["brightness"]),
                    oscuridad: opt(&p["darkness_proxy"]),
                    para_concentrarse: opt(&p["focus_score_proxy"]),
                    para_entrenar: opt(&p["workout_score_proxy"]),
                    para_fiesta: opt(&p["party_score_proxy"]),
                    para_la_noche: opt(&p["night_score_proxy"]),
                    feliz: opt(&p["mood_happy"]),
                    triste: opt(&p["mood_sad"]),
                    relajada: opt(&p["mood_relaxed"]),
                    agresiva: opt(&p["mood_aggressive"]),
                    fiesta: opt(&p["mood_party"]),
                    bailable_modelo: opt(&p["danceability_model"]),
                    valencia_modelo: opt(&p["valence"]),
                    etiquetas: tags["tags_msd50"]
                        .as_array()
                        .map(|l| {
                            l.iter()
                                .map(|t| {
                                    (
                                        t["label"].as_str().unwrap_or_default().to_owned(),
                                        t["score"].as_f64().unwrap_or(0.0),
                                    )
                                })
                                .collect()
                        })
                        .unwrap_or_default(),
                    ambiente: serde_json::from_value(p["vibe_tags"].clone()).expect("vibe"),
                }
            })
            .collect()
    }

    #[test]
    fn con_la_misma_semilla_la_sesion_es_la_de_la_v1() {
        let d = doradas();
        let pool = candidatas(&d);
        for s in d["sesiones"].as_array().expect("sesiones") {
            let prompt = s["prompt"].as_str().expect("prompt");
            let i = intencion::interpretar(prompt, s["minutos"].as_u64().expect("minutos") as u32);
            let ajustes = Ajustes {
                semilla: s["semilla"].as_i64(),
                ..Ajustes::default()
            };
            let mut c = Constructor::new(i.clone(), ajustes, pool.clone(), Box::new(Determinista));
            let mut bloques = Vec::new();
            for (n, esperado) in s["bloques"].as_array().expect("bloques").iter().enumerate() {
                let b = c.bloque(n == 0);
                let pistas: Vec<serde_json::Value> = b
                    .pistas
                    .iter()
                    .map(|p| {
                        json!({
                            "id": p.pista.id,
                            "posicion": p.posicion,
                            "score_total": p.puntuacion,
                            "score_intent": p.puntuacion_intencion,
                            "score_curva": p.puntuacion_curva,
                            "razones": p.razones,
                        })
                    })
                    .collect();
                assert_eq!(
                    serde_json::Value::from(pistas),
                    esperado["pistas"],
                    "{prompt}, bloque {n}"
                );
                let t: Vec<_> = b.transiciones.iter().map(Transicion::a_json).collect();
                assert_eq!(
                    serde_json::Value::from(t),
                    esperado["transiciones"],
                    "{prompt}"
                );
                assert_eq!(json!(b.duracion_seg), esperado["duracion_seg"], "{prompt}");
                assert_eq!(json!(b.completado), esperado["completado"], "{prompt}");
                assert_eq!(b.corte.como_v1(), esperado["motivo"], "{prompt}");
                bloques.push(b);
            }
            assert_eq!(resumen(&bloques, &i), s["resumen"], "{prompt}");
        }
    }

    #[test]
    fn una_sesion_no_repite_pistas_y_cada_bloque_respeta_dos_por_artista() {
        let pool = candidatas(&doradas());
        let i = intencion::interpretar("fiesta con mucha energia", 120);
        let mut c = Constructor::new(i, Ajustes::default(), pool, Box::new(Determinista));
        let mut ids = HashSet::new();
        for n in 0..20 {
            let b = c.bloque(n == 0);
            // El tope es por bloque, como en la V1: cada bloque planifica de cero
            // sobre lo que queda del pool.
            let mut artistas: HashMap<i64, usize> = HashMap::new();
            for p in &b.pistas {
                assert!(ids.insert(p.pista.id), "repetida");
                if let Some(a) = p.pista.artista_id {
                    *artistas.entry(a).or_default() += 1;
                }
            }
            assert!(artistas.values().all(|n| *n <= 2));
            if b.completado || b.pistas.is_empty() {
                break;
            }
        }
        assert!(ids.len() > 8);
    }

    #[test]
    fn sin_candidatas_el_bloque_dice_que_se_agoto_el_pool() {
        let mut c = Constructor::new(
            Intencion::default(),
            Ajustes::default(),
            Vec::new(),
            Box::new(Determinista),
        );
        let b = c.bloque(true);
        assert_eq!(b.corte, Corte::PoolAgotado);
        assert!(!b.completado);
    }
}
