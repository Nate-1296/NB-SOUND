//! Importador de la V1 (F1.2.2).
//!
//! Contrato: docs/adr/decisions/ADR-004-datos.md y el inventario columna a
//! columna de docs/engineering/migracion-v1.md. Se ejecuta una sola vez, la
//! primera vez que la V2 encuentra la base de la V1, y tiene tres reglas:
//!
//! 1. **La V1 no se toca.** Su base se abre en solo lectura (`mode=ro`) y sus
//!    archivos solo se leen; una prueba compara el hash antes y después.
//! 2. **Los identificadores se conservan**, y las `sync_version` también, porque
//!    NB Sound Mobile los tiene guardados (ADR-005).
//! 3. **Todo o nada** en la base: las filas entran en una sola transacción. Las
//!    copias de archivos van antes y son por contenido, así que repetirlas tras
//!    un fallo no duplica nada.

pub mod archivos;
pub mod claves;
mod copia;
mod manifiestos;

use std::collections::{BTreeMap, HashMap};
use std::path::{Path, PathBuf};

use rusqlite::{Connection, OpenFlags, OptionalExtension};
use serde::Serialize;
use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::db::{self, BaseDeDatos};
use crate::error::{NsError, NsResult};
use crate::net::{PoliticaDeRed, Servicio};
use crate::paths::Rutas;

use self::archivos::Copiado;
use self::manifiestos::LetraV1;

/// Lo que se importó, para el informe que ve el usuario y para la prueba de
/// conservación. Solo cifras: nada de títulos ni rutas.
#[derive(Debug, Clone, Default, Serialize, PartialEq, Eq)]
pub struct Informe {
    /// Filas por tabla de la V2.
    pub filas: BTreeMap<String, i64>,
    /// Archivos que la V1 citaba y ya no existen (portadas, instrumentales,
    /// archivos por revisar). No se importan, y se cuentan.
    pub archivos_ausentes: u64,
    /// Líneas de los manifiestos de la V1 que no se pudieron leer.
    pub lineas_ilegibles: u64,
    /// Claves de servicio que pasaron al llavero.
    pub claves_al_llavero: u32,
    /// Claves que no se pudieron guardar porque el sistema no tiene llavero. No
    /// se guardan en ningún otro sitio: el usuario tendrá que volver a pegarlas.
    pub claves_no_migradas: u32,
}

/// Clave de `instalacion` que marca la importación hecha.
const MARCA: &str = "importada_v1";

/// Abre la base de la V1 en solo lectura. `immutable` no: la V1 puede estar
/// abierta, y SQLite tiene que ver su `-wal`.
fn uri_solo_lectura(ruta: &Path) -> String {
    let texto = ruta.to_string_lossy().replace('\\', "/");
    let mut uri = String::from("file:");
    // `C:/…` necesita la barra delante para ser una ruta absoluta en una URI.
    if !texto.starts_with('/') {
        uri.push('/');
    }
    for byte in texto.bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'.' | b'_' | b'~' | b'/' | b':' => {
                uri.push(byte as char);
            }
            _ => uri.push_str(&format!("%{byte:02X}")),
        }
    }
    uri.push_str("?mode=ro");
    uri
}

fn bd<T>(resultado: rusqlite::Result<T>, que: &'static str) -> NsResult<T> {
    resultado.map_err(|error| {
        tracing::error!(paso = que, error = %error, "falló la importación de la V1");
        NsError::StorageFailure
    })
}

/// La configuración de la V1 (`config_ui`), sin las claves de servicios, que no
/// pasan por aquí (F1.2.4).
fn configuracion(v1: &Connection) -> NsResult<HashMap<String, String>> {
    let mut sentencia = bd(
        v1.prepare(
            "SELECT clave, valor FROM config_ui
             WHERE valor IS NOT NULL AND clave NOT LIKE '%\\_key' ESCAPE '\\'",
        ),
        "configuración",
    )?;
    let filas = bd(
        sentencia.query_map([], |f| Ok((f.get::<_, String>(0)?, f.get::<_, String>(1)?))),
        "configuración",
    )?;
    filas
        .collect::<rusqlite::Result<_>>()
        .map_err(|_| NsError::StorageFailure)
}

/// Solo las claves de servicio de `config_ui`, que van al llavero y a ningún
/// otro sitio.
fn claves_de_servicio(v1: &Connection) -> NsResult<HashMap<String, String>> {
    let mut sentencia = bd(
        v1.prepare(
            "SELECT clave, valor FROM config_ui
             WHERE valor IS NOT NULL AND clave LIKE '%\\_key' ESCAPE '\\'",
        ),
        "claves",
    )?;
    let filas = bd(
        sentencia.query_map([], |f| Ok((f.get::<_, String>(0)?, f.get::<_, String>(1)?))),
        "claves",
    )?;
    filas
        .collect::<rusqlite::Result<_>>()
        .map_err(|_| NsError::StorageFailure)
}

fn carpeta(config: &HashMap<String, String>, clave: &str) -> Option<PathBuf> {
    config
        .get(clave)
        .map(|v| v.trim())
        .filter(|v| !v.is_empty())
        .map(PathBuf::from)
}

fn extension(ruta: &Path) -> String {
    ruta.extension()
        .and_then(|e| e.to_str())
        .map_or_else(|| "bin".to_owned(), str::to_ascii_lowercase)
}

/// Una portada ya copiada, con lo que pide su fila.
struct Portada {
    copiado: Copiado,
    ancho: u32,
    alto: u32,
    mime: &'static str,
}

fn copiar_portada(
    origen: &Path,
    destino: &Path,
    informe: &mut Informe,
) -> NsResult<Option<Portada>> {
    let Some((ancho, alto, mime)) = archivos::dimensiones(origen) else {
        // Ni JPEG ni PNG legible: la V1 tampoco podía mostrarla.
        informe.archivos_ausentes += 1;
        return Ok(None);
    };
    let extension = if mime == "image/png" { "png" } else { "jpg" };
    match archivos::copiar_por_contenido(origen, destino, extension) {
        Ok(copiado) => Ok(Some(Portada {
            copiado,
            ancho,
            alto,
            mime,
        })),
        Err(NsError::FileNotFound) => {
            informe.archivos_ausentes += 1;
            Ok(None)
        }
        Err(otro) => Err(otro),
    }
}

/// Lo que se prepara fuera de la transacción: archivos copiados y datos que no
/// están en la base de la V1.
#[derive(Default)]
struct Preparado {
    portadas_album: Vec<(i64, Portada)>,
    imagenes_artista: Vec<(i64, Portada)>,
    instrumentales: Vec<(i64, Copiado, Option<String>)>,
    letras: Vec<(i64, LetraV1)>,
    por_revisar: Vec<i64>,
    foto_perfil: Option<Copiado>,
}

fn preparar(
    v1: &Connection,
    config: &HashMap<String, String>,
    rutas: &Rutas,
    informe: &mut Informe,
) -> NsResult<Preparado> {
    let mut p = Preparado::default();
    let assets = carpeta(config, "dir_assets");
    let recursos = assets
        .as_ref()
        .map(|a| manifiestos::recursos(&a.join("assets_manifest.jsonl")))
        .unwrap_or_default();
    informe.lineas_ilegibles += recursos.saltadas as u64;

    // Una portada por álbum: la de alta resolución si la V1 la tenía, y si no la
    // normal (P11, decisión de Nathan). La V2 deriva de ella los tamaños pequeños.
    let albumes: Vec<(i64, Option<String>, Option<String>)> = {
        let mut s = bd(
            v1.prepare("SELECT id, mb_release_id, portada_ruta FROM albums"),
            "álbumes",
        )?;
        let filas = bd(
            s.query_map([], |f| Ok((f.get(0)?, f.get(1)?, f.get(2)?))),
            "álbumes",
        )?;
        filas
            .collect::<rusqlite::Result<_>>()
            .map_err(|_| NsError::StorageFailure)?
    };
    for (id, release, normal) in albumes {
        let origen = release
            .and_then(|r| recursos.album_hd.get(&r).cloned())
            .or_else(|| normal.filter(|n| !n.is_empty()).map(PathBuf::from));
        if let Some(origen) = origen {
            if let Some(portada) = copiar_portada(&origen, &rutas.portadas(), informe)? {
                p.portadas_album.push((id, portada));
            }
        }
    }

    // La V1 resolvía la imagen de un artista por su nombre; la V2, por su id.
    let artistas: Vec<(i64, String)> = {
        let mut s = bd(v1.prepare("SELECT id, nombre FROM artistas"), "artistas")?;
        let filas = bd(s.query_map([], |f| Ok((f.get(0)?, f.get(1)?))), "artistas")?;
        filas
            .collect::<rusqlite::Result<_>>()
            .map_err(|_| NsError::StorageFailure)?
    };
    for (id, nombre) in artistas {
        if let Some(origen) = recursos.artista.get(&nombre) {
            if let Some(portada) = copiar_portada(origen, &rutas.portadas(), informe)? {
                p.imagenes_artista.push((id, portada));
            }
        }
    }

    let pistas: Vec<(i64, String, Option<String>, Option<String>)> = {
        let mut s = bd(
            v1.prepare(
                "SELECT id, ruta_archivo, karaoke_ruta_instrumental, karaoke_actualizado_en
                 FROM pistas",
            ),
            "pistas",
        )?;
        let filas = bd(
            s.query_map([], |f| Ok((f.get(0)?, f.get(1)?, f.get(2)?, f.get(3)?))),
            "pistas",
        )?;
        filas
            .collect::<rusqlite::Result<_>>()
            .map_err(|_| NsError::StorageFailure)?
    };
    for (id, _, instrumental, cuando) in &pistas {
        let Some(instrumental) = instrumental.as_deref().filter(|i| !i.is_empty()) else {
            continue;
        };
        let origen = Path::new(instrumental);
        match archivos::copiar_por_contenido(origen, &rutas.stems(), &extension(origen)) {
            Ok(copiado) => p.instrumentales.push((*id, copiado, cuando.clone())),
            Err(NsError::FileNotFound) => informe.archivos_ausentes += 1,
            Err(otro) => return Err(otro),
        }
    }

    // Las letras vivían en un manifiesto indexado por la ruta del archivo.
    if let Some(assets) = &assets {
        let (letras, saltadas) =
            manifiestos::letras(&assets.join("enrichment").join("enrichment_manifest.jsonl"));
        informe.lineas_ilegibles += saltadas as u64;
        for (id, ruta, _, _) in &pistas {
            if let Some(letra) = letras.get(ruta) {
                p.letras.push((*id, letra.clone()));
            }
        }
    }

    // Por revisar: solo lo pendiente cuyo archivo siga existiendo (ADR-004).
    let pendientes: Vec<(i64, String)> = {
        let mut s = bd(
            v1.prepare("SELECT id, ruta_archivo FROM archivos_pendientes WHERE resuelto = 0"),
            "por revisar",
        )?;
        let filas = bd(
            s.query_map([], |f| Ok((f.get(0)?, f.get(1)?))),
            "por revisar",
        )?;
        filas
            .collect::<rusqlite::Result<_>>()
            .map_err(|_| NsError::StorageFailure)?
    };
    for (id, ruta) in pendientes {
        if Path::new(&ruta).is_file() {
            p.por_revisar.push(id);
        } else {
            informe.archivos_ausentes += 1;
        }
    }

    if let Some(foto) = carpeta(config, "foto_perfil") {
        match archivos::copiar_por_contenido(&foto, &rutas.datos.join("perfil"), &extension(&foto))
        {
            Ok(copiado) => p.foto_perfil = Some(copiado),
            Err(NsError::FileNotFound) => informe.archivos_ausentes += 1,
            Err(otro) => return Err(otro),
        }
    }
    Ok(p)
}

fn sha256_texto(texto: &str) -> String {
    Sha256::digest(texto.as_bytes())
        .iter()
        .fold(String::with_capacity(64), |mut s, b| {
            use std::fmt::Write as _;
            let _ = write!(s, "{b:02x}");
            s
        })
}

fn verdadero(config: &HashMap<String, String>, clave: &str) -> bool {
    config
        .get(clave)
        .is_some_and(|v| matches!(v.trim(), "1" | "true" | "True"))
}

/// Los servicios que el usuario ya había activado en la V1. Se respetan como
/// consentimiento dado; Agregados no existía y no se concede.
fn politica_de_red(config: &HashMap<String, String>) -> PoliticaDeRed {
    let v = |clave| verdadero(config, clave);
    let letras = v("enable_lyrics_enrichment");
    let concedidos = [
        (Servicio::AcoustId, v("enable_acoustid")),
        // La V1 consultaba MusicBrainz siempre que el enriquecimiento estaba activo.
        (Servicio::MusicBrainz, v("enable_external_enrichment")),
        (Servicio::CoverArtArchive, v("enable_cover_art_archive")),
        (Servicio::Shazam, v("enable_shazam")),
        (
            Servicio::Itunes,
            v("enable_itunes_cover_fallback") || v("enable_itunes_artist_images"),
        ),
        (Servicio::Lrclib, letras && v("enable_lrclib")),
        (Servicio::LyricsOvh, letras && v("enable_lyrics_ovh")),
        (Servicio::Deezer, v("enable_deezer_artist_images")),
        (Servicio::Wikipedia, v("enable_wikipedia_artist_images")),
        (Servicio::TheAudioDb, v("enable_theaudiodb_artist_images")),
        (
            Servicio::ProveedorIa,
            v("enable_ia_tiebreak") || v("enable_ia_discography"),
        ),
    ];
    let servicios: std::collections::BTreeSet<_> = concedidos
        .into_iter()
        .filter_map(|(s, si)| si.then_some(s))
        .collect();
    PoliticaDeRed {
        general: !servicios.is_empty(),
        servicios,
    }
}

/// Las preferencias que la V2 conserva, con su tipo. El resto de `config_ui` se
/// descarta por los motivos del inventario.
fn preferencias(
    config: &HashMap<String, String>,
    preparado: &Preparado,
) -> Vec<(&'static str, Value)> {
    let texto = |clave: &str| {
        config
            .get(clave)
            .map(|v| v.trim().to_owned())
            .filter(|v| !v.is_empty())
    };
    let numero = |clave: &str| texto(clave).and_then(|v| v.parse::<f64>().ok());
    let mut p: Vec<(&'static str, Value)> = Vec::new();
    let mut poner = |clave: &'static str, valor: Option<Value>| {
        if let Some(valor) = valor {
            p.push((clave, valor));
        }
    };
    poner("tema", texto("tema").map(Value::from));
    poner("tipografia", texto("ui_font_family").map(Value::from));
    poner("escala", numero("ui_scale").map(Value::from));
    poner("nombre_usuario", texto("nombre_usuario").map(Value::from));
    poner(
        "foto_perfil",
        preparado
            .foto_perfil
            .as_ref()
            .map(|c| Value::from(c.relativa.clone())),
    );
    poner("carpeta_musica", texto("dir_biblioteca").map(Value::from));
    poner("ultima_vista", texto("ultima_vista").map(Value::from));
    poner(
        "vista_biblioteca",
        texto("vista_biblioteca").map(Value::from),
    );
    poner(
        "ecualizador_activo",
        texto("eq_activo").map(|_| Value::from(verdadero(config, "eq_activo"))),
    );
    poner(
        "ecualizador_bandas",
        texto("eq_bandas")
            .and_then(|v| serde_json::from_str::<Vec<f64>>(&v).ok())
            .map(Value::from),
    );
    poner(
        "ecualizador_preamplificacion",
        numero("eq_preamp").map(Value::from),
    );
    poner("ecualizador_preajuste", texto("eq_preset").map(Value::from));
    poner("copia_carpeta", texto("backup_carpeta").map(Value::from));
    poner(
        "copia_cada_dias",
        numero("backup_frecuencia_dias").map(Value::from),
    );
    poner(
        "servidor_movil_al_arrancar",
        texto("sync_auto_encender").map(|_| Value::from(verdadero(config, "sync_auto_encender"))),
    );
    poner(
        "analisis_activado",
        texto("enable_audio_features")
            .map(|_| Value::from(verdadero(config, "enable_audio_features"))),
    );
    poner(
        "analizar_al_importar",
        texto("audio_features_analyze_on_import")
            .map(|_| Value::from(verdadero(config, "audio_features_analyze_on_import"))),
    );
    poner(
        "analisis_en_segundo_plano",
        texto("audio_intelligence_background")
            .map(|_| Value::from(verdadero(config, "audio_intelligence_background"))),
    );
    poner(
        "politica_de_red",
        serde_json::to_value(politica_de_red(config)).ok(),
    );
    p
}

/// Importa la V1 si no se importó ya. Devuelve `None` si ya estaba hecho.
///
/// # Errors
///
/// - [`NsError::FileNotFound`] si no existe la base de la V1.
/// - [`NsError::StorageFailure`] si falla la lectura, una copia o la escritura.
///   La base de la V2 queda como estaba.
pub fn importar(
    base_v1: &Path,
    env_v1: Option<&Path>,
    db: &BaseDeDatos,
    rutas: &Rutas,
    llavero: &dyn claves::Llavero,
) -> NsResult<Option<Informe>> {
    if !base_v1.is_file() {
        return Err(NsError::FileNotFound);
    }
    {
        let conn = db.conexion()?;
        let hecha: Option<String> = bd(
            conn.query_row(
                "SELECT valor FROM instalacion WHERE clave = ?1",
                [MARCA],
                |f| f.get(0),
            )
            .optional(),
            "marca",
        )?;
        if hecha.is_some() {
            return Ok(None);
        }
    }

    let uri = uri_solo_lectura(base_v1);
    let mut informe = Informe::default();
    let (config, claves_v1, preparado) = {
        let v1 = bd(
            Connection::open_with_flags(
                &uri,
                OpenFlags::SQLITE_OPEN_READ_ONLY
                    | OpenFlags::SQLITE_OPEN_URI
                    | OpenFlags::SQLITE_OPEN_NO_MUTEX,
            ),
            "abrir la V1",
        )?;
        let config = configuracion(&v1)?;
        let claves_v1 = claves_de_servicio(&v1)?;
        let preparado = preparar(&v1, &config, rutas, &mut informe)?;
        (config, claves_v1, preparado)
    };

    let mut conn = db.conexion()?;
    bd(
        conn.execute("ATTACH DATABASE ?1 AS v1", [&uri]),
        "adjuntar la V1",
    )?;
    let resultado = escribir(&mut conn, &config, &preparado, &mut informe);
    // Se suelta pase lo que pase: la conexión vuelve al pool.
    let _ = conn.execute("DETACH DATABASE v1", []);
    resultado?;

    // Después de confirmar: si el llavero falla, la biblioteca ya está importada,
    // y las claves siguen en la V1, que no se ha tocado.
    let claves = claves::migrar(&claves_v1, env_v1, llavero);
    informe.claves_al_llavero = claves.migradas;
    informe.claves_no_migradas = claves.no_migradas;

    tracing::info!(
        pistas = informe.filas.get("pistas").copied().unwrap_or(0),
        ausentes = informe.archivos_ausentes,
        ilegibles = informe.lineas_ilegibles,
        "importación de la V1 terminada"
    );
    Ok(Some(informe))
}

fn escribir(
    conn: &mut Connection,
    config: &HashMap<String, String>,
    p: &Preparado,
    informe: &mut Informe,
) -> NsResult<()> {
    let mut musica = config
        .get("dir_biblioteca")
        .map(|v| v.trim().to_owned())
        .unwrap_or_default();
    if !musica.is_empty() && !musica.ends_with(['/', '\\']) {
        musica.push(std::path::MAIN_SEPARATOR);
    }

    let tx = db::transaccion_de_escritura(conn)?;
    // Las filas de la V1 traen su `sync_version`; los disparadores no pueden
    // darles otra.
    bd(
        tx.execute("UPDATE sincronizacion SET pausada = 1", []),
        "pausar",
    )?;

    for (tabla, sql) in copia::SENTENCIAS {
        let r = if sql.contains(":musica") {
            tx.execute(sql, rusqlite::named_params! { ":musica": musica })
        } else {
            tx.execute(sql, [])
        };
        bd(r, tabla)?;
    }

    // Dispositivos: el token se guarda como hash (F1.1.5).
    {
        let mut leer = bd(
            tx.prepare(
                "SELECT id, device_token, nombre, plataforma, ultima_conexion, ultima_sync_version,
                        seleccion_json, creado_en, revocado
                 FROM v1.sync_dispositivos",
            ),
            "dispositivos",
        )?;
        let mut escribir = bd(
            tx.prepare(
                "INSERT INTO dispositivos (id, token_sha256, nombre, plataforma, ultima_conexion,
                                           ultima_sync_version, seleccion, creado_en, revocado)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6,
                         CASE WHEN json_valid(?7) THEN ?7 END, ?8, ?9)",
            ),
            "dispositivos",
        )?;
        let mut filas = bd(leer.query([]), "dispositivos")?;
        while let Some(f) = bd(filas.next(), "dispositivos")? {
            let token: String = bd(f.get(1), "dispositivos")?;
            bd(
                escribir.execute(rusqlite::params![
                    f.get::<_, i64>(0).map_err(|_| NsError::StorageFailure)?,
                    sha256_texto(&token),
                    f.get::<_, String>(2).map_err(|_| NsError::StorageFailure)?,
                    f.get::<_, Option<String>>(3)
                        .map_err(|_| NsError::StorageFailure)?,
                    f.get::<_, Option<String>>(4)
                        .map_err(|_| NsError::StorageFailure)?,
                    f.get::<_, i64>(5).map_err(|_| NsError::StorageFailure)?,
                    f.get::<_, Option<String>>(6)
                        .map_err(|_| NsError::StorageFailure)?,
                    f.get::<_, String>(7).map_err(|_| NsError::StorageFailure)?,
                    f.get::<_, i64>(8).map_err(|_| NsError::StorageFailure)?,
                ]),
                "dispositivos",
            )?;
        }
    }
    bd(tx.execute(copia::TRANSFERENCIAS, []), "transferencias")?;

    // Portadas: una fila por contenido, aunque dos álbumes compartan imagen.
    {
        let mut insertar = bd(
            tx.prepare(
                "INSERT INTO portadas (sha256, ruta, ancho, alto, bytes, mime, origen)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, 'v1')
                 ON CONFLICT (sha256) DO UPDATE SET sha256 = excluded.sha256
                 RETURNING id",
            ),
            "portadas",
        )?;
        let mut id_de = |portada: &Portada| -> NsResult<i64> {
            bd(
                insertar.query_row(
                    rusqlite::params![
                        portada.copiado.sha256,
                        portada.copiado.relativa,
                        portada.ancho,
                        portada.alto,
                        portada.copiado.bytes as i64,
                        portada.mime,
                    ],
                    |f| f.get(0),
                ),
                "portadas",
            )
        };
        for (album, portada) in &p.portadas_album {
            let id = id_de(portada)?;
            bd(
                tx.execute(
                    "UPDATE albumes SET portada_id = ?1 WHERE id = ?2",
                    [id, *album],
                ),
                "portadas",
            )?;
        }
        for (artista, portada) in &p.imagenes_artista {
            let id = id_de(portada)?;
            bd(
                tx.execute(
                    "UPDATE artistas SET imagen_id = ?1 WHERE id = ?2",
                    [id, *artista],
                ),
                "portadas",
            )?;
        }
    }

    // Stems: una pista con su instrumental en disco está lista, diga lo que diga
    // su estado en la V1; las demás que esperaban en cola, pendientes.
    for (pista, copiado, cuando) in &p.instrumentales {
        bd(
            tx.execute(
                "INSERT INTO stems (pista_id, estado, instrumental, bytes, modelo, terminada_en)
                 VALUES (?1, 'lista', ?2, ?3, 'htdemucs', ?4)",
                rusqlite::params![pista, copiado.relativa, copiado.bytes as i64, cuando],
            ),
            "stems",
        )?;
    }
    bd(
        tx.execute(
            "INSERT INTO stems (pista_id, estado)
             SELECT id, 'pendiente' FROM v1.pistas
             WHERE karaoke_estado = 'en_cola' AND id NOT IN (SELECT pista_id FROM stems)",
            [],
        ),
        "stems",
    )?;

    for (pista, letra) in &p.letras {
        bd(
            tx.execute(
                "INSERT INTO letras (pista_id, planas, sincronizadas, proveedor, idioma, obtenidas_en)
                 VALUES (?1, ?2, ?3, ?4, ?5,
                         coalesce(?6, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))",
                rusqlite::params![
                    pista,
                    letra.planas,
                    letra.sincronizadas,
                    letra.proveedor,
                    letra.idioma,
                    letra.obtenidas_en,
                ],
            ),
            "letras",
        )?;
    }

    for id in &p.por_revisar {
        bd(
            tx.execute(
                "INSERT INTO por_revisar (id, ruta, causa, metadatos, importacion_id, registrado_en)
                 SELECT id, ruta_archivo, causa,
                        CASE WHEN json_valid(manifiesto_json) THEN manifiesto_json END,
                        CASE WHEN sesion_id IN (SELECT id FROM importaciones) THEN sesion_id END,
                        registrado_en
                 FROM v1.archivos_pendientes WHERE id = ?1",
                [id],
            ),
            "por revisar",
        )?;
    }

    // El reproductor y la sesión del DJ, que la V1 guardaba como texto suelto.
    let entero = |clave: &str| config.get(clave).and_then(|v| v.trim().parse::<i64>().ok());
    let real = |clave: &str| config.get(clave).and_then(|v| v.trim().parse::<f64>().ok());
    let repeticion = config
        .get("modo_repeticion")
        .map(|v| v.trim())
        .filter(|v| matches!(*v, "ninguno" | "todo" | "uno"))
        .unwrap_or("ninguno");
    bd(
        tx.execute(
            "UPDATE estado_reproductor SET
                 pista_id = (SELECT id FROM pistas WHERE id = ?1),
                 posicion_cola = max(?2, 0),
                 posicion_seg = max(coalesce(?3, 0), 0),
                 volumen = min(max(coalesce(?4, 100) / 100.0, 0), 1),
                 aleatorio = ?5, repeticion = ?6, normalizar = ?7",
            rusqlite::params![
                entero("reproductor_pista_id"),
                entero("reproductor_pos_cola"),
                real("reproductor_pos_seg"),
                real("volumen"),
                verdadero(config, "modo_aleatorio"),
                repeticion,
                config
                    .get("audio_normalizar")
                    .is_none_or(|_| verdadero(config, "audio_normalizar")),
            ],
        ),
        "estado del reproductor",
    )?;
    bd(
        tx.execute(
            "UPDATE dj_en_curso SET
                 sesion_id = (SELECT id FROM dj_sesiones WHERE id = ?1),
                 indice = max(?2, 0),
                 posicion_seg = max(coalesce(?3, 0), 0),
                 posicion_global_seg = max(coalesce(?4, 0), 0),
                 volumen = min(max(coalesce(?5, 1), 0), 1)",
            rusqlite::params![
                entero("dj_sesion_id"),
                entero("dj_indice_pista"),
                real("dj_pos_pista_seg"),
                real("dj_pos_global_seg"),
                real("dj_volumen"),
            ],
        ),
        "sesión del DJ",
    )?;

    for (clave, valor) in preferencias(config, p) {
        bd(
            tx.execute(
                "INSERT INTO preferencias (clave, valor) VALUES (?1, ?2)",
                rusqlite::params![clave, valor.to_string()],
            ),
            "preferencias",
        )?;
    }

    // El contador de la V1, para que el siguiente cambio sea mayor que todo lo
    // que el móvil vio, y la sincronización vuelve a andar.
    bd(
        tx.execute(
            "UPDATE sincronizacion SET pausada = 0, version = max(version, coalesce(
                 (SELECT CAST(valor AS INTEGER) FROM v1.sync_estado
                  WHERE clave = 'sync_version_actual'), 0))",
            [],
        ),
        "sincronización",
    )?;
    bd(
        tx.execute(
            "INSERT INTO instalacion (clave, valor) VALUES (?1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
            [MARCA],
        ),
        "marca",
    )?;

    for tabla in [
        "artistas",
        "albumes",
        "pistas",
        "portadas",
        "letras",
        "playlists",
        "playlist_pistas",
        "historial",
        "cola",
        "rasgos",
        "analisis_profundo",
        "etiquetas_ambiente",
        "stems",
        "importaciones",
        "por_revisar",
        "correcciones_catalogo",
        "dispositivos",
        "tumbas",
        "transferencias_stems",
        "dj_sesiones",
        "dj_sesion_pistas",
        "dj_eventos",
        "dj_preferencias",
        "preferencias",
    ] {
        let n: i64 = bd(
            tx.query_row(&format!("SELECT count(*) FROM {tabla}"), [], |f| f.get(0)),
            "informe",
        )?;
        informe.filas.insert(tabla.to_owned(), n);
    }
    bd(tx.commit(), "confirmar")?;
    Ok(())
}

#[cfg(test)]
mod pruebas;
