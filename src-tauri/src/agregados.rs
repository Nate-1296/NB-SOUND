//! Los agregados (ADR-006): lo grande y opcional, que se instala con un clic.
//!
//! **El catálogo se compila dentro del binario** (F5.1.1): cada agregado es un ZIP
//! publicado en las Releases del repositorio, con su URL, su tamaño y su SHA-256
//! fijados aquí. Lo que aún no tiene archivo publicado (P13) lleva `url: None`: se
//! ve en Ajustes como "todavía no disponible" y no se puede instalar, en lugar de
//! inventar una dirección.
//!
//! **La instalación** (F5.1.2): se descarga a `agregados/.descargas/` como
//! `<id>-<versión>.zip.parcial`, que sobrevive a un cierre y se reanuda con
//! `Range`; se verifica el SHA-256 del ZIP entero antes de abrirlo; se extrae a una
//! carpeta temporal junto a la definitiva y se cambia de nombre al final. Una
//! descarga cortada o un hash alterado no dejan nada instalado. **La lista de
//! instalados es la carpeta** (`paths.rs`): un agregado está instalado si existe
//! `agregados/<id>/agregado.json`; quitarlo es apartar su carpeta y borrarla.

use std::fs::File;
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use ts_rs::TS;

use crate::error::{NsError, NsResult};
use crate::net::{Destino, Red, Servicio};
use crate::paths::Rutas;

/// Los agregados de ADR-006.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub enum IdAgregado {
    /// `htdemucs` en ONNX fp16 (F0.4.2).
    Karaoke,
    /// MusiCNN y sus siete cabezas en ONNX (F0.4.3).
    Analisis,
    /// `all-MiniLM-L6-v2` en ONNX, para los pedidos al DJ (Fase 6).
    TextoDj,
    /// El proveedor de ONNX Runtime para la GPU (CUDA, DirectML o CoreML).
    Aceleracion,
}

impl IdAgregado {
    pub const TODOS: [IdAgregado; 4] = [
        IdAgregado::Karaoke,
        IdAgregado::Analisis,
        IdAgregado::TextoDj,
        IdAgregado::Aceleracion,
    ];

    /// El nombre de su carpeta.
    #[must_use]
    pub fn carpeta(self) -> &'static str {
        match self {
            Self::Karaoke => "karaoke",
            Self::Analisis => "analisis",
            Self::TextoDj => "texto-dj",
            Self::Aceleracion => "aceleracion",
        }
    }
}

/// Una entrada del catálogo.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Entrada {
    pub id: IdAgregado,
    /// La versión del archivo publicado: si cambia, lo instalado se actualiza.
    pub version: &'static str,
    /// `None` mientras no esté publicado (P13).
    pub url: Option<&'static str>,
    /// El tamaño del ZIP. Sin publicar, el aproximado de ADR-006, para decirlo en
    /// Ajustes.
    pub bytes: u64,
    pub sha256: Option<&'static str>,
}

impl Entrada {
    #[must_use]
    pub fn publicada(&self) -> bool {
        self.url.is_some() && self.sha256.is_some()
    }
}

const MB: u64 = 1024 * 1024;

/// El catálogo. Sin publicar todavía (P13): al subir la Release `agregados-1`, se
/// rellenan `url`, `bytes` y `sha256` de cada uno.
pub const CATALOGO: [Entrada; 4] = [
    Entrada {
        id: IdAgregado::Karaoke,
        version: "1",
        url: None,
        bytes: 166 * MB,
        sha256: None,
    },
    Entrada {
        id: IdAgregado::Analisis,
        version: "1",
        url: None,
        bytes: 4 * MB,
        sha256: None,
    },
    Entrada {
        id: IdAgregado::TextoDj,
        version: "1",
        url: None,
        bytes: 90 * MB,
        sha256: None,
    },
    Entrada {
        id: IdAgregado::Aceleracion,
        version: "1",
        url: None,
        bytes: 300 * MB,
        sha256: None,
    },
];

/// # Errors
///
/// [`NsError::InvalidInput`] si el id no está en el catálogo.
pub fn entrada(id: IdAgregado) -> NsResult<Entrada> {
    CATALOGO
        .iter()
        .find(|e| e.id == id)
        .copied()
        .ok_or(NsError::InvalidInput)
}

/// Lo que se apunta dentro de cada agregado instalado.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
struct Marca {
    version: String,
}

const MARCA: &str = "agregado.json";

/// La carpeta de un agregado instalado.
#[must_use]
pub fn carpeta(rutas: &Rutas, id: IdAgregado) -> PathBuf {
    rutas.agregados().join(id.carpeta())
}

/// La versión instalada, si lo está.
#[must_use]
pub fn instalado(rutas: &Rutas, id: IdAgregado) -> Option<String> {
    let texto = std::fs::read_to_string(carpeta(rutas, id).join(MARCA)).ok()?;
    serde_json::from_str::<Marca>(&texto)
        .ok()
        .map(|m| m.version)
}

fn descargas(rutas: &Rutas) -> PathBuf {
    rutas.agregados().join(".descargas")
}

fn parcial(rutas: &Rutas, e: &Entrada) -> PathBuf {
    descargas(rutas).join(format!("{}-{}.zip.parcial", e.id.carpeta(), e.version))
}

// --- La red, abstraída para las pruebas ----------------------------------------------

/// De dónde se descarga. En la aplicación, la puerta de red; en las pruebas, un
/// servidor de mentira que se puede cortar.
pub trait Origen {
    /// # Errors
    ///
    /// Los de [`Red::descargar`].
    fn descargar(
        &self,
        url: &str,
        desde: u64,
        destino: &mut dyn Destino,
        progreso: &mut dyn FnMut(u64),
    ) -> NsResult<()>;
}

impl Origen for Red {
    fn descargar(
        &self,
        url: &str,
        desde: u64,
        destino: &mut dyn Destino,
        progreso: &mut dyn FnMut(u64),
    ) -> NsResult<()> {
        Red::descargar(self, Servicio::Agregados, url, desde, destino, progreso)
    }
}

struct AlArchivo(File);

impl Destino for AlArchivo {
    fn empezar(&mut self, continuada: bool) -> std::io::Result<()> {
        if continuada {
            self.0.seek(SeekFrom::End(0)).map(|_| ())
        } else {
            self.0.set_len(0)?;
            self.0.seek(SeekFrom::Start(0)).map(|_| ())
        }
    }

    fn escribir(&mut self, bloque: &[u8]) -> std::io::Result<()> {
        self.0.write_all(bloque)
    }
}

fn sha256_de(ruta: &Path) -> NsResult<String> {
    let mut f = File::open(ruta).map_err(|_| NsError::StorageFailure)?;
    let mut h = Sha256::new();
    let mut buf = vec![0u8; 1 << 20];
    loop {
        let n = f.read(&mut buf).map_err(|_| NsError::StorageFailure)?;
        if n == 0 {
            break;
        }
        h.update(&buf[..n]);
    }
    Ok(h.finalize()
        .iter()
        .fold(String::with_capacity(64), |mut s, b| {
            use std::fmt::Write as _;
            let _ = write!(s, "{b:02x}");
            s
        }))
}

/// Descarga, verifica e instala un agregado. `progreso` recibe los bytes que hay
/// del ZIP y el total.
///
/// # Errors
///
/// - [`NsError::ComponentUnavailable`] si aún no está publicado.
/// - [`NsError::NetworkDisabled`] o [`NsError::ConsentRequired`] sin permiso.
/// - [`NsError::NetworkFailure`] si la descarga se corta: lo descargado se queda
///   para reanudar.
/// - [`NsError::IntegrityMismatch`] si el SHA-256 no coincide: lo descargado se
///   borra y no queda nada instalado.
/// - [`NsError::StorageFailure`] si no se puede escribir.
pub fn instalar(
    rutas: &Rutas,
    origen: &dyn Origen,
    e: &Entrada,
    progreso: &mut dyn FnMut(u64, u64),
) -> NsResult<()> {
    let (Some(url), Some(esperado)) = (e.url, e.sha256) else {
        return Err(NsError::ComponentUnavailable);
    };
    std::fs::create_dir_all(descargas(rutas)).map_err(|_| NsError::StorageFailure)?;
    let zip = parcial(rutas, e);
    let mut tiene = std::fs::metadata(&zip).map(|m| m.len()).unwrap_or(0);
    if tiene < e.bytes {
        let archivo = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&zip)
            .map_err(|_| NsError::StorageFailure)?;
        let mut destino = AlArchivo(archivo);
        let base = tiene;
        let resultado = origen.descargar(url, tiene, &mut destino, &mut |n| {
            progreso(base + n, e.bytes);
        });
        destino.0.sync_all().map_err(|_| NsError::StorageFailure)?;
        resultado?;
        tiene = std::fs::metadata(&zip).map(|m| m.len()).unwrap_or(0);
    }
    if tiene != e.bytes || sha256_de(&zip)? != esperado {
        // Un ZIP del tamaño justo con otro contenido no se reanuda: se empieza de
        // nuevo la próxima vez.
        let _ = std::fs::remove_file(&zip);
        tracing::warn!(?e.id, "el agregado descargado no coincide con el catálogo");
        return Err(NsError::IntegrityMismatch);
    }
    extraer_e_instalar(rutas, e, &zip)?;
    let _ = std::fs::remove_file(&zip);
    tracing::info!(?e.id, "agregado instalado");
    Ok(())
}

fn extraer_e_instalar(rutas: &Rutas, e: &Entrada, zip: &Path) -> NsResult<()> {
    let destino = carpeta(rutas, e.id);
    let temporal = rutas
        .agregados()
        .join(format!(".instalando-{}", e.id.carpeta()));
    let _ = std::fs::remove_dir_all(&temporal);
    std::fs::create_dir_all(&temporal).map_err(|_| NsError::StorageFailure)?;
    let resultado = (|| -> NsResult<()> {
        let f = File::open(zip).map_err(|_| NsError::StorageFailure)?;
        let mut z = zip::ZipArchive::new(f).map_err(|_| NsError::IntegrityMismatch)?;
        for i in 0..z.len() {
            let mut entrada = z.by_index(i).map_err(|_| NsError::IntegrityMismatch)?;
            if entrada.is_dir() {
                continue;
            }
            // Nunca al nombre tal cual: una entrada con `..` no sale de su carpeta.
            let relativa = entrada.enclosed_name().ok_or(NsError::IntegrityMismatch)?;
            let salida = temporal.join(relativa);
            if let Some(dir) = salida.parent() {
                std::fs::create_dir_all(dir).map_err(|_| NsError::StorageFailure)?;
            }
            let mut f = File::create(&salida).map_err(|_| NsError::StorageFailure)?;
            std::io::copy(&mut entrada, &mut f).map_err(|_| NsError::StorageFailure)?;
        }
        let marca = serde_json::to_string(&Marca {
            version: e.version.to_owned(),
        })
        .map_err(|_| NsError::Internal)?;
        std::fs::write(temporal.join(MARCA), marca).map_err(|_| NsError::StorageFailure)?;
        // La versión vieja se aparta antes de poner la nueva, y se borra después:
        // en ningún momento hay una carpeta a medio escribir con el nombre bueno.
        let viejo = rutas.agregados().join(format!(".viejo-{}", e.id.carpeta()));
        let _ = std::fs::remove_dir_all(&viejo);
        if destino.exists() {
            std::fs::rename(&destino, &viejo).map_err(|_| NsError::StorageFailure)?;
        }
        std::fs::rename(&temporal, &destino).map_err(|_| NsError::StorageFailure)?;
        let _ = std::fs::remove_dir_all(&viejo);
        Ok(())
    })();
    if resultado.is_err() {
        let _ = std::fs::remove_dir_all(&temporal);
    }
    resultado
}

/// Quita un agregado y libera su espacio en el acto. No falla si no estaba.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si no se puede apartar su carpeta.
pub fn quitar(rutas: &Rutas, id: IdAgregado) -> NsResult<()> {
    let dir = carpeta(rutas, id);
    if !dir.exists() {
        return Ok(());
    }
    // Primero se aparta (instantáneo y atómico): deja de estar instalado aunque
    // borrar cientos de MB tarde o se corte.
    let apartado = rutas
        .agregados()
        .join(format!(".quitando-{}", id.carpeta()));
    let _ = std::fs::remove_dir_all(&apartado);
    std::fs::rename(&dir, &apartado).map_err(|_| NsError::StorageFailure)?;
    let _ = std::fs::remove_dir_all(&apartado);
    for e in CATALOGO.iter().filter(|e| e.id == id) {
        let _ = std::fs::remove_file(parcial(rutas, e));
    }
    Ok(())
}

// --- El gestor: estado y progreso para Ajustes (F5.1.3) -----------------------------

/// Lo que muestra la tarjeta de un agregado.
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct EstadoAgregado {
    pub id: IdAgregado,
    /// Lo que ocupa la descarga.
    #[ts(type = "number")]
    pub bytes: u64,
    /// Si hay archivo publicado que instalar (P13).
    pub publicado: bool,
    pub instalado: bool,
    /// Hay una versión más nueva en el catálogo que la instalada.
    pub actualizable: bool,
    /// De 0 a 1 mientras se descarga.
    pub progreso: Option<f64>,
    /// El código del último fallo (`NETWORK_FAILURE`, `INTEGRITY_MISMATCH`…).
    pub error: Option<String>,
}

#[derive(Default)]
struct EnCurso {
    progreso: std::collections::HashMap<IdAgregado, f64>,
    errores: std::collections::HashMap<IdAgregado, String>,
}

/// Lleva las instalaciones en curso. Clonable: el hilo de cada descarga y los
/// comandos comparten el estado.
#[derive(Clone, Default)]
pub struct Gestor {
    en_curso: std::sync::Arc<std::sync::Mutex<EnCurso>>,
}

impl Gestor {
    fn con<T>(&self, f: impl FnOnce(&mut EnCurso) -> T) -> T {
        let mut g = self
            .en_curso
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        f(&mut g)
    }

    /// El estado de todos, en el orden del catálogo.
    #[must_use]
    pub fn estado(&self, rutas: &Rutas) -> Vec<EstadoAgregado> {
        self.con(|c| {
            CATALOGO
                .iter()
                .map(|e| {
                    let version = instalado(rutas, e.id);
                    EstadoAgregado {
                        id: e.id,
                        bytes: e.bytes,
                        publicado: e.publicada(),
                        instalado: version.is_some(),
                        actualizable: e.publicada()
                            && version.as_deref().is_some_and(|v| v != e.version),
                        progreso: c.progreso.get(&e.id).copied(),
                        error: c.errores.get(&e.id).cloned(),
                    }
                })
                .collect()
        })
    }

    /// Lanza la instalación en su hilo. `avisar` se llama con cada cambio que la
    /// interfaz deba ver (progreso cada 1 %, fin o fallo). No hace nada si ya se
    /// está instalando.
    ///
    /// # Errors
    ///
    /// [`NsError::InvalidInput`] si el id no está en el catálogo;
    /// [`NsError::ComponentUnavailable`] si no está publicado.
    pub fn instalar(
        &self,
        rutas: Rutas,
        red: std::sync::Arc<Red>,
        id: IdAgregado,
        avisar: impl Fn() + Send + 'static,
    ) -> NsResult<()> {
        let e = entrada(id)?;
        if !e.publicada() {
            return Err(NsError::ComponentUnavailable);
        }
        let empezar = self.con(|c| {
            if c.progreso.contains_key(&id) {
                return false;
            }
            c.errores.remove(&id);
            c.progreso.insert(id, 0.0);
            true
        });
        if !empezar {
            return Ok(());
        }
        avisar();
        let gestor = self.clone();
        let lanzado = std::thread::Builder::new()
            .name(format!("agregado-{}", id.carpeta()))
            .spawn(move || {
                let mut ultimo = 0.0;
                let r = instalar(&rutas, red.as_ref(), &e, &mut |n, total| {
                    let p = (n as f64 / total.max(1) as f64).min(1.0);
                    if p - ultimo >= 0.01 {
                        ultimo = p;
                        gestor.con(|c| {
                            c.progreso.insert(id, p);
                        });
                        avisar();
                    }
                });
                gestor.con(|c| {
                    c.progreso.remove(&id);
                    if let Err(error) = r {
                        c.errores.insert(id, error.code().to_owned());
                    }
                });
                avisar();
            });
        if lanzado.is_err() {
            self.con(|c| {
                c.progreso.remove(&id);
            });
            return Err(NsError::Internal);
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use std::cell::Cell;

    use super::*;

    /// Un servidor de mentira: sirve `datos`, respeta el `Range` o no, y se puede
    /// cortar tras unos bytes la primera vez.
    struct Falso {
        datos: Vec<u8>,
        respeta_range: bool,
        cortar_tras: Cell<Option<usize>>,
    }

    impl Origen for Falso {
        fn descargar(
            &self,
            _url: &str,
            desde: u64,
            destino: &mut dyn Destino,
            progreso: &mut dyn FnMut(u64),
        ) -> NsResult<()> {
            let continuada = self.respeta_range && desde > 0;
            destino.empezar(continuada).unwrap();
            let inicio = if continuada { desde as usize } else { 0 };
            let resto = &self.datos[inicio..];
            let corte = self.cortar_tras.take();
            let mut enviados = 0;
            for trozo in resto.chunks(1000) {
                if corte.is_some_and(|c| enviados >= c) {
                    return Err(NsError::NetworkFailure);
                }
                destino.escribir(trozo).unwrap();
                enviados += trozo.len();
                progreso(enviados as u64);
            }
            Ok(())
        }
    }

    fn zip_con(archivos: &[(&str, &[u8])]) -> Vec<u8> {
        let mut w = zip::ZipWriter::new(std::io::Cursor::new(Vec::new()));
        for (nombre, datos) in archivos {
            // Sin comprimir: el tamaño del ZIP es el de los datos y se puede cortar
            // por la mitad.
            w.start_file(
                *nombre,
                zip::write::SimpleFileOptions::default()
                    .compression_method(zip::CompressionMethod::Stored),
            )
            .unwrap();
            w.write_all(datos).unwrap();
        }
        w.finish().unwrap().into_inner()
    }

    fn hex(datos: &[u8]) -> &'static str {
        let h = Sha256::digest(datos)
            .iter()
            .fold(String::new(), |mut s, b| {
                use std::fmt::Write as _;
                let _ = write!(s, "{b:02x}");
                s
            });
        Box::leak(h.into_boxed_str())
    }

    fn rutas(nombre: &str) -> (PathBuf, Rutas) {
        let d = std::env::temp_dir().join(format!("ns-agregados-{nombre}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        let r = Rutas::bajo(&d).unwrap();
        (d, r)
    }

    fn entrada_de(datos: &[u8]) -> Entrada {
        Entrada {
            id: IdAgregado::Karaoke,
            version: "1",
            url: Some("https://github.com/x"),
            bytes: datos.len() as u64,
            sha256: Some(hex(datos)),
        }
    }

    #[test]
    fn una_descarga_cortada_se_reanuda_y_da_el_archivo_correcto() {
        let (d, r) = rutas("reanudar");
        let modelo = vec![7u8; 20_000];
        let datos = zip_con(&[("htdemucs.onnx", &modelo)]);
        let e = entrada_de(&datos);
        let origen = Falso {
            datos: datos.clone(),
            respeta_range: true,
            cortar_tras: Cell::new(Some(datos.len() / 2)),
        };
        assert_eq!(
            instalar(&r, &origen, &e, &mut |_, _| {}),
            Err(NsError::NetworkFailure)
        );
        assert!(
            instalado(&r, IdAgregado::Karaoke).is_none(),
            "nada a medias"
        );
        let a_medias = std::fs::metadata(parcial(&r, &e)).unwrap().len();
        assert!(a_medias > 0 && a_medias < datos.len() as u64);

        let mut visto = 0;
        instalar(&r, &origen, &e, &mut |n, _| visto = n).unwrap();
        assert_eq!(
            visto,
            datos.len() as u64,
            "el progreso cuenta lo que ya había"
        );
        assert_eq!(instalado(&r, IdAgregado::Karaoke).as_deref(), Some("1"));
        assert_eq!(
            std::fs::read(carpeta(&r, IdAgregado::Karaoke).join("htdemucs.onnx")).unwrap(),
            modelo
        );
        assert!(!parcial(&r, &e).exists());
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn si_el_servidor_ignora_el_range_se_empieza_de_cero_sin_corromper() {
        let (d, r) = rutas("sin-range");
        let datos = zip_con(&[("m.onnx", &[1u8; 5_000])]);
        let e = entrada_de(&datos);
        std::fs::create_dir_all(descargas(&r)).unwrap();
        std::fs::write(parcial(&r, &e), &datos[..1000]).unwrap();
        let origen = Falso {
            datos,
            respeta_range: false,
            cortar_tras: Cell::new(None),
        };
        instalar(&r, &origen, &e, &mut |_, _| {}).unwrap();
        assert!(instalado(&r, IdAgregado::Karaoke).is_some());
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn un_hash_alterado_se_rechaza_y_no_deja_nada_instalado() {
        let (d, r) = rutas("hash");
        let datos = zip_con(&[("m.onnx", &[1u8; 5_000])]);
        let mut e = entrada_de(&datos);
        e.sha256 = Some(hex(b"otra cosa"));
        let origen = Falso {
            datos,
            respeta_range: true,
            cortar_tras: Cell::new(None),
        };
        assert_eq!(
            instalar(&r, &origen, &e, &mut |_, _| {}),
            Err(NsError::IntegrityMismatch)
        );
        assert!(instalado(&r, IdAgregado::Karaoke).is_none());
        assert!(!carpeta(&r, IdAgregado::Karaoke).exists());
        assert!(!parcial(&r, &e).exists(), "lo malo no se reanuda");
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn un_zip_con_ruta_trampa_no_escribe_fuera_ni_queda_instalado() {
        let (d, r) = rutas("trampa");
        let datos = zip_con(&[("../../fuera.txt", b"x")]);
        let e = entrada_de(&datos);
        let origen = Falso {
            datos,
            respeta_range: true,
            cortar_tras: Cell::new(None),
        };
        assert_eq!(
            instalar(&r, &origen, &e, &mut |_, _| {}),
            Err(NsError::IntegrityMismatch)
        );
        assert!(!d.join("fuera.txt").exists() && !r.datos.join("fuera.txt").exists());
        assert!(instalado(&r, IdAgregado::Karaoke).is_none());
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn quitar_libera_el_espacio_y_reinstalar_vuelve_a_funcionar() {
        let (d, r) = rutas("quitar");
        let datos = zip_con(&[("m.onnx", &[3u8; 2_000])]);
        let e = entrada_de(&datos);
        let origen = Falso {
            datos,
            respeta_range: true,
            cortar_tras: Cell::new(None),
        };
        instalar(&r, &origen, &e, &mut |_, _| {}).unwrap();
        quitar(&r, IdAgregado::Karaoke).unwrap();
        assert!(instalado(&r, IdAgregado::Karaoke).is_none());
        assert!(!carpeta(&r, IdAgregado::Karaoke).exists());
        quitar(&r, IdAgregado::Karaoke).unwrap();
        instalar(&r, &origen, &e, &mut |_, _| {}).unwrap();
        assert!(instalado(&r, IdAgregado::Karaoke).is_some());
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn lo_que_no_esta_publicado_no_se_puede_instalar() {
        let (d, r) = rutas("sin-publicar");
        let origen = Falso {
            datos: Vec::new(),
            respeta_range: true,
            cortar_tras: Cell::new(None),
        };
        for e in &CATALOGO {
            if !e.publicada() {
                assert_eq!(
                    instalar(&r, &origen, e, &mut |_, _| {}),
                    Err(NsError::ComponentUnavailable)
                );
            }
        }
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn el_catalogo_tiene_cada_agregado_una_vez_y_solo_urls_de_las_releases() {
        for id in IdAgregado::TODOS {
            assert_eq!(CATALOGO.iter().filter(|e| e.id == id).count(), 1, "{id:?}");
        }
        for e in &CATALOGO {
            if let Some(u) = e.url {
                assert!(
                    u.starts_with("https://github.com/Nate-1296/NB-SOUND/releases/download/"),
                    "{u}"
                );
                assert_eq!(e.sha256.map(str::len), Some(64));
            }
        }
    }

    #[test]
    fn el_gestor_lista_el_catalogo_y_no_lanza_lo_que_no_esta_publicado() {
        let (d, r) = rutas("gestor");
        let g = Gestor::default();
        let estado = g.estado(&r);
        assert_eq!(estado.len(), CATALOGO.len());
        assert!(estado.iter().all(|e| !e.instalado && e.progreso.is_none()));
        let red = std::sync::Arc::new(Red::new(crate::net::PoliticaDeRed::default()));
        if let Some(e) = CATALOGO.iter().find(|e| !e.publicada()) {
            assert_eq!(
                g.instalar(r.clone(), red, e.id, || {}),
                Err(NsError::ComponentUnavailable)
            );
        }
        let _ = std::fs::remove_dir_all(&d);
    }
}
