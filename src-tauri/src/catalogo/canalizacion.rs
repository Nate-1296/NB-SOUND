//! La canalización de un archivo (F4.1.9): `core/pipeline.py` de la V1, pieza a
//! pieza, sobre los módulos de `catalogo`.
//!
//! Validar, buscar duplicados exactos, identificar (Shazam, AcoustID), normalizar,
//! buscar en MusicBrainz, decidir en tres etapas y, si entra, organizar el
//! archivo, escribir sus etiquetas, buscar portada y letra y darlo de alta. Lo que
//! no entra va a Por revisar con su causa (enmienda de ADR-007), con el archivo
//! guardado en la carpeta interna de la aplicación.
//!
//! Dos decisiones propias de la V2, las dos de la fase:
//!
//! - **Sin red** (el usuario no dio permiso a MusicBrainz), un archivo con título
//!   y artista en sus etiquetas entra tal como está, sin verificar, en lugar de ir
//!   a Por revisar: así la importación funciona solo con las etiquetas.
//! - **No se destruye nada del usuario**: lo que viene de fuera de la carpeta de
//!   música se copia; solo lo que ya está dentro se mueve a su sitio.

use std::path::{Path, PathBuf};

use rusqlite::{params, OptionalExtension};
use serde_json::json;

use super::acoustid::{self, Huella};
use super::correcciones;
use super::duplicados::{huella_de_archivo, Calidad, Duplicado, Gestor, Referencia, Visible};
use super::emparejador::{self, Contexto};
use super::etapas::{self, Tercera};
use super::etiquetas::{self, Cruda, Escritura, Tecnico};
use super::ia;
use super::letras_red;
use super::modelo::{CausaCuarentena, CausaRevision, DeAcoustid, DeShazam, Normalizada, Veredicto};
use super::musicbrainz::{self, Busqueda, Candidato};
use super::normalizacion;
use super::organizacion::{ruta_relativa, sin_conflicto, Destino};
use super::portadas_red;
use super::shazam;
use super::texto::construir_slug;
use crate::db::{self, BaseDeDatos};
use crate::error::{NsError, NsResult};
use crate::net::{Red, Servicio};
use crate::paths::Rutas;

/// Los límites técnicos de la V1 (`config/settings.py`).
const TAMANO_MINIMO: u64 = 10_240;
const DURACION_MINIMA_SEG: f64 = 15.0;
const BITRATE_MINIMO: u32 = 64;

/// Los formatos que importa la V2: los que decodifica Symphonia (ADR-003).
pub const EXTENSIONES: [&str; 8] = ["mp3", "flac", "m4a", "mp4", "ogg", "opus", "wav", "aac"];

/// Todo lo que necesita la canalización.
pub struct Entorno<'a> {
    pub db: &'a BaseDeDatos,
    pub rutas: &'a Rutas,
    pub red: &'a Red,
    pub musica: PathBuf,
    pub clave_acoustid: Option<String>,
    pub clave_theaudiodb: Option<String>,
    pub fpcalc: PathBuf,
    /// "Organizar archivos": colocarlos en la carpeta de música por sus datos.
    pub organizar: bool,
    pub importacion: Option<i64>,
    /// El desempate por IA, si el usuario lo activó y hay clave (F4.1.7).
    pub ia: Option<ia::ConfigIa>,
}

/// Qué pasó con un archivo.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Resultado {
    Importada {
        pista: i64,
        verificada: bool,
    },
    PorRevisar {
        id: i64,
        causa: &'static str,
    },
    /// No es audio que la V2 importe (otra extensión).
    Omitido,
}

/// La causa de Por revisar (la columna `por_revisar.causa`) de un veredicto.
pub fn causa_por_revisar(v: Veredicto) -> &'static str {
    match v {
        Veredicto::Revision(c) => match c {
            CausaRevision::PuntajeIntermedio => "puntaje_intermedio",
            CausaRevision::DuracionMarginal => "duracion_marginal",
            CausaRevision::ReleaseTypeDudoso => "release_type_dudoso",
            CausaRevision::CandidatosAmbiguos
            | CausaRevision::OwnershipAmbiguo
            | CausaRevision::IaRevisionManual
            | CausaRevision::FuentesDiscrepantes
            | CausaRevision::ClasificacionProvisional => "candidatos_ambiguos",
        },
        Veredicto::Cuarentena(c) => match c {
            CausaCuarentena::SinCandidatos => "sin_candidatos",
            CausaCuarentena::MetadataInsuficiente | CausaCuarentena::MetadataFinalInvalida => {
                "metadata_insuficiente"
            }
            CausaCuarentena::PuntajeBajo | CausaCuarentena::OwnershipInvalido => "puntaje_bajo",
            CausaCuarentena::EscrituraFallida | CausaCuarentena::ErrorInesperado => {
                "escritura_fallida"
            }
            CausaCuarentena::ValidacionPostEscritura => "validacion_post_escritura",
            CausaCuarentena::DuracionInvalida => "duracion_invalida",
            CausaCuarentena::ArchivoCorrupto
            | CausaCuarentena::ArchivoMuyPequeno
            | CausaCuarentena::ArchivoIlegible
            | CausaCuarentena::BitrateInsuficiente => "audio_ilegible",
        },
        Veredicto::Aceptado | Veredicto::Provisional(_) => "puntaje_intermedio",
    }
}

/// `validar_archivo`: existe, mide lo bastante, se lee, dura y suena.
pub fn validar(ruta: &Path) -> Result<(Tecnico, Cruda), CausaCuarentena> {
    let meta = std::fs::metadata(ruta).map_err(|_| CausaCuarentena::ArchivoIlegible)?;
    if !meta.is_file() {
        return Err(CausaCuarentena::ArchivoIlegible);
    }
    if meta.len() < TAMANO_MINIMO {
        return Err(CausaCuarentena::ArchivoMuyPequeno);
    }
    let (t, c) = etiquetas::leer(ruta).map_err(|e| match e {
        NsError::FileNotFound => CausaCuarentena::ArchivoIlegible,
        _ => CausaCuarentena::ArchivoCorrupto,
    })?;
    if t.duracion_seg <= 0.0 || t.duracion_seg < DURACION_MINIMA_SEG {
        return Err(CausaCuarentena::DuracionInvalida);
    }
    if t.bitrate_kbps.is_some_and(|b| b < BITRATE_MINIMO) {
        return Err(CausaCuarentena::BitrateInsuficiente);
    }
    Ok((t, c))
}

pub(super) fn bd<T>(r: rusqlite::Result<T>) -> NsResult<T> {
    r.map_err(|error| {
        tracing::error!(error = %error, "falló una escritura de la catalogación");
        NsError::StorageFailure
    })
}

/// Copia (o mueve, si ya está en la carpeta de música) un archivo a `destino`.
fn colocar(origen: &Path, destino: &Path, mover: bool) -> NsResult<()> {
    if let Some(dir) = destino.parent() {
        std::fs::create_dir_all(dir).map_err(|_| NsError::StorageFailure)?;
    }
    if mover && std::fs::rename(origen, destino).is_ok() {
        return Ok(());
    }
    let temporal = destino.with_extension(format!("{}.parcial", std::process::id()));
    std::fs::copy(origen, &temporal)
        .and_then(|_| std::fs::rename(&temporal, destino))
        .map_err(|_| {
            let _ = std::fs::remove_file(&temporal);
            NsError::StorageFailure
        })?;
    if mover {
        let _ = std::fs::remove_file(origen);
    }
    Ok(())
}

/// Lo guarda en Por revisar con su causa y lo necesario para importarlo después.
fn a_por_revisar(
    e: &Entorno<'_>,
    ruta: &Path,
    causa: &'static str,
    datos: serde_json::Value,
) -> NsResult<Resultado> {
    let huella = huella_de_archivo(ruta).unwrap_or_default();
    let ext = ruta
        .extension()
        .and_then(|x| x.to_str())
        .unwrap_or("audio")
        .to_lowercase();
    let nombre = if huella.is_empty() {
        format!("{}.{ext}", std::process::id())
    } else {
        format!("{huella}.{ext}")
    };
    let destino = e.rutas.por_revisar().join(nombre);
    if !destino.is_file() {
        colocar(ruta, &destino, ruta.starts_with(&e.musica))?;
    }
    let mut conn = e.db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    let id: i64 = bd(tx.query_row(
        "INSERT INTO por_revisar (ruta, causa, metadatos, importacion_id) VALUES (?1, ?2, ?3, ?4)
         ON CONFLICT (ruta) DO UPDATE SET causa = excluded.causa, metadatos = excluded.metadatos,
             importacion_id = excluded.importacion_id, resuelto_en = NULL
         RETURNING id",
        params![
            destino.to_string_lossy(),
            causa,
            datos.to_string(),
            e.importacion
        ],
        |f| f.get(0),
    ))?;
    bd(tx.commit())?;
    Ok(Resultado::PorRevisar { id, causa })
}

fn datos_para_revisar(
    nombre: &str,
    cruda: Option<&Cruda>,
    tecnico: Option<&Tecnico>,
    candidatos: &[Candidato],
) -> serde_json::Value {
    json!({
        "nombre_original": nombre,
        "etiquetas": cruda.map(|c| json!({
            "titulo": c.titulo, "artista": c.artista, "album": c.album, "numero": c.numero, "anio": c.anio,
        })),
        "duracion_seg": tecnico.map(|t| t.duracion_seg),
        "candidatos": candidatos.iter().take(5).map(|c| json!({
            "mbid_grabacion": c.mbid_grabacion, "mbid_lanzamiento": c.mbid_lanzamiento, "titulo": c.titulo,
            "artista": c.artista, "album": c.album, "anio": c.anio, "tipo": c.tipo, "duracion_seg": c.duracion_seg,
        })).collect::<Vec<_>>(),
    })
}

/// Lo que se da de alta: los datos definitivos de la pista.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct Alta {
    pub titulo: String,
    pub artista: String,
    pub album: String,
    pub tipo: String,
    pub numero: Option<u32>,
    pub total: Option<u32>,
    pub anio: Option<i32>,
    pub isrc: Option<String>,
    pub genero: Option<String>,
    pub mbid_grabacion: Option<String>,
    pub mbid_lanzamiento: Option<String>,
    pub mbid_grupo: Option<String>,
    pub verificada: bool,
    pub fuentes: Vec<&'static str>,
}

pub(super) fn alta_de_candidato(
    c: &Candidato,
    n: &Normalizada,
    fuentes: Vec<&'static str>,
) -> Alta {
    Alta {
        titulo: c.titulo.clone(),
        artista: if c.artista.is_empty() {
            n.artista.clone()
        } else {
            c.artista.clone()
        },
        album: c.album.clone(),
        tipo: c.tipo.clone(),
        numero: c.numero.or(n.numero),
        total: c.total,
        anio: c.anio.or(n.anio),
        isrc: c.isrc.clone().or_else(|| n.isrc.clone()),
        genero: None,
        mbid_grabacion: Some(c.mbid_grabacion.clone()).filter(|s| !s.is_empty()),
        mbid_lanzamiento: Some(c.mbid_lanzamiento.clone()).filter(|s| !s.is_empty()),
        mbid_grupo: Some(c.mbid_grupo.clone()).filter(|s| !s.is_empty()),
        verificada: true,
        fuentes,
    }
}

/// Tal como está: con sus etiquetas o, si no, lo que diga el nombre del archivo
/// (`Importar tal como está`, enmienda de ADR-007).
pub fn alta_tal_cual(c: &Cruda, nombre_archivo: &str, duracion_seg: f64) -> Alta {
    let n = normalizacion::normalizar(c, duracion_seg, nombre_archivo, None, None).ok();
    let stem = Path::new(nombre_archivo)
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("sin título")
        .to_owned();
    Alta {
        titulo: n
            .as_ref()
            .map(|n| n.titulo.clone())
            .filter(|t| !t.is_empty())
            .unwrap_or(stem),
        artista: n.as_ref().map(|n| n.artista.clone()).unwrap_or_default(),
        album: c.album.clone().unwrap_or_default(),
        numero: n.as_ref().and_then(|n| n.numero),
        anio: n.as_ref().and_then(|n| n.anio),
        isrc: c.isrc.clone(),
        genero: c.genero.clone(),
        mbid_grabacion: c.mbid_grabacion.clone(),
        verificada: false,
        fuentes: vec!["tag_local"],
        ..Alta::default()
    }
}

pub(super) fn artista_id(tx: &rusqlite::Transaction<'_>, nombre: &str) -> NsResult<i64> {
    let nombre = if nombre.trim().is_empty() {
        "Desconocido"
    } else {
        nombre.trim()
    };
    let clave = construir_slug(nombre);
    if let Some(id) = bd(tx
        .query_row("SELECT id FROM artistas WHERE clave = ?1", [&clave], |f| {
            f.get(0)
        })
        .optional())?
    {
        return Ok(id);
    }
    bd(tx.execute(
        "INSERT INTO artistas (nombre, clave) VALUES (?1, ?2)",
        params![nombre, clave],
    ))?;
    Ok(tx.last_insert_rowid())
}

pub(super) fn album_id(
    tx: &rusqlite::Transaction<'_>,
    artista: i64,
    a: &Alta,
    carpeta: Option<&str>,
) -> NsResult<Option<i64>> {
    if a.album.trim().is_empty() {
        return Ok(None);
    }
    let clave = construir_slug(&a.album);
    if let Some(id) = bd(tx
        .query_row(
            "SELECT id FROM albumes WHERE artista_id = ?1 AND clave = ?2",
            params![artista, clave],
            |f| f.get(0),
        )
        .optional())?
    {
        return Ok(Some(id));
    }
    let tipo = if a.tipo.is_empty() { "Album" } else { &a.tipo };
    bd(tx.execute(
        "INSERT INTO albumes (artista_id, titulo, clave, tipo, anio, mbid, carpeta) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
        params![artista, a.album.trim(), clave, tipo, a.anio.filter(|y| (1000..=9999).contains(y)), a.mbid_lanzamiento, carpeta],
    ))?;
    Ok(Some(tx.last_insert_rowid()))
}

/// Da de alta una pista ya colocada en `ruta` (relativa a la música si está
/// dentro). Devuelve su id y los de su artista y álbum.
pub fn dar_de_alta(
    e: &Entorno<'_>,
    ruta: &Path,
    a: &Alta,
    t: &Tecnico,
) -> NsResult<(i64, i64, Option<i64>)> {
    let huella = huella_de_archivo(ruta)?;
    let tamano = std::fs::metadata(ruta).map(|m| m.len()).unwrap_or(0);
    let guardada = ruta
        .strip_prefix(&e.musica)
        .unwrap_or(ruta)
        .to_string_lossy()
        .replace('\\', "/");
    let carpeta = Path::new(&guardada)
        .parent()
        .map(|p| p.to_string_lossy().into_owned())
        .filter(|p| !p.is_empty());
    let mut conn = e.db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    let artista = artista_id(&tx, &a.artista)?;
    let album = album_id(&tx, artista, a, carpeta.as_deref())?;
    let album_titulo: String = match album {
        Some(id) => bd(
            tx.query_row("SELECT titulo FROM albumes WHERE id = ?1", [id], |f| {
                f.get(0)
            }),
        )?,
        None => String::new(),
    };
    let artista_nombre: String = bd(tx.query_row(
        "SELECT nombre FROM artistas WHERE id = ?1",
        [artista],
        |f| f.get(0),
    ))?;
    let titulo = if a.titulo.trim().is_empty() {
        "Sin título"
    } else {
        a.titulo.trim()
    };
    bd(tx.execute(
        "INSERT INTO pistas (album_id, artista_id, titulo, artista_nombre, album_titulo, numero, duracion_seg,
                             anio, genero, isrc, mbid_grabacion, mbid_lanzamiento, tipo_lanzamiento,
                             fuentes_etiquetado, ruta, tamano, sha256, bitrate_kbps, verificada)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17, ?18, ?19)",
        params![
            album,
            artista,
            titulo,
            artista_nombre,
            album_titulo,
            a.numero.filter(|n| *n > 0),
            t.duracion_seg,
            a.anio.filter(|y| (1000..=9999).contains(y)),
            a.genero,
            a.isrc,
            a.mbid_grabacion,
            a.mbid_lanzamiento,
            Some(a.tipo.clone()).filter(|x| !x.is_empty()),
            serde_json::to_string(&a.fuentes).ok(),
            guardada,
            tamano as i64,
            huella,
            t.bitrate_kbps.filter(|b| *b > 0),
            a.verificada,
        ],
    ))?;
    let pista = tx.last_insert_rowid();
    bd(tx.commit())?;
    Ok((pista, artista, album))
}

/// Portada y letra de una pista recién dada de alta: de lo que trae el archivo y,
/// con permiso, de la red. Nada de esto impide que la pista entre.
pub fn completar(
    e: &Entorno<'_>,
    (pista, artista, album): (i64, Option<i64>, Option<i64>),
    ruta: &Path,
    a: &Alta,
    cruda: &Cruda,
    duracion: f64,
) {
    let red = portadas_red::EnLaRed(e.red);
    let sin = |sql: &str, id: i64| -> bool {
        e.db.conexion()
            .ok()
            .and_then(|c| c.query_row(sql, [id], |f| f.get::<_, Option<i64>>(0)).ok())
            .flatten()
            .is_none()
    };
    if let Some(album) = album.filter(|id| sin("SELECT portada_id FROM albumes WHERE id = ?1", *id))
    {
        let imagen = portadas_red::de_etiquetas(ruta).or_else(|| {
            portadas_red::portada_album(
                &red,
                a.mbid_lanzamiento.as_deref().unwrap_or_default(),
                a.mbid_grupo.as_deref().unwrap_or_default(),
                &a.artista,
                &a.album,
            )
        });
        if let Some(id) = imagen.and_then(|i| portadas_red::guardar(e.db, e.rutas, &i).ok()) {
            let _ = actualizar(
                e.db,
                "UPDATE albumes SET portada_id = ?1 WHERE id = ?2",
                params![id, album],
            );
        }
    } else if album.is_none() {
        if let Some(id) = portadas_red::de_etiquetas(ruta)
            .and_then(|i| portadas_red::guardar(e.db, e.rutas, &i).ok())
        {
            let _ = actualizar(
                e.db,
                "UPDATE pistas SET portada_id = ?1 WHERE id = ?2",
                params![id, pista],
            );
        }
    }
    if let Some(artista) =
        artista.filter(|id| sin("SELECT imagen_id FROM artistas WHERE id = ?1", *id))
    {
        if let Some(id) =
            portadas_red::imagen_artista(&red, &a.artista, e.clave_theaudiodb.as_deref())
                .and_then(|i| portadas_red::guardar(e.db, e.rutas, &i).ok())
        {
            let _ = actualizar(
                e.db,
                "UPDATE artistas SET imagen_id = ?1 WHERE id = ?2",
                params![id, artista],
            );
        }
    }
    let (planas, sincronizadas, proveedor) =
        match cruda.letra.as_deref().filter(|l| !l.trim().is_empty()) {
            Some(l) => (l.to_owned(), String::new(), "etiqueta"),
            None => {
                let r = letras_red::buscar(
                    &letras_red::EnLaRed(e.red),
                    &a.artista,
                    &a.titulo,
                    Some(duracion),
                    &a.album,
                );
                (r.planas, r.sincronizadas, r.proveedor)
            }
        };
    if !planas.is_empty() || !sincronizadas.is_empty() {
        let _ = actualizar(
            e.db,
            "INSERT INTO letras (pista_id, planas, sincronizadas, proveedor) VALUES (?1, ?2, ?3, ?4)
             ON CONFLICT (pista_id) DO NOTHING",
            params![pista, Some(planas).filter(|p| !p.is_empty()), Some(sincronizadas).filter(|s| !s.is_empty()), proveedor],
        );
    }
}

fn actualizar(db: &BaseDeDatos, sql: &str, p: impl rusqlite::Params) -> NsResult<()> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    bd(tx.execute(sql, p))?;
    bd(tx.commit())
}

/// Coloca, etiqueta, da de alta y completa. Lo usan la canalización y Por revisar.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si no se puede colocar el archivo ni darlo de alta.
pub fn importar(
    e: &Entorno<'_>,
    origen: &Path,
    a: &Alta,
    t: &Tecnico,
    cruda: &Cruda,
    escribir_etiquetas: bool,
) -> NsResult<i64> {
    let ext = origen.extension().and_then(|x| x.to_str()).unwrap_or("mp3");
    let dentro = origen.starts_with(&e.musica);
    let destino = if e.organizar {
        sin_conflicto(&e.musica.join(ruta_relativa(&Destino {
            artista: &a.artista,
            titulo: &a.titulo,
            album: &a.album,
            tipo: &a.tipo,
            numero: a.numero,
            extension: ext,
        })))
    } else if dentro {
        origen.to_path_buf()
    } else {
        sin_conflicto(&e.musica.join(origen.file_name().unwrap_or_default()))
    };
    if destino != origen {
        colocar(
            origen,
            &destino,
            dentro || origen.starts_with(e.rutas.por_revisar()),
        )?;
    }
    if escribir_etiquetas {
        etiquetas::escribir(
            &destino,
            &Escritura {
                titulo: Some(a.titulo.clone()),
                artista: Some(a.artista.clone()),
                album: Some(a.album.clone()).filter(|x| !x.is_empty()),
                numero: a.numero,
                total: a.total,
                anio: a.anio,
                isrc: a.isrc.clone(),
                mbid_grabacion: a.mbid_grabacion.clone(),
                mbid_lanzamiento: a.mbid_lanzamiento.clone(),
                mbid_grupo: a.mbid_grupo.clone(),
                tipo_lanzamiento: Some(a.tipo.clone()).filter(|x| !x.is_empty()),
            },
        )?;
    }
    let ids = dar_de_alta(e, &destino, a, t)?;
    completar(
        e,
        (ids.0, Some(ids.1), ids.2),
        &destino,
        a,
        cruda,
        t.duracion_seg,
    );
    Ok(ids.0)
}

/// Lo que dicen las fuentes de identificación, con permiso o sin él.
fn identificar(
    e: &Entorno<'_>,
    ruta: &Path,
    duracion: f64,
) -> (Option<DeShazam>, Option<DeAcoustid>) {
    let shazam = shazam::identificar(e.red, ruta, duracion)
        .ok()
        .filter(|s| s.identificado);
    let acoustid = e.clave_acoustid.as_deref().and_then(|clave| {
        let h: Huella = acoustid::calcular(&e.fpcalc, ruta).ok()?;
        let c = acoustid::consultar(e.red, clave, &h).ok()?;
        Some(DeAcoustid {
            grabaciones: c.iter().map(|x| x.mbid_grabacion.clone()).collect(),
            confianzas: c.iter().map(|x| x.confianza).collect(),
        })
    });
    (shazam, acoustid)
}

/// Lo que concluye la identificación de un archivo: con qué se buscó, qué se
/// encontró y qué se decidió. Lo comparten la canalización y "Completar datos".
pub struct Identificada {
    pub norm: Normalizada,
    pub shazam: Option<DeShazam>,
    pub acoustid: Option<DeAcoustid>,
    pub candidatos: Vec<Candidato>,
    pub veredicto: Veredicto,
    pub elegido: Option<Candidato>,
    pub puntaje: f64,
}

/// Shazam y AcoustID, normalización, MusicBrainz, el emparejador (con la IA si
/// está activa) y la segunda y tercera etapas.
///
/// # Errors
///
/// La causa de cuarentena si la normalización no deja nada que buscar.
pub fn identificar_y_decidir(
    e: &Entorno<'_>,
    ruta: &Path,
    cruda: &Cruda,
    tecnico: &Tecnico,
    nombre: &str,
) -> Result<Identificada, CausaCuarentena> {
    let (shazam, acoustid) = identificar(e, ruta, tecnico.duracion_seg);
    let n = normalizacion::normalizar(
        cruda,
        tecnico.duracion_seg,
        nombre,
        shazam.as_ref(),
        acoustid.as_ref(),
    )?;
    let ctx = Contexto {
        norm: &n,
        shazam: shazam.as_ref(),
        acoustid: acoustid.as_ref(),
    };
    let mb = musicbrainz::Cliente::new(musicbrainz::EnLaRed::new(e.red));
    let busqueda = Busqueda {
        artista: n.artista.clone(),
        titulo: n.titulo.clone(),
        featuring: n.featuring.clone(),
        isrc: ctx
            .shazam
            .and_then(|s| s.isrc.clone())
            .or_else(|| n.isrc.clone()),
        duracion_seg: n.duracion_seg,
    };
    let de_acoustid = acoustid
        .as_ref()
        .map(|a| a.grabaciones.clone())
        .unwrap_or_default();
    let candidatos = mb.candidatos(&busqueda, &de_acoustid).unwrap_or_default();
    let cliente_ia =
        e.ia.clone()
            .map(|config| ia::ClienteIa { red: e.red, config });
    let d = emparejador::evaluar(
        candidatos.clone(),
        &ctx,
        cliente_ia
            .as_ref()
            .map(|c| c as &dyn emparejador::Desempate),
    );
    let (mut veredicto, mut elegido, mut puntaje) =
        (d.veredicto, d.elegido.map(|p| p.candidato), d.puntaje);
    if !veredicto.entra() {
        if let Some(p) = etapas::segunda(veredicto, puntaje, &ctx, candidatos.clone(), false) {
            (veredicto, elegido, puntaje) = (p.veredicto, Some(p.candidato), p.puntaje);
        }
    }
    if !veredicto.entra() && etapas::elegible_tercera(veredicto) {
        let hint = e
            .red
            .obtener(
                Servicio::Itunes,
                &etapas::url_itunes(&n.artista, &n.titulo),
                &[],
            )
            .ok()
            .and_then(|b| serde_json::from_slice(&b).ok())
            .and_then(|v| etapas::pista_itunes(&v));
        let otros = match hint.as_ref().and_then(|h| h.isrc.clone()) {
            Some(isrc) if busqueda.isrc.is_none() => mb
                .candidatos(
                    &Busqueda {
                        isrc: Some(isrc),
                        ..busqueda.clone()
                    },
                    &de_acoustid,
                )
                .unwrap_or_default(),
            _ => candidatos.clone(),
        };
        match etapas::tercera(veredicto, puntaje, &ctx, hint.as_ref(), otros) {
            Tercera::Promovida(p) => {
                (veredicto, elegido, puntaje) = (p.veredicto, Some(p.candidato), p.puntaje)
            }
            Tercera::ARevision => veredicto = Veredicto::Revision(CausaRevision::PuntajeIntermedio),
            Tercera::SinCambio => {}
        }
    }
    Ok(Identificada {
        norm: n,
        shazam,
        acoustid,
        candidatos,
        veredicto,
        elegido,
        puntaje,
    })
}

/// Procesa un archivo de principio a fin.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base o la carpeta interna fallan; lo demás
/// acaba en Por revisar.
pub fn procesar(e: &Entorno<'_>, g: &mut Gestor, ruta: &Path) -> NsResult<Resultado> {
    let ext = ruta
        .extension()
        .and_then(|x| x.to_str())
        .unwrap_or_default()
        .to_lowercase();
    if !EXTENSIONES.contains(&ext.as_str()) {
        return Ok(Resultado::Omitido);
    }
    let nombre = ruta
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or_default()
        .to_owned();
    let (tecnico, cruda) = match validar(ruta) {
        Ok(v) => v,
        Err(c) => {
            return a_por_revisar(
                e,
                ruta,
                causa_por_revisar(Veredicto::Cuarentena(c)),
                datos_para_revisar(&nombre, None, None, &[]),
            )
        }
    };
    let huella = huella_de_archivo(ruta).unwrap_or_default();
    if let Some(d) = g.registrar_huella(&huella, &ruta.to_string_lossy()) {
        return a_por_revisar(
            e,
            ruta,
            "duplicado",
            json!({"nombre_original": nombre, "duplicado": referencia(&d)}),
        );
    }
    // Lo que el usuario dejó corregido gana a las fuentes y no necesita red
    // (`overrides` de la V1).
    let corregida = correcciones::buscar(
        e.db,
        &huella,
        cruda.isrc.as_deref(),
        correcciones::clave_artista_titulo(
            cruda.artista.as_deref().unwrap_or_default(),
            cruda.titulo.as_deref().unwrap_or_default(),
        )
        .as_deref(),
    )
    .unwrap_or_default();
    if let Some(mut a) = corregida {
        // Una corrección que solo fija identificadores toma el resto del archivo.
        let tal_cual = alta_tal_cual(&cruda, &nombre, tecnico.duracion_seg);
        if a.titulo.is_empty() {
            a.titulo = tal_cual.titulo;
        }
        if a.artista.is_empty() {
            a.artista = tal_cual.artista;
        }
        let verificada = a.verificada;
        let pista = importar(e, ruta, &a, &tecnico, &cruda, true)?;
        return Ok(Resultado::Importada { pista, verificada });
    }
    let sin_red = e
        .red
        .autorizar(Servicio::MusicBrainz, "https://musicbrainz.org/ws/2/")
        .is_err();
    if sin_red {
        // Solo con las etiquetas: entra sin verificar si dicen qué es.
        let completa = cruda
            .titulo
            .as_deref()
            .is_some_and(|t| !t.trim().is_empty())
            && cruda
                .artista
                .as_deref()
                .is_some_and(|a| !a.trim().is_empty());
        if !completa {
            return a_por_revisar(
                e,
                ruta,
                "sin_candidatos",
                datos_para_revisar(&nombre, Some(&cruda), Some(&tecnico), &[]),
            );
        }
        let a = alta_tal_cual(&cruda, &nombre, tecnico.duracion_seg);
        let pista = importar(e, ruta, &a, &tecnico, &cruda, false)?;
        return Ok(Resultado::Importada {
            pista,
            verificada: false,
        });
    }
    let Identificada {
        norm: n,
        shazam,
        acoustid,
        candidatos,
        veredicto,
        elegido,
        puntaje,
    } = match identificar_y_decidir(e, ruta, &cruda, &tecnico, &nombre) {
        Ok(i) => i,
        Err(c) => {
            return a_por_revisar(
                e,
                ruta,
                causa_por_revisar(Veredicto::Cuarentena(c)),
                datos_para_revisar(&nombre, Some(&cruda), Some(&tecnico), &[]),
            )
        }
    };
    let ctx = Contexto {
        norm: &n,
        shazam: shazam.as_ref(),
        acoustid: acoustid.as_ref(),
    };
    let Some(c) = elegido.filter(|_| veredicto.entra()) else {
        return a_por_revisar(
            e,
            ruta,
            causa_por_revisar(veredicto),
            datos_para_revisar(&nombre, Some(&cruda), Some(&tecnico), &candidatos),
        );
    };
    let calidad = Calidad {
        puntaje,
        con_grabacion: !c.mbid_grabacion.is_empty(),
        con_lanzamiento: !c.mbid_lanzamiento.is_empty(),
        con_isrc_candidato: c.isrc.is_some(),
        con_numero: c.numero.is_some(),
        bitrate_kbps: tecnico.bitrate_kbps,
        etiquetas_con_titulo_y_artista: cruda.titulo.is_some() && cruda.artista.is_some(),
        con_acoustid: acoustid.as_ref().is_some_and(|a| !a.grabaciones.is_empty()),
        con_isrc_archivo: ctx
            .shazam
            .and_then(|s| s.isrc.as_ref())
            .or(n.isrc.as_ref())
            .is_some(),
    }
    .valor();
    let isrc = ctx
        .shazam
        .and_then(|s| s.isrc.clone())
        .or_else(|| n.isrc.clone())
        .or_else(|| c.isrc.clone());
    if let Some(dup) = g.registrar_identidad(
        Some(&c.mbid_grabacion),
        isrc.as_deref(),
        calidad,
        &ruta.to_string_lossy(),
    ) {
        return a_por_revisar(
            e,
            ruta,
            "duplicado",
            json!({"nombre_original": nombre, "duplicado": referencia(&dup)}),
        );
    }
    let mut fuentes = vec!["tag_local"];
    if shazam.is_some() {
        fuentes.push("shazam");
    }
    if acoustid.as_ref().is_some_and(|a| !a.grabaciones.is_empty()) {
        fuentes.push("acoustid");
    }
    fuentes.push("musicbrainz");
    let a = alta_de_candidato(&c, &n, fuentes);
    let visible = Visible {
        titulo: &a.titulo,
        artista: &a.artista,
        album: &a.album,
        duracion: Some(tecnico.duracion_seg),
        portada: None,
    };
    if let Some(dup) = g.duplicado_observable(visible) {
        return a_por_revisar(
            e,
            ruta,
            "duplicado",
            json!({"nombre_original": nombre, "duplicado": referencia(&dup)}),
        );
    }
    match importar(e, ruta, &a, &tecnico, &cruda, true) {
        Ok(pista) => Ok(Resultado::Importada {
            pista,
            verificada: true,
        }),
        Err(NsError::StorageFailure) if ruta.is_file() => a_por_revisar(
            e,
            ruta,
            "escritura_fallida",
            datos_para_revisar(&nombre, Some(&cruda), Some(&tecnico), &candidatos),
        ),
        Err(otro) => Err(otro),
    }
}

fn referencia(d: &Duplicado) -> serde_json::Value {
    let (tipo, r) = match d {
        Duplicado::Exacto(r) => ("exacto", r),
        Duplicado::Identidad(r) => ("identidad", r),
        Duplicado::Mejorable(r) => ("mejorable", r),
        Duplicado::Observable(r) => ("observable", r),
    };
    match r {
        Referencia::Pista(id) => json!({"tipo": tipo, "pista_id": id}),
        Referencia::Archivo(_) => json!({"tipo": tipo, "en_esta_importacion": true}),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::audio::pruebas::wav;
    use crate::net::PoliticaDeRed;

    struct Montaje {
        db: BaseDeDatos,
        rutas: Rutas,
        red: Red,
        musica: PathBuf,
        fuera: PathBuf,
    }

    fn montar(nombre: &str) -> Montaje {
        let dir =
            std::env::temp_dir().join(format!("ns-canalizacion-{nombre}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let rutas = Rutas::bajo(&dir).unwrap();
        let musica = dir.join("musica");
        let fuera = dir.join("descargas");
        std::fs::create_dir_all(&musica).unwrap();
        std::fs::create_dir_all(&fuera).unwrap();
        Montaje {
            db: BaseDeDatos::en_memoria().unwrap(),
            rutas,
            red: Red::new(PoliticaDeRed::default()),
            musica,
            fuera,
        }
    }

    impl Montaje {
        fn entorno(&self) -> Entorno<'_> {
            Entorno {
                db: &self.db,
                rutas: &self.rutas,
                red: &self.red,
                musica: self.musica.clone(),
                clave_acoustid: None,
                clave_theaudiodb: None,
                fpcalc: PathBuf::from("fpcalc"),
                organizar: true,
                importacion: None,
                ia: None,
            }
        }

        fn pista(
            &self,
            nombre: &str,
            segundos: usize,
            titulo: Option<&str>,
            artista: Option<&str>,
        ) -> PathBuf {
            let ruta = self.fuera.join(nombre);
            let _ = wav(&ruta, 44_100, 44_100 * segundos, |i, c| {
                ((i * (c + 3)) % 97) as f32 / 400.0
            });
            etiquetas::escribir(
                &ruta,
                &Escritura {
                    titulo: titulo.map(str::to_owned),
                    artista: artista.map(str::to_owned),
                    album: Some("Sueños líquidos".into()),
                    numero: Some(3),
                    ..Escritura::default()
                },
            )
            .unwrap();
            ruta
        }
    }

    #[test]
    fn lo_corregido_a_mano_gana_a_las_etiquetas_sin_necesitar_red() {
        let m = montar("correccion");
        m.db.conexion()
            .unwrap()
            .execute(
                "INSERT INTO correcciones_catalogo (tipo, valor, cambios) VALUES
                 ('artist_title', 'mana::rayando el sol',
                  '{\"titulo_oficial\": \"Rayando el Sol\", \"artista_principal\": \"Maná\",
                    \"album_oficial\": \"¿Dónde jugarán los niños?\", \"numero\": 4}')",
                [],
            )
            .unwrap();
        let origen = m.pista("x.wav", 20, Some("rayando el sol"), Some("MANA"));
        let r = procesar(&m.entorno(), &mut Gestor::default(), &origen).unwrap();
        let Resultado::Importada { pista, verificada } = r else {
            panic!("{r:?}")
        };
        assert!(!verificada, "lo escrito a mano no cuenta como identificado");
        let (titulo, album, numero): (String, String, i64) =
            m.db.conexion()
                .unwrap()
                .query_row(
                    "SELECT titulo, album_titulo, numero FROM pistas WHERE id = ?1",
                    [pista],
                    |f| Ok((f.get(0)?, f.get(1)?, f.get(2)?)),
                )
                .unwrap();
        assert_eq!(
            (titulo.as_str(), album.as_str(), numero),
            ("Rayando el Sol", "¿Dónde jugarán los niños?", 4)
        );
    }

    #[test]
    fn sin_red_una_pista_con_etiquetas_entra_sin_verificar_y_organizada() {
        let m = montar("sin-red");
        let e = m.entorno();
        let mut g = Gestor::default();
        let origen = m.pista("descarga.wav", 20, Some("Clavado en un bar"), Some("Maná"));
        let r = procesar(&e, &mut g, &origen).unwrap();
        let Resultado::Importada { pista, verificada } = r else {
            panic!("{r:?}")
        };
        assert!(!verificada);
        assert!(origen.is_file(), "lo de fuera de la música no se toca");
        let (ruta, titulo, album, v): (String, String, String, bool) =
            m.db.conexion()
                .unwrap()
                .query_row(
                    "SELECT ruta, titulo, album_titulo, verificada FROM pistas WHERE id = ?1",
                    [pista],
                    |f| Ok((f.get(0)?, f.get(1)?, f.get(2)?, f.get(3)?)),
                )
                .unwrap();
        assert_eq!(
            ruta,
            "maná/albumes/sueños_líquidos/03_clavado_en_un_bar.wav"
        );
        assert!(m.musica.join(&ruta).is_file());
        assert_eq!(
            (titulo.as_str(), album.as_str(), v),
            ("Clavado en un bar", "Sueños líquidos", false)
        );
        let otra = m.pista("copia.wav", 20, Some("Clavado en un bar"), Some("Maná"));
        std::fs::copy(&origen, &otra).unwrap();
        let r = procesar(&e, &mut g, &otra).unwrap();
        assert!(
            matches!(
                r,
                Resultado::PorRevisar {
                    causa: "duplicado",
                    ..
                }
            ),
            "{r:?}"
        );
    }

    #[test]
    fn lo_que_no_se_puede_importar_va_a_por_revisar_con_su_causa() {
        let m = montar("revisar");
        let e = m.entorno();
        let mut g = Gestor::default();
        let corta = m.pista("corta.wav", 5, Some("x"), Some("y"));
        assert!(matches!(
            procesar(&e, &mut g, &corta).unwrap(),
            Resultado::PorRevisar {
                causa: "duracion_invalida",
                ..
            }
        ));
        let rota = m.fuera.join("rota.mp3");
        std::fs::write(&rota, vec![7u8; 20_000]).unwrap();
        assert!(matches!(
            procesar(&e, &mut g, &rota).unwrap(),
            Resultado::PorRevisar {
                causa: "audio_ilegible",
                ..
            }
        ));
        let sin = m.pista("01.wav", 20, None, None);
        assert!(matches!(
            procesar(&e, &mut g, &sin).unwrap(),
            Resultado::PorRevisar {
                causa: "sin_candidatos",
                ..
            }
        ));
        assert_eq!(
            procesar(&e, &mut g, &m.fuera.join("notas.txt")).unwrap(),
            Resultado::Omitido
        );
        let n: i64 =
            m.db.conexion()
                .unwrap()
                .query_row("SELECT count(*) FROM por_revisar", [], |f| f.get(0))
                .unwrap();
        assert_eq!(n, 3);
        let guardados = std::fs::read_dir(m.rutas.por_revisar()).unwrap().count();
        assert_eq!(guardados, 3, "cada uno con su copia en la carpeta interna");
    }

    #[test]
    fn cada_causa_interna_tiene_su_causa_de_por_revisar() {
        use CausaCuarentena as Q;
        use CausaRevision as R;
        let validas = [
            "candidatos_ambiguos",
            "puntaje_intermedio",
            "duracion_marginal",
            "release_type_dudoso",
            "sin_candidatos",
            "metadata_insuficiente",
            "puntaje_bajo",
            "escritura_fallida",
            "validacion_post_escritura",
            "duplicado",
            "duracion_invalida",
            "audio_ilegible",
        ];
        let todas = [
            Veredicto::Revision(R::PuntajeIntermedio),
            Veredicto::Revision(R::CandidatosAmbiguos),
            Veredicto::Revision(R::OwnershipAmbiguo),
            Veredicto::Revision(R::ReleaseTypeDudoso),
            Veredicto::Revision(R::DuracionMarginal),
            Veredicto::Revision(R::IaRevisionManual),
            Veredicto::Revision(R::FuentesDiscrepantes),
            Veredicto::Revision(R::ClasificacionProvisional),
            Veredicto::Cuarentena(Q::ArchivoCorrupto),
            Veredicto::Cuarentena(Q::ArchivoMuyPequeno),
            Veredicto::Cuarentena(Q::ArchivoIlegible),
            Veredicto::Cuarentena(Q::DuracionInvalida),
            Veredicto::Cuarentena(Q::BitrateInsuficiente),
            Veredicto::Cuarentena(Q::MetadataInsuficiente),
            Veredicto::Cuarentena(Q::MetadataFinalInvalida),
            Veredicto::Cuarentena(Q::SinCandidatos),
            Veredicto::Cuarentena(Q::PuntajeBajo),
            Veredicto::Cuarentena(Q::OwnershipInvalido),
            Veredicto::Cuarentena(Q::EscrituraFallida),
            Veredicto::Cuarentena(Q::ValidacionPostEscritura),
            Veredicto::Cuarentena(Q::ErrorInesperado),
        ];
        for v in todas {
            assert!(validas.contains(&causa_por_revisar(v)), "{v:?}");
        }
    }
}
