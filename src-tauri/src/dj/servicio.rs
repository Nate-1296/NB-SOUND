//! El servicio del DJ Privado: `servicios/dj_privado/servicio.py`.
//!
//! El ciclo de una sesión: interpretar el pedido, construir el primer bloque y
//! guardarlo, seguir construyendo hasta la duración pedida, apuntar lo que el
//! usuario hace con cada pista, regenerarla, descartarla o guardarla como playlist.
//! Mantiene una sola sesión activa; las demás se consultan en el historial.
//!
//! Una diferencia con la V1: toda sesión nueva guarda su semilla. La V1 solo la
//! guardaba si se la daban, y una sesión sin semilla no se podía reconstruir; aquí
//! retomar una sesión del historial sigue construyéndola igual que la primera vez.

use serde::Serialize;
use ts_rs::TS;

use super::azar::Azar;
use super::constructor::{self, Ajustes, Bloque, Constructor};
use super::embeddings::Proveedor;
use super::intencion::{self, Intencion};
use super::planificador::{self, Candidata};
use super::sesiones::{self, Evento};
use crate::db::BaseDeDatos;
use crate::error::{NsError, NsResult};

/// Lo que se guarda en `dj_sesiones.motor_version`: la V2 planifica como la V1.
pub const MOTOR_VERSION: &str = "dj_v1";
/// Cuántas pistas se leen como candidatas, como la V1 (`cargar_candidatos`).
const LIMITE_POOL: usize = 5000;
/// Cuántas sesiones mira el historial antes de filtrar.
const HISTORIAL: u32 = 60;

/// La sesión activa en memoria (`SesionActiva`).
pub struct Activa {
    pub id: i64,
    pub intencion: Intencion,
    pub semilla: i64,
    constructor: Constructor,
    bloques: Vec<Bloque>,
    pub completada: bool,
}

impl Activa {
    #[must_use]
    pub fn bloques(&self) -> &[Bloque] {
        &self.bloques
    }
}

/// Cómo acabó el intento de empezar una sesión.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Inicio {
    /// Con su primer bloque guardado.
    Lista { id: i64 },
    /// No hay ninguna pista que encaje: biblioteca vacía o exclusiones que lo
    /// descartan todo (`PoolVacioError` de la V1). La sesión queda en `error`.
    SinCandidatas { id: i64 },
}

/// Una fila del historial, con lo que la V1 enseñaba de cada sesión.
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct FilaHistorial {
    #[ts(type = "number")]
    pub id: i64,
    pub peticion: String,
    pub estado: String,
    pub minutos: u32,
    pub creada_en: String,
    #[ts(type = "number | null")]
    pub playlist_id: Option<i64>,
    #[ts(type = "number")]
    pub total_pistas: u64,
    #[ts(type = "number")]
    pub artistas_distintos: u64,
    pub duracion_seg: f64,
    #[ts(type = "number")]
    pub transiciones_buenas: u64,
    #[ts(type = "number")]
    pub transiciones_total: u64,
}

type Fabrica = Box<dyn Fn() -> Box<dyn Proveedor + Send> + Send>;

pub struct Dj {
    db: BaseDeDatos,
    proveedor: Fabrica,
    activa: Option<Activa>,
}

impl Dj {
    /// `proveedor` da el embedding con el que se construye cada sesión: el del
    /// agregado de texto si está, o el determinista.
    #[must_use]
    pub fn new(db: BaseDeDatos, proveedor: Fabrica) -> Self {
        Self {
            db,
            proveedor,
            activa: None,
        }
    }

    #[must_use]
    pub const fn activa(&self) -> Option<&Activa> {
        self.activa.as_ref()
    }

    /// Hace activa la sesión `id` si no lo es: tras abrir la aplicación, la que
    /// suena puede no estar en memoria.
    ///
    /// # Errors
    ///
    /// Los de [`Self::cargar`].
    pub fn asegurar(&mut self, id: i64) -> NsResult<()> {
        if self.activa.as_ref().is_some_and(|a| a.id == id) {
            Ok(())
        } else {
            self.cargar(id)
        }
    }

    /// `iniciar_sesion`. `pool` sustituye a la biblioteca (pruebas).
    ///
    /// # Errors
    ///
    /// [`NsError::InvalidInput`] si la petición está vacía o la duración no está
    /// entre 1 y 480 minutos; [`NsError::StorageFailure`] si la base falla.
    pub fn iniciar(
        &mut self,
        peticion: &str,
        minutos: u32,
        semilla: Option<i64>,
        pool: Option<Vec<Candidata>>,
    ) -> NsResult<Inicio> {
        let peticion = peticion.trim();
        if peticion.is_empty() || !(1..=480).contains(&minutos) {
            return Err(NsError::InvalidInput);
        }
        let intencion = intencion::interpretar(peticion, minutos);
        // Una semilla que cabe en un `f64` sin perder cifras: el JSON del puente no
        // las distingue más allá.
        let semilla =
            semilla.unwrap_or_else(|| (Azar::sin_semilla().real() * 2f64.powi(31)) as i64);
        let json = serde_json::to_string(&intencion).map_err(|_| NsError::Internal)?;
        let id = sesiones::crear(
            &self.db,
            peticion,
            &json,
            minutos,
            MOTOR_VERSION,
            Some(semilla),
        )?;
        let pool = match pool {
            Some(p) => p,
            None => planificador::cargar(&self.db, LIMITE_POOL, &[], false)?,
        };
        if pool.is_empty() {
            self.activa = None;
            sesiones::cambiar_estado(&self.db, id, "error", true)?;
            return Ok(Inicio::SinCandidatas { id });
        }
        let ajustes = Ajustes {
            semilla: Some(semilla),
            ..Ajustes::default()
        };
        let mut c = Constructor::new(intencion.clone(), ajustes, pool, (self.proveedor)());
        let bloque = c.bloque(true);
        if bloque.pistas.is_empty() {
            self.activa = None;
            sesiones::cambiar_estado(&self.db, id, "error", true)?;
            return Ok(Inicio::SinCandidatas { id });
        }
        let resumen = constructor::resumen(std::slice::from_ref(&bloque), &intencion);
        sesiones::guardar_bloque(&self.db, id, &bloque, &resumen)?;
        let completada = bloque.completado;
        sesiones::cambiar_estado(
            &self.db,
            id,
            if completada { "lista" } else { "construyendo" },
            false,
        )?;
        self.activa = Some(Activa {
            id,
            intencion,
            semilla,
            constructor: c,
            bloques: vec![bloque],
            completada,
        });
        Ok(Inicio::Lista { id })
    }

    /// `continuar_construccion`: el siguiente bloque, ya guardado. `None` si no hay
    /// sesión activa o ya está completa.
    ///
    /// # Errors
    ///
    /// [`NsError::StorageFailure`] si la base falla.
    pub fn continuar(&mut self) -> NsResult<Option<&Bloque>> {
        let Some(a) = self.activa.as_mut().filter(|a| !a.completada) else {
            return Ok(None);
        };
        let bloque = a.constructor.bloque(false);
        if bloque.pistas.is_empty() {
            a.completada = true;
            sesiones::cambiar_estado(&self.db, a.id, "lista", false)?;
            return Ok(None);
        }
        a.completada = bloque.completado;
        a.bloques.push(bloque);
        let resumen = constructor::resumen(&a.bloques, &a.intencion);
        let bloque = a.bloques.last().expect("recién añadido");
        sesiones::guardar_bloque(&self.db, a.id, bloque, &resumen)?;
        if a.completada {
            sesiones::cambiar_estado(&self.db, a.id, "lista", false)?;
        }
        Ok(a.bloques.last())
    }

    /// `registrar_reproduccion`, `registrar_skip`, `registrar_like` y
    /// `registrar_dislike`. Sin sesión activa no hace nada.
    ///
    /// # Errors
    ///
    /// [`NsError::StorageFailure`] si la base falla.
    pub fn registrar(&self, posicion: u32, pista: i64, evento: Evento) -> NsResult<()> {
        match &self.activa {
            Some(a) => sesiones::registrar(
                &self.db,
                a.id,
                Some(posicion),
                Some(pista),
                evento,
                &serde_json::json!({}),
            ),
            None => Ok(()),
        }
    }

    /// `regenerar_sesion`: otra sesión con el mismo pedido y otra semilla (la de la
    /// V1: la anterior más 17). La anterior queda descartada.
    ///
    /// # Errors
    ///
    /// Los de [`Self::iniciar`].
    pub fn regenerar(&mut self) -> NsResult<Option<Inicio>> {
        let Some(a) = self.activa.take() else {
            return Ok(None);
        };
        sesiones::cambiar_estado(&self.db, a.id, "descartada", true)?;
        self.iniciar(
            &a.intencion.prompt,
            a.intencion.duracion_minutos,
            Some(a.semilla + 17),
            None,
        )
        .map(Some)
    }

    /// `descartar_sesion_activa`.
    ///
    /// # Errors
    ///
    /// [`NsError::StorageFailure`] si la base falla.
    pub fn descartar(&mut self) -> NsResult<()> {
        if let Some(a) = self.activa.take() {
            sesiones::cambiar_estado(&self.db, a.id, "descartada", true)?;
            sesiones::guardar_en_curso(&self.db, None)?;
        }
        Ok(())
    }

    /// `finalizar_sesion_activa`: acabó de sonar.
    ///
    /// # Errors
    ///
    /// [`NsError::StorageFailure`] si la base falla.
    pub fn finalizar(&mut self) -> NsResult<()> {
        if let Some(a) = &self.activa {
            sesiones::cambiar_estado(&self.db, a.id, "finalizada", true)?;
            sesiones::guardar_en_curso(&self.db, None)?;
        }
        Ok(())
    }

    /// `guardar_como_playlist`: con el nombre dado o, vacío, el siguiente
    /// "DJ Privado: Music Session, Vol. N". Devuelve el id de la playlist.
    ///
    /// # Errors
    ///
    /// [`NsError::InvalidInput`] sin sesión activa; los de [`crate::playlists::crear`].
    pub fn guardar_como_playlist(&self, nombre: &str) -> NsResult<i64> {
        let a = self.activa.as_ref().ok_or(NsError::InvalidInput)?;
        let nombre = match nombre.trim() {
            "" => self.nombre_automatico()?,
            n => n.to_owned(),
        };
        let descripcion: String = a.intencion.prompt.chars().take(120).collect();
        let playlist = crate::playlists::crear(
            &self.db,
            &nombre,
            Some(&format!("Sesión DJ: {descripcion}")),
        )?;
        let ids: Vec<i64> = sesiones::pistas(&self.db, a.id)?
            .iter()
            .map(|p| p.pista_id)
            .collect();
        crate::playlists::agregar(&self.db, playlist, &ids)?;
        sesiones::vincular_playlist(&self.db, a.id, playlist)?;
        sesiones::registrar(
            &self.db,
            a.id,
            None,
            None,
            Evento::Comentario,
            &serde_json::json!({
                "accion": "guardar_como_playlist",
                "playlist_id": playlist,
                "nombre": nombre,
            }),
        )?;
        Ok(playlist)
    }

    /// `_nombre_auto_playlist`: el mayor volumen usado más uno.
    fn nombre_automatico(&self) -> NsResult<String> {
        const PREFIJO: &str = "DJ Privado: Music Session, Vol.";
        let conn = self.db.conexion()?;
        let mut s = conn
            .prepare("SELECT nombre FROM playlists WHERE nombre LIKE ?1")
            .map_err(|_| NsError::StorageFailure)?;
        let nombres = s
            .query_map([format!("{PREFIJO} %")], |f| f.get::<_, String>(0))
            .map_err(|_| NsError::StorageFailure)?
            .collect::<rusqlite::Result<Vec<_>>>()
            .map_err(|_| NsError::StorageFailure)?;
        let mayor = nombres
            .iter()
            .filter_map(|n| n.rsplit_once("Vol.").map(|(_, v)| v.trim()))
            .filter_map(|v| v.parse::<u32>().ok())
            .max()
            .unwrap_or(0);
        Ok(format!("{PREFIJO} {}", mayor + 1))
    }

    /// `cargar_sesion`: retoma una del historial como activa. Sigue construyéndola
    /// sin repetir lo planificado y descontando lo que ya dura.
    ///
    /// # Errors
    ///
    /// [`NsError::InvalidInput`] si no existe; [`NsError::StorageFailure`].
    pub fn cargar(&mut self, id: i64) -> NsResult<()> {
        let s = sesiones::una(&self.db, id)?.ok_or(NsError::InvalidInput)?;
        let intencion: Intencion = serde_json::from_str(&s.intencion).unwrap_or_default();
        let semilla = s.semilla.unwrap_or(0);
        let ya = sesiones::pistas(&self.db, id)?;
        let ids: Vec<i64> = ya.iter().map(|p| p.pista_id).collect();
        let pool = planificador::cargar(&self.db, LIMITE_POOL, &ids, false)?;
        let ajustes = Ajustes {
            semilla: Some(semilla),
            ..Ajustes::default()
        };
        let mut c = Constructor::new(intencion.clone(), ajustes, pool, (self.proveedor)());
        c.retomar(
            ya.iter()
                .map(|p| p.posicion)
                .max()
                .map_or(0, |m| m as usize + 1),
            super::suma(ya.iter().map(|p| p.duracion_seg)),
        );
        self.activa = Some(Activa {
            id,
            intencion,
            semilla,
            constructor: c,
            bloques: Vec::new(),
            completada: s.estado == "lista" || s.estado == "finalizada",
        });
        Ok(())
    }

    /// Las sesiones recientes que contienen `texto` (sin distinguir tildes ni
    /// mayúsculas) y, si se da, con ese `estado`. Cota: las 60 más recientes, como
    /// la V1.
    ///
    /// # Errors
    ///
    /// [`NsError::StorageFailure`] si la base falla.
    pub fn historial(&self, texto: &str, estado: &str) -> NsResult<Vec<FilaHistorial>> {
        let normal = |t: &str| crate::catalogo::texto::eliminar_acentos(t).to_lowercase();
        let buscado = normal(texto.trim());
        let estado = estado.trim();
        Ok(sesiones::recientes(&self.db, HISTORIAL)?
            .into_iter()
            .filter(|s| estado.is_empty() || s.estado == estado)
            .filter(|s| buscado.is_empty() || normal(&s.peticion).contains(&buscado))
            .map(|s| {
                let r: serde_json::Value = serde_json::from_str(&s.resumen).unwrap_or_default();
                let n = |k: &str| r[k].as_u64().unwrap_or(0);
                FilaHistorial {
                    id: s.id,
                    peticion: s.peticion,
                    estado: s.estado,
                    minutos: s.objetivo_minutos,
                    creada_en: s.creada_en,
                    playlist_id: s.playlist_id,
                    total_pistas: n("total_pistas"),
                    artistas_distintos: n("artistas_distintos"),
                    duracion_seg: r["duracion_seg"].as_f64().unwrap_or(0.0),
                    transiciones_buenas: n("transiciones_buenas"),
                    transiciones_total: n("transiciones_total"),
                }
            })
            .collect())
    }

    /// Borra una sesión del historial; si era la activa, deja de serlo.
    ///
    /// # Errors
    ///
    /// [`NsError::StorageFailure`] si la base falla.
    pub fn eliminar(&mut self, id: i64) -> NsResult<()> {
        if self.activa.as_ref().is_some_and(|a| a.id == id) {
            self.activa = None;
        }
        if sesiones::en_curso(&self.db)?.is_some_and(|e| e.sesion == id) {
            sesiones::guardar_en_curso(&self.db, None)?;
        }
        sesiones::borrar(&self.db, id)
    }
}

#[cfg(test)]
mod pruebas {
    //! `tests/test_dj_privado_integracion.py` de la V1, sobre una base en memoria.

    use super::*;
    use crate::dj::embeddings::Determinista;
    use crate::dj::sesiones::EnCurso;

    /// La biblioteca de la V1: diez pistas de cinco artistas con rasgos sintéticos.
    fn biblioteca() -> BaseDeDatos {
        let db = BaseDeDatos::en_memoria().unwrap();
        let conn = db.conexion().unwrap();
        conn.execute_batch(
            "INSERT INTO artistas (id, nombre, clave) VALUES (1, 'Chopin', 'chopin'),
                 (2, 'Star', 'star'), (3, 'Trainer', 'trainer'), (4, 'Calm', 'calm'),
                 (5, 'LoudBand', 'loud');",
        )
        .unwrap();
        let pistas = [
            (1, 1, "Nocturne 1", "classical", 240.0),
            (2, 1, "Nocturne 2", "classical", 230.0),
            (3, 2, "Hit 1", "pop", 200.0),
            (4, 2, "Hit 2", "pop", 195.0),
            (5, 3, "Workout 1", "electronic", 220.0),
            (6, 3, "Workout 2", "electronic", 215.0),
            (7, 4, "Calm 1", "ambient", 360.0),
            (8, 5, "Hard 1", "metal", 220.0),
            (9, 5, "Hard 2", "rock", 210.0),
            (10, 2, "Hit 3", "pop", 205.0),
        ];
        for (id, artista, titulo, genero, duracion) in pistas {
            conn.execute(
                "INSERT INTO pistas (id, artista_id, titulo, artista_nombre, genero, duracion_seg, ruta)
                 VALUES (?1, ?2, ?3, (SELECT nombre FROM artistas WHERE id = ?2), ?4, ?5, ?6)",
                rusqlite::params![id, artista, titulo, genero, duracion, format!("t{id}.mp3")],
            )
            .unwrap();
        }
        let rasgos: [(i64, f64, &str, &str, [f64; 12]); 10] = [
            (
                1,
                60.0,
                "C#",
                "minor",
                [
                    0.25, 0.4, 0.10, 0.6, 0.85, 0.05, 0.3, 0.6, 0.6, 0.05, 0.05, 0.75,
                ],
            ),
            (
                2,
                55.0,
                "A",
                "minor",
                [
                    0.22, 0.35, 0.05, 0.7, 0.85, 0.1, 0.25, 0.7, 0.55, 0.05, 0.05, 0.8,
                ],
            ),
            (
                3,
                118.0,
                "C",
                "major",
                [0.7, 0.7, 0.6, 0.2, 0.3, 0.2, 0.7, 0.3, 0.2, 0.3, 0.7, 0.3],
            ),
            (
                4,
                122.0,
                "G",
                "major",
                [
                    0.68, 0.78, 0.65, 0.1, 0.3, 0.15, 0.78, 0.25, 0.25, 0.45, 0.75, 0.2,
                ],
            ),
            (
                5,
                128.0,
                "A",
                "minor",
                [
                    0.88, 0.6, 0.85, 0.1, 0.15, 0.4, 0.6, 0.4, 0.1, 0.9, 0.75, 0.3,
                ],
            ),
            (
                6,
                126.0,
                "D",
                "minor",
                [
                    0.82, 0.5, 0.80, 0.15, 0.2, 0.45, 0.55, 0.4, 0.1, 0.85, 0.75, 0.4,
                ],
            ),
            (
                7,
                72.0,
                "F",
                "major",
                [
                    0.15, 0.5, 0.05, 0.3, 0.95, 0.05, 0.4, 0.5, 0.9, 0.1, 0.05, 0.7,
                ],
            ),
            (
                8,
                165.0,
                "E",
                "minor",
                [
                    0.95, 0.2, 0.4, 0.5, 0.05, 0.95, 0.4, 0.7, 0.05, 0.9, 0.5, 0.5,
                ],
            ),
            (
                9,
                130.0,
                "A",
                "minor",
                [
                    0.9, 0.4, 0.5, 0.3, 0.1, 0.85, 0.5, 0.5, 0.05, 0.85, 0.6, 0.4,
                ],
            ),
            (
                10,
                116.0,
                "C",
                "major",
                [
                    0.66, 0.75, 0.6, 0.15, 0.3, 0.15, 0.75, 0.25, 0.25, 0.4, 0.7, 0.25,
                ],
            ),
        ];
        for (id, bpm, tono, modo, v) in rasgos {
            // Las columnas de la V1, en su orden: energy, valence, danceability,
            // melancholy, calmness, aggressiveness, brightness, darkness, focus,
            // workout, party y night.
            conn.execute(
                "INSERT INTO rasgos (pista_id, version, bpm, tonalidad, modo, energia, valencia,
                     bailabilidad, melancolia, calma, agresividad, brillo, oscuridad,
                     para_concentrarse, para_entrenar, para_fiesta, para_la_noche)
                 VALUES (?1, 'v1', ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16)",
                rusqlite::params![
                    id, bpm, tono, modo, v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7], v[8], v[9],
                    v[10], v[11]
                ],
            )
            .unwrap();
        }
        drop(conn);
        db
    }

    fn dj(db: &BaseDeDatos) -> Dj {
        Dj::new(db.clone(), Box::new(|| Box::new(Determinista)))
    }

    fn id(i: Inicio) -> i64 {
        match i {
            Inicio::Lista { id } => id,
            Inicio::SinCandidatas { .. } => panic!("sin candidatas"),
        }
    }

    fn ids(d: &Dj) -> Vec<i64> {
        d.activa().unwrap().bloques()[0]
            .pistas
            .iter()
            .map(|p| p.pista.id)
            .collect()
    }

    #[test]
    fn concentrarse_elige_lo_tranquilo_y_entrenar_lo_energico() {
        let db = biblioteca();
        let mut d = dj(&db);
        let sesion = id(d.iniciar("para concentrarme", 15, Some(7), None).unwrap());
        assert!(sesion > 0);
        assert_eq!(d.activa().unwrap().intencion.curva_energia, "stable");
        assert!(ids(&d).contains(&7), "{:?}", ids(&d));
        let _ = d
            .iniciar("subida progresiva para entrenar", 15, Some(42), None)
            .unwrap();
        assert!(ids(&d).iter().any(|i| *i == 5 || *i == 6), "{:?}", ids(&d));
    }

    #[test]
    fn lo_construido_queda_guardado_con_su_resumen_y_su_semilla() {
        let db = biblioteca();
        let mut d = dj(&db);
        let s = id(d.iniciar("algo variado", 15, None, None).unwrap());
        let guardada = sesiones::una(&db, s).unwrap().unwrap();
        assert!(guardada.semilla.is_some());
        assert_eq!(guardada.motor_version, MOTOR_VERSION);
        let pistas = sesiones::pistas(&db, s).unwrap();
        assert_eq!(pistas.len(), d.activa().unwrap().bloques()[0].pistas.len());
        assert_eq!(pistas[0].transicion, serde_json::json!({}));
        if pistas.len() > 1 {
            assert!(pistas[1].transicion["score"].is_number());
        }
        let resumen: serde_json::Value = serde_json::from_str(&guardada.resumen).unwrap();
        assert_eq!(resumen["total_pistas"].as_u64(), Some(pistas.len() as u64));
    }

    #[test]
    fn continuar_no_repite_y_termina_en_lista() {
        let db = biblioteca();
        let mut d = dj(&db);
        let s = id(d.iniciar("de todo", 60, Some(3), None).unwrap());
        while d.continuar().unwrap().is_some() {}
        let pistas = sesiones::pistas(&db, s).unwrap();
        let mut vistos: Vec<i64> = pistas.iter().map(|p| p.pista_id).collect();
        vistos.sort_unstable();
        vistos.dedup();
        assert_eq!(vistos.len(), pistas.len());
        assert_eq!(sesiones::una(&db, s).unwrap().unwrap().estado, "lista");
    }

    #[test]
    fn sin_biblioteca_no_hay_sesion_y_queda_en_error() {
        let db = BaseDeDatos::en_memoria().unwrap();
        let mut d = dj(&db);
        let Inicio::SinCandidatas { id } = d.iniciar("lo que sea", 30, None, None).unwrap() else {
            panic!("debía faltar biblioteca");
        };
        assert_eq!(sesiones::una(&db, id).unwrap().unwrap().estado, "error");
        assert!(d.activa().is_none());
    }

    #[test]
    fn una_duracion_fuera_de_rango_o_un_pedido_vacio_se_rechazan() {
        let db = biblioteca();
        let mut d = dj(&db);
        assert_eq!(d.iniciar("x", 0, None, None), Err(NsError::InvalidInput));
        assert_eq!(d.iniciar("x", 481, None, None), Err(NsError::InvalidInput));
        assert_eq!(d.iniciar("   ", 30, None, None), Err(NsError::InvalidInput));
    }

    #[test]
    fn saltar_apunta_el_evento_y_marca_la_pista() {
        let db = biblioteca();
        let mut d = dj(&db);
        let s = id(d.iniciar("pop alegre", 15, Some(1), None).unwrap());
        let primera = sesiones::pistas(&db, s).unwrap()[0].clone();
        d.registrar(primera.posicion, primera.pista_id, Evento::Saltada)
            .unwrap();
        d.registrar(primera.posicion, primera.pista_id, Evento::MeGusta)
            .unwrap();
        assert_eq!(sesiones::pistas(&db, s).unwrap()[0].estado, "saltada");
        let tipos: Vec<String> = db
            .conexion()
            .unwrap()
            .prepare("SELECT tipo FROM dj_eventos WHERE sesion_id = ?1 ORDER BY id")
            .unwrap()
            .query_map([s], |f| f.get(0))
            .unwrap()
            .collect::<rusqlite::Result<_>>()
            .unwrap();
        assert_eq!(tipos, ["saltada", "like"]);
    }

    #[test]
    fn guardar_como_playlist_numera_y_vincula() {
        let db = biblioteca();
        let mut d = dj(&db);
        assert_eq!(d.guardar_como_playlist(""), Err(NsError::InvalidInput));
        let s = id(d.iniciar("rock", 15, Some(2), None).unwrap());
        let p1 = d.guardar_como_playlist("").unwrap();
        let p2 = d.guardar_como_playlist("  ").unwrap();
        let nombre = |p: i64| crate::playlists::una(&db, p).unwrap().unwrap().nombre;
        assert_eq!(nombre(p1), "DJ Privado: Music Session, Vol. 1");
        assert_eq!(nombre(p2), "DJ Privado: Music Session, Vol. 2");
        assert_eq!(
            crate::playlists::ids(&db, p1).unwrap(),
            sesiones::pistas(&db, s)
                .unwrap()
                .iter()
                .map(|p| p.pista_id)
                .collect::<Vec<_>>()
        );
        assert_eq!(
            sesiones::una(&db, s).unwrap().unwrap().playlist_id,
            Some(p2)
        );
    }

    #[test]
    fn retomar_una_sesion_sigue_sin_repetir_lo_planificado() {
        let db = biblioteca();
        let mut d = dj(&db);
        let s = id(d.iniciar("para concentrarme", 60, Some(9), None).unwrap());
        let antes: Vec<i64> = sesiones::pistas(&db, s)
            .unwrap()
            .iter()
            .map(|p| p.pista_id)
            .collect();
        let mut otro = dj(&db);
        otro.cargar(s).unwrap();
        assert_eq!(otro.activa().unwrap().intencion.prompt, "para concentrarme");
        if let Some(b) = otro.continuar().unwrap() {
            assert!(b.pistas.iter().all(|p| !antes.contains(&p.pista.id)));
            assert_eq!(b.pistas[0].posicion, antes.len());
        }
        assert_eq!(otro.cargar(9_999), Err(NsError::InvalidInput));
    }

    #[test]
    fn regenerar_descarta_la_anterior_y_cambia_la_semilla() {
        let db = biblioteca();
        let mut d = dj(&db);
        assert_eq!(d.regenerar(), Ok(None));
        let s1 = id(d.iniciar("algo energico", 15, Some(5), None).unwrap());
        let s2 = id(d.regenerar().unwrap().unwrap());
        assert_ne!(s1, s2);
        assert_eq!(
            sesiones::una(&db, s1).unwrap().unwrap().estado,
            "descartada"
        );
        assert_eq!(sesiones::una(&db, s2).unwrap().unwrap().semilla, Some(22));
    }

    #[test]
    fn el_historial_va_de_la_mas_nueva_y_filtra_sin_tildes() {
        let db = biblioteca();
        let mut d = dj(&db);
        d.descartar().unwrap();
        let a = id(d
            .iniciar("enérgico para correr", 15, Some(1), None)
            .unwrap());
        let b = id(d.iniciar("relajante nocturno", 15, Some(1), None).unwrap());
        let todas: Vec<i64> = d.historial("", "").unwrap().iter().map(|f| f.id).collect();
        assert_eq!(todas, [b, a]);
        let filtradas: Vec<i64> = d
            .historial("ENERGICO", "")
            .unwrap()
            .iter()
            .map(|f| f.id)
            .collect();
        assert_eq!(filtradas, [a]);
        assert!(d.historial("", "finalizada").unwrap().is_empty());
        assert!(d.historial("", "").unwrap()[0].total_pistas > 0);
    }

    #[test]
    fn eliminar_borra_la_sesion_sus_pistas_y_su_estado_en_curso() {
        let db = biblioteca();
        let mut d = dj(&db);
        let s = id(d.iniciar("pop", 15, Some(1), None).unwrap());
        sesiones::guardar_en_curso(
            &db,
            Some(&EnCurso {
                sesion: s,
                posicion: 1,
                segundos: 12.5,
                segundos_global: 230.0,
                volumen: 0.8,
            }),
        )
        .unwrap();
        assert_eq!(sesiones::en_curso(&db).unwrap().unwrap().posicion, 1);
        d.eliminar(s).unwrap();
        assert!(d.activa().is_none());
        assert!(sesiones::una(&db, s).unwrap().is_none());
        assert!(sesiones::pistas(&db, s).unwrap().is_empty());
        assert!(sesiones::en_curso(&db).unwrap().is_none());
    }

    #[test]
    fn las_preferencias_del_dj_vuelven_como_se_guardaron() {
        let db = biblioteca();
        assert_eq!(sesiones::preferencia(&db, "duracion").unwrap(), None);
        sesiones::guardar_preferencia(&db, "duracion", &serde_json::json!({"minutos": 45}))
            .unwrap();
        sesiones::guardar_preferencia(&db, "duracion", &serde_json::json!({"minutos": 90}))
            .unwrap();
        assert_eq!(
            sesiones::preferencia(&db, "duracion").unwrap(),
            Some(serde_json::json!({"minutos": 90}))
        );
        assert_eq!(
            sesiones::guardar_preferencia(&db, " ", &serde_json::json!(1)),
            Err(NsError::InvalidInput)
        );
    }
}
