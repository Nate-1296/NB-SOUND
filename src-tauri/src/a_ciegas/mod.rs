//! A ciegas (F6.2): el juego de redescubrir la propia música,
//! `servicios/explorador_ciego/` de la V1.
//!
//! Una ronda son unos cuantos retos: una canción que hay que reconocer por su
//! portada o por un fragmento, o que se redescubre. Se puede ir revelando el
//! artista y el álbum, pedir indicios sobre el título, escribirlo o rendirse. Nada
//! de esto cambia la biblioteca, y la ronda vive solo en memoria, como en la V1.
//!
//! Lo que sale hacia la interfaz es siempre [`RetoVisible`]: un dato que aún no se
//! ha revelado no viaja por el puente, ni siquiera para que la vista lo esconda.

pub mod indicios;
pub mod selectores;

use std::collections::{BTreeSet, HashMap};

use serde::{Deserialize, Serialize};
use ts_rs::TS;

use self::indicios::{Indicio, Intento, INDICIOS};
use self::selectores::Candidata;
use crate::db::BaseDeDatos;
use crate::error::NsResult;

pub const RETOS_POR_DEFECTO: u32 = 5;
pub const RETOS_MAXIMO: u32 = 25;

/// `ModoExplorador`, con sus nombres de la V1.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "snake_case")]
pub enum Modo {
    Portada,
    Audio,
    Redescubrimiento,
    NuncaEliges,
}

pub const MODOS: [Modo; 4] = [
    Modo::Portada,
    Modo::Audio,
    Modo::Redescubrimiento,
    Modo::NuncaEliges,
];

/// `NivelRevelacion`: lo revelado crece en este orden.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "snake_case")]
pub enum Nivel {
    Oculto,
    Artista,
    Album,
    Total,
}

/// `EstadoReto`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "snake_case")]
pub enum EstadoReto {
    EnCurso,
    Acertado,
    Revelado,
    Pasado,
}

#[derive(Debug, Clone)]
struct Reto {
    pista: Candidata,
    nivel: Nivel,
    estado: EstadoReto,
    fragmento_escuchado: bool,
    indicios: BTreeSet<Indicio>,
    fallos: u32,
}

/// Un indicio desvelado, con su valor.
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
pub struct IndicioVisto {
    pub indicio: Indicio,
    pub valor: String,
}

/// `Reto.datos_visibles`: lo que la vista puede enseñar del reto en curso.
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct RetoVisible {
    #[ts(type = "number")]
    pub pista_id: i64,
    pub nivel: Nivel,
    pub estado: EstadoReto,
    pub fragmento_escuchado: bool,
    pub titulo: Option<String>,
    pub artista: Option<String>,
    pub album: Option<String>,
    #[ts(type = "number | null")]
    pub anio: Option<i64>,
    #[ts(type = "number | null")]
    pub artista_id: Option<i64>,
    #[ts(type = "number | null")]
    pub album_id: Option<i64>,
    pub duracion_seg: f64,
    pub tiene_portada: bool,
    #[ts(type = "number")]
    pub reproducciones: i64,
    pub favorita: bool,
    /// Si el título se puede escribir con un teclado latino; si no, "¡La sé!".
    pub se_puede_escribir: bool,
    pub indicios: Vec<IndicioVisto>,
    pub fallos: u32,
}

impl Reto {
    fn visible(&self) -> RetoVisible {
        let p = &self.pista;
        let hasta = |n: Nivel| self.nivel >= n;
        RetoVisible {
            pista_id: p.id,
            nivel: self.nivel,
            estado: self.estado,
            fragmento_escuchado: self.fragmento_escuchado,
            titulo: hasta(Nivel::Total).then(|| p.titulo.clone()),
            artista: hasta(Nivel::Artista).then(|| p.artista.clone()),
            album: hasta(Nivel::Album).then(|| p.album.clone()),
            anio: p.anio.filter(|_| hasta(Nivel::Total)),
            artista_id: p.artista_id.filter(|_| hasta(Nivel::Artista)),
            album_id: p.album_id.filter(|_| hasta(Nivel::Album)),
            duracion_seg: p.duracion_seg,
            tiene_portada: p.tiene_portada,
            reproducciones: p.reproducciones,
            favorita: p.favorita,
            se_puede_escribir: indicios::se_puede_escribir(&p.titulo),
            indicios: self
                .indicios
                .iter()
                .map(|i| IndicioVisto {
                    indicio: *i,
                    valor: indicios::valor(*i, &p.titulo),
                })
                .collect(),
            fallos: self.fallos,
        }
    }
}

/// La ronda tal como la ve la interfaz tras cada jugada.
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct Ronda {
    pub modo: Option<Modo>,
    pub indice: u32,
    pub total: u32,
    pub terminada: bool,
    pub reto: Option<RetoVisible>,
    pub acertados: u32,
    pub revelados: u32,
    pub pasados: u32,
    pub segundos_fragmento: f64,
}

/// `ExploradorCiegoService`.
pub struct Juego {
    modo: Option<Modo>,
    retos: Vec<Reto>,
    indice: usize,
    segundos_fragmento: f64,
    pools: HashMap<Modo, Vec<Candidata>>,
}

impl Default for Juego {
    fn default() -> Self {
        Self {
            modo: None,
            retos: Vec::new(),
            indice: 0,
            segundos_fragmento: 12.0,
            pools: HashMap::new(),
        }
    }
}

impl Juego {
    fn activa(&self) -> bool {
        self.modo.is_some() && self.indice < self.retos.len()
    }

    fn reto(&mut self) -> Option<&mut Reto> {
        if self.activa() {
            self.retos.get_mut(self.indice)
        } else {
            None
        }
    }

    fn contar(&self, e: EstadoReto) -> u32 {
        self.retos.iter().filter(|r| r.estado == e).count() as u32
    }

    #[must_use]
    pub fn ronda(&self) -> Ronda {
        Ronda {
            modo: self.modo,
            indice: self.indice as u32,
            total: self.retos.len() as u32,
            terminada: !self.retos.is_empty() && self.indice >= self.retos.len(),
            reto: if self.activa() {
                self.retos.get(self.indice).map(Reto::visible)
            } else {
                None
            },
            acertados: self.contar(EstadoReto::Acertado),
            revelados: self.contar(EstadoReto::Revelado),
            pasados: self.contar(EstadoReto::Pasado),
            segundos_fragmento: self.segundos_fragmento,
        }
    }

    /// Entre 4 y 30 segundos.
    pub fn fijar_segundos_fragmento(&mut self, s: f64) {
        if s.is_finite() {
            self.segundos_fragmento = s.clamp(4.0, 30.0);
        }
    }

    /// `iniciar_ronda`: `n` retos (entre 1 y 25) del modo, evitando si se puede
    /// las de `evitar`. Devuelve si hubo con qué empezar.
    ///
    /// # Errors
    ///
    /// Los de la base.
    pub fn iniciar(
        &mut self,
        db: &BaseDeDatos,
        modo: Modo,
        n: u32,
        evitar: &[i64],
    ) -> NsResult<bool> {
        let n = n.clamp(1, RETOS_MAXIMO) as usize;
        let mut pool = match self.pools.get(&modo) {
            Some(p) if !p.is_empty() => p.clone(),
            _ => selectores::candidatas(db, modo)?,
        };
        if pool.is_empty() {
            self.cerrar();
            return Ok(false);
        }
        if evitar.is_empty() {
            self.pools.insert(modo, pool.clone());
        } else {
            let filtrado: Vec<Candidata> = pool
                .iter()
                .filter(|p| !evitar.contains(&p.id))
                .cloned()
                .collect();
            if !filtrado.is_empty() {
                pool = filtrado;
            }
        }
        // Fisher-Yates: el orden de la ronda no tiene que coincidir con la V1.
        let mut azar = crate::dj::azar::Azar::sin_semilla();
        for i in (1..pool.len()).rev() {
            let j = ((azar.real() * (i + 1) as f64) as usize).min(i);
            pool.swap(i, j);
        }
        pool.truncate(n);
        self.modo = Some(modo);
        self.indice = 0;
        self.retos = pool
            .into_iter()
            .map(|pista| Reto {
                pista,
                nivel: Nivel::Oculto,
                estado: EstadoReto::EnCurso,
                fragmento_escuchado: false,
                indicios: BTreeSet::new(),
                fallos: 0,
            })
            .collect();
        Ok(true)
    }

    /// `cerrar_ronda`.
    pub fn cerrar(&mut self) {
        self.modo = None;
        self.retos.clear();
        self.indice = 0;
    }

    /// `invalidar_caches`: tras cambiar la biblioteca.
    pub fn olvidar_candidatas(&mut self) {
        self.pools.clear();
    }

    pub fn fragmento_escuchado(&mut self) {
        if let Some(r) = self.reto() {
            r.fragmento_escuchado = true;
        }
    }

    pub fn revelar_artista(&mut self) {
        if let Some(r) = self.reto() {
            r.nivel = r.nivel.max(Nivel::Artista);
        }
    }

    pub fn revelar_album(&mut self) {
        if let Some(r) = self.reto() {
            r.nivel = r.nivel.max(Nivel::Album);
        }
    }

    /// Lo revela todo; si estaba en curso, cuenta como revelado.
    pub fn revelar_todo(&mut self) {
        if let Some(r) = self.reto() {
            r.nivel = Nivel::Total;
            if r.estado == EstadoReto::EnCurso {
                r.estado = EstadoReto::Revelado;
            }
        }
    }

    /// `marcar_acertada`: "¡La sé!", para los títulos que no se pueden escribir.
    pub fn la_se(&mut self) {
        if let Some(r) = self.reto() {
            r.estado = EstadoReto::Acertado;
            r.nivel = Nivel::Total;
        }
    }

    /// `intentar_adivinar`.
    pub fn intentar(&mut self, texto: &str) -> Intento {
        let Some(r) = self.reto() else {
            return indicios::comprobar("", "");
        };
        let i = indicios::comprobar(&r.pista.titulo, texto);
        if i.acierto {
            r.estado = EstadoReto::Acertado;
            r.nivel = Nivel::Total;
        } else {
            r.fallos += 1;
        }
        i
    }

    pub fn revelar_indicio(&mut self, indicio: Indicio) {
        if let Some(r) = self.reto() {
            r.indicios.insert(indicio);
        }
    }

    pub fn pasar(&mut self) {
        if let Some(r) = self.reto() {
            if r.estado == EstadoReto::EnCurso {
                r.estado = EstadoReto::Pasado;
            }
        }
    }

    /// `avanzar`: el reto que se deja sin decidir cuenta como pasado.
    pub fn avanzar(&mut self) {
        if self.retos.is_empty() || self.indice >= self.retos.len() {
            return;
        }
        self.pasar();
        self.indice += 1;
    }

    /// `retroceder`: el reto al que se vuelve conserva cómo quedó.
    pub fn retroceder(&mut self) {
        if !self.retos.is_empty() && self.indice > 0 {
            self.indice = (self.indice - 1).min(self.retos.len() - 1);
        }
    }

    /// `posicion_inicio_fragmento`: las de más de un minuto, desde el 30 %, donde
    /// suele caer el primer estribillo.
    #[must_use]
    pub fn inicio_fragmento(duracion_seg: f64) -> f64 {
        if duracion_seg <= 60.0 {
            0.0
        } else {
            crate::dj::redondear(duracion_seg * 0.30, 2)
        }
    }

    /// La pista del reto en curso, para tocar su fragmento.
    #[must_use]
    pub fn pista_en_curso(&self) -> Option<(i64, f64)> {
        self.retos
            .get(self.indice)
            .filter(|_| self.activa())
            .map(|r| (r.pista.id, r.pista.duracion_seg))
    }
}

/// `disponibles_por_modo`.
///
/// # Errors
///
/// Los de la base.
pub fn disponibles(db: &BaseDeDatos) -> NsResult<Vec<(Modo, u32)>> {
    MODOS
        .iter()
        .map(|m| selectores::disponibles(db, *m).map(|n| (*m, n)))
        .collect()
}

/// Los indicios que se pueden pedir, en su orden.
#[must_use]
pub const fn indicios_disponibles() -> [Indicio; 5] {
    INDICIOS
}

#[cfg(test)]
mod pruebas {
    //! `tests/test_explorador_ciego_service.py` y `_modelo.py` de la V1.

    use super::*;

    /// Doce canciones: con portada las pares, escuchadas las múltiplos de tres,
    /// la 5 favorita y la 7 de 20 segundos.
    fn biblioteca() -> BaseDeDatos {
        let db = BaseDeDatos::en_memoria().unwrap();
        let conn = db.conexion().unwrap();
        conn.execute(
            "INSERT INTO portadas (id, sha256, ruta, ancho, alto, bytes, mime, origen)
             VALUES (1, ?1, 'p.jpg', 1, 1, 1, 'image/jpeg', 'etiqueta')",
            ["a".repeat(64)],
        )
        .unwrap();
        for id in 1..=12i64 {
            conn.execute(
                "INSERT INTO pistas (id, titulo, artista_nombre, album_titulo, ruta, duracion_seg,
                     portada_id, reproducciones, favorita)
                 VALUES (?1, ?2, 'Artista', 'Álbum', ?3, ?4, ?5, ?6, ?7)",
                rusqlite::params![
                    id,
                    format!("Canción {id}"),
                    format!("{id}.mp3"),
                    if id == 7 { 20.0 } else { 200.0 },
                    (id % 2 == 0).then_some(1),
                    if id % 3 == 0 { 4 } else { 0 },
                    i64::from(id == 5)
                ],
            )
            .unwrap();
        }
        drop(conn);
        db
    }

    #[test]
    fn cada_modo_saca_de_su_universo() {
        let db = biblioteca();
        let n: HashMap<Modo, u32> = disponibles(&db).unwrap().into_iter().collect();
        assert_eq!(n[&Modo::Portada], 6);
        assert_eq!(n[&Modo::Audio], 11);
        assert_eq!(n[&Modo::Redescubrimiento], 5);
        assert_eq!(n[&Modo::NuncaEliges], 8);
        let r: Vec<i64> = selectores::candidatas(&db, Modo::Redescubrimiento)
            .unwrap()
            .iter()
            .map(|c| c.id)
            .collect();
        let mut esperadas = r.clone();
        esperadas.sort_unstable();
        assert_eq!(esperadas, [3, 5, 6, 9, 12]);
    }

    #[test]
    fn sin_cola_larga_nunca_la_eliges_toma_las_menos_escuchadas() {
        let db = biblioteca();
        db.conexion()
            .unwrap()
            .execute("UPDATE pistas SET reproducciones = reproducciones + 1", [])
            .unwrap();
        let c = selectores::candidatas(&db, Modo::NuncaEliges).unwrap();
        assert_eq!(c.len(), 8, "las de una sola escucha");
    }

    #[test]
    fn nada_oculto_viaja_hasta_que_se_revela() {
        let db = biblioteca();
        let mut j = Juego::default();
        assert!(j.iniciar(&db, Modo::Audio, 3, &[]).unwrap());
        let v = j.ronda().reto.unwrap();
        assert_eq!(
            (
                v.titulo.as_deref(),
                v.artista.as_deref(),
                v.album.as_deref()
            ),
            (None, None, None)
        );
        j.revelar_artista();
        let v = j.ronda().reto.unwrap();
        assert_eq!(
            (v.artista.as_deref(), v.album.as_deref()),
            (Some("Artista"), None)
        );
        j.revelar_album();
        j.revelar_artista();
        assert_eq!(j.ronda().reto.unwrap().nivel, Nivel::Album, "no baja");
        j.revelar_todo();
        let v = j.ronda().reto.unwrap();
        assert!(v.titulo.is_some());
        assert_eq!(v.estado, EstadoReto::Revelado);
    }

    #[test]
    fn escribir_el_titulo_acierta_o_suma_un_fallo() {
        let db = biblioteca();
        let mut j = Juego::default();
        j.iniciar(&db, Modo::Audio, 1, &[]).unwrap();
        let id = j.pista_en_curso().unwrap().0;
        assert!(!j.intentar("otra cosa").acierto);
        assert_eq!(j.ronda().reto.unwrap().fallos, 1);
        assert!(j.intentar(&format!("cancion {id}")).acierto);
        let r = j.ronda();
        assert_eq!(r.reto.unwrap().estado, EstadoReto::Acertado);
        assert_eq!(r.acertados, 1);
    }

    #[test]
    fn los_indicios_se_acumulan_con_su_valor() {
        let db = biblioteca();
        let mut j = Juego::default();
        j.iniciar(&db, Modo::Audio, 1, &[]).unwrap();
        assert!(j.ronda().reto.unwrap().indicios.is_empty());
        j.revelar_indicio(Indicio::EmpiezaCon);
        j.revelar_indicio(Indicio::CantidadPalabras);
        j.revelar_indicio(Indicio::EmpiezaCon);
        let v = j.ronda().reto.unwrap();
        assert_eq!(
            v.indicios,
            [
                IndicioVisto {
                    indicio: Indicio::EmpiezaCon,
                    valor: "C".into()
                },
                IndicioVisto {
                    indicio: Indicio::CantidadPalabras,
                    valor: "2".into()
                }
            ]
        );
        assert!(v.titulo.is_none());
    }

    #[test]
    fn avanzar_sin_decidir_cuenta_como_pasado_y_la_ronda_termina() {
        let db = biblioteca();
        let mut j = Juego::default();
        j.iniciar(&db, Modo::Audio, 2, &[]).unwrap();
        j.la_se();
        j.avanzar();
        j.avanzar();
        let r = j.ronda();
        assert!(r.terminada && r.reto.is_none());
        assert_eq!((r.acertados, r.pasados, r.total), (1, 1, 2));
        j.retroceder();
        assert_eq!(j.ronda().reto.unwrap().estado, EstadoReto::Pasado);
        j.cerrar();
        assert_eq!(j.ronda().modo, None);
    }

    #[test]
    fn la_ronda_evita_las_ya_jugadas_si_quedan_otras_y_sin_candidatas_no_empieza() {
        let db = biblioteca();
        let mut j = Juego::default();
        j.iniciar(&db, Modo::Portada, 25, &[2, 4, 6]).unwrap();
        assert_eq!(j.ronda().total, 3);
        j.iniciar(&db, Modo::Portada, 25, &[2, 4, 6, 8, 10, 12])
            .unwrap();
        assert_eq!(j.ronda().total, 6, "si no queda otra, se repite");
        let vacia = BaseDeDatos::en_memoria().unwrap();
        let mut j = Juego::default();
        assert!(!j.iniciar(&vacia, Modo::Audio, 5, &[]).unwrap());
        assert!(j.ronda().reto.is_none());
    }

    #[test]
    fn el_fragmento_va_del_30_por_ciento_y_dura_entre_4_y_30_segundos() {
        assert_eq!(Juego::inicio_fragmento(45.0), 0.0);
        assert_eq!(Juego::inicio_fragmento(200.0), 60.0);
        let mut j = Juego::default();
        j.fijar_segundos_fragmento(1.0);
        assert_eq!(j.ronda().segundos_fragmento, 4.0);
        j.fijar_segundos_fragmento(f64::NAN);
        j.fijar_segundos_fragmento(99.0);
        assert_eq!(j.ronda().segundos_fragmento, 30.0);
    }
}
