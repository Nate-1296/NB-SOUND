//! La sonoridad de la biblioteca, medida en segundo plano (F2.1.4), y en el mismo
//! hilo los rasgos básicos de lo importado (F4.1.12).
//!
//! La V1 nunca midió la sonoridad, así que al llegar de ella ninguna pista la
//! tiene, y la normalización no haría nada. Medirla entera en la importación
//! retrasaría la biblioteca varios minutos; medirla al empezar cada pista retrasaría
//! el sonido. Se mide aquí, una pista cada vez y con una pausa entre una y otra,
//! para que el equipo no lo note: la pista que aún no tiene medida suena sin
//! normalizar, como en la V1.

use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::time::Duration;

use rusqlite::params;

use crate::audio::sonoridad;
use crate::db::{self, BaseDeDatos};
use crate::error::{NsError, NsResult};
use crate::reproductor::persistencia;

/// Lo que se descansa entre dos pistas. Medir una canción ocupa un núcleo menos de
/// un segundo; con esta pausa, la biblioteca de 2.400 pistas tarda media hora y el
/// equipo no se calienta.
const PAUSA_ENTRE_PISTAS: Duration = Duration::from_millis(300);
/// Cuando no queda nada, se vuelve a mirar de vez en cuando: la biblioteca crece.
const PAUSA_SIN_TRABAJO: Duration = Duration::from_secs(120);
const LOTE: i64 = 32;

struct Pendiente {
    id: i64,
    ruta: PathBuf,
    sha256: Option<String>,
}

/// Las pistas sin medida, o cuya medida es de otro archivo. Cota: `LOTE`.
fn pendientes(db: &BaseDeDatos, saltar: &HashSet<i64>) -> NsResult<Vec<Pendiente>> {
    let conn = db.conexion()?;
    let musica = persistencia::carpeta_musica(&conn)?;
    let mut s = conn
        .prepare(
            "SELECT p.id, p.ruta, p.sha256 FROM pistas p
             LEFT JOIN sonoridad so ON so.pista_id = p.id
             WHERE p.estado = 'biblioteca'
               AND (so.pista_id IS NULL OR so.sha256 IS NOT p.sha256)
             ORDER BY p.id LIMIT ?1",
        )
        .map_err(|_| NsError::StorageFailure)?;
    let filas = s
        .query_map(params![LOTE + saltar.len() as i64], |f| {
            Ok((
                f.get::<_, i64>(0)?,
                f.get::<_, String>(1)?,
                f.get::<_, Option<String>>(2)?,
            ))
        })
        .map_err(|_| NsError::StorageFailure)?
        .collect::<rusqlite::Result<Vec<_>>>()
        .map_err(|_| NsError::StorageFailure)?;
    Ok(filas
        .into_iter()
        .filter(|(id, _, _)| !saltar.contains(id))
        .map(|(id, ruta, sha256)| {
            let ruta = PathBuf::from(ruta);
            let ruta = match &musica {
                Some(m) if ruta.is_relative() => m.join(ruta),
                _ => ruta,
            };
            Pendiente { id, ruta, sha256 }
        })
        .collect())
}

fn guardar(db: &BaseDeDatos, p: &Pendiente, medida: Option<&sonoridad::Sonoridad>) -> NsResult<()> {
    let finito = |v: f64| v.is_finite().then_some(v);
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    tx.execute(
        "INSERT INTO sonoridad (pista_id, sha256, lufs, pico_verdadero, rango)
         VALUES (?1, ?2, ?3, ?4, ?5)
         ON CONFLICT (pista_id) DO UPDATE SET sha256 = excluded.sha256, lufs = excluded.lufs,
             pico_verdadero = excluded.pico_verdadero, rango = excluded.rango,
             medida_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')",
        params![
            p.id,
            p.sha256,
            medida.and_then(|m| finito(m.lufs)),
            medida.and_then(|m| finito(m.pico_verdadero)),
            medida.and_then(|m| finito(m.rango).map(|r| r.max(0.0))),
        ],
    )
    .map_err(|_| NsError::StorageFailure)?;
    tx.commit().map_err(|_| NsError::StorageFailure)
}

/// Mide lo pendiente hasta que no quede nada. Devuelve cuántas pistas apuntó.
///
/// Un archivo que no se puede medir (silencio, dañado, formato raro) se apunta sin
/// valores para no reintentarlo en cada arranque. Uno que no está (un disco sin
/// montar) solo se salta en esta pasada: cuando vuelva, se medirá.
pub fn medir_pendientes(db: &BaseDeDatos, pausa: Duration) -> NsResult<usize> {
    let mut saltar = HashSet::new();
    let mut apuntadas = 0;
    loop {
        let lote = pendientes(db, &saltar)?;
        if lote.is_empty() {
            return Ok(apuntadas);
        }
        for p in lote {
            match medir(&p.ruta) {
                Ok(m) => guardar(db, &p, Some(&m))?,
                Err(NsError::AudioCorrupted | NsError::FormatUnsupported) => {
                    guardar(db, &p, None)?;
                }
                Err(_) => {
                    saltar.insert(p.id);
                    continue;
                }
            }
            apuntadas += 1;
            std::thread::sleep(pausa);
        }
    }
}

fn medir(ruta: &Path) -> NsResult<sonoridad::Sonoridad> {
    if !ruta.is_file() {
        return Err(NsError::FileNotFound);
    }
    sonoridad::medir(ruta)
}

/// Lanza el hilo que mide la biblioteca mientras la aplicación esté abierta.
pub fn arrancar(db: BaseDeDatos) {
    let lanzado = std::thread::Builder::new()
        .name("sonoridad".into())
        .spawn(move || loop {
            match medir_pendientes(&db, PAUSA_ENTRE_PISTAS) {
                Ok(n) if n > 0 => tracing::info!(pistas = n, "sonoridad medida"),
                Ok(_) => {}
                Err(error) => {
                    tracing::error!(codigo = error.code(), "no se pudo medir la sonoridad")
                }
            }
            // Los rasgos básicos de lo importado (F4.1.12), en el mismo hilo: dos
            // análisis a la vez se notarían en el equipo.
            match crate::rasgos::analizar_pendientes(&db, PAUSA_ENTRE_PISTAS) {
                Ok(n) if n > 0 => tracing::info!(pistas = n, "rasgos analizados"),
                Ok(_) => {}
                Err(error) => {
                    tracing::error!(codigo = error.code(), "no se pudieron analizar los rasgos")
                }
            }
            std::thread::sleep(PAUSA_SIN_TRABAJO);
        });
    if lanzado.is_err() {
        tracing::error!("no se pudo lanzar la medición de sonoridad");
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::audio::pruebas::wav;

    fn base_con(pistas: &[(i64, &str, Option<&str>)]) -> BaseDeDatos {
        let db = BaseDeDatos::en_memoria().unwrap();
        let conn = db.conexion().unwrap();
        for (id, ruta, sha) in pistas {
            conn.execute(
                "INSERT INTO pistas (id, titulo, ruta, sha256) VALUES (?1, 't', ?2, ?3)",
                params![id, ruta, sha],
            )
            .unwrap();
        }
        db
    }

    fn medida(db: &BaseDeDatos, id: i64) -> Option<Option<f64>> {
        db.conexion()
            .unwrap()
            .query_row(
                "SELECT lufs FROM sonoridad WHERE pista_id = ?1",
                [id],
                |f| f.get(0),
            )
            .ok()
    }

    fn dir(nombre: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("ns-medicion-{nombre}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        d
    }

    #[test]
    fn cada_pista_queda_medida_una_sola_vez() {
        let d = dir("una-vez");
        let ruta = d.join("tono.wav");
        let _ = wav(&ruta, 44_100, 44_100 * 3, |i, _| {
            (2.0 * std::f32::consts::PI * 440.0 * i as f32 / 44_100.0).sin() * 0.3
        });
        let db = base_con(&[(1, ruta.to_str().unwrap(), None)]);
        assert_eq!(medir_pendientes(&db, Duration::ZERO).unwrap(), 1);
        let lufs = medida(&db, 1).flatten().expect("medida");
        assert!((-25.0..-5.0).contains(&lufs), "{lufs}");
        assert_eq!(medir_pendientes(&db, Duration::ZERO).unwrap(), 0);
    }

    #[test]
    fn un_archivo_que_no_se_puede_medir_se_apunta_sin_valores() {
        let d = dir("silencio");
        let ruta = d.join("silencio.wav");
        let _ = wav(&ruta, 44_100, 44_100, |_, _| 0.0);
        let db = base_con(&[(1, ruta.to_str().unwrap(), None)]);
        assert_eq!(medir_pendientes(&db, Duration::ZERO).unwrap(), 1);
        assert_eq!(medida(&db, 1), Some(None));
    }

    #[test]
    fn un_archivo_ausente_no_se_apunta_y_se_reintenta_despues() {
        let d = dir("ausente");
        let ruta = d.join("aun-no.wav");
        let db = base_con(&[(1, ruta.to_str().unwrap(), None)]);
        assert_eq!(medir_pendientes(&db, Duration::ZERO).unwrap(), 0);
        assert_eq!(medida(&db, 1), None);
        let _ = wav(&ruta, 44_100, 44_100 * 3, |i, _| {
            ((i % 100) as f32 / 100.0 - 0.5) * 0.4
        });
        assert_eq!(medir_pendientes(&db, Duration::ZERO).unwrap(), 1);
    }

    #[test]
    fn si_el_archivo_cambia_la_medida_caduca() {
        let d = dir("caduca");
        let ruta = d.join("tono.wav");
        let _ = wav(&ruta, 44_100, 44_100 * 3, |i, _| {
            ((i % 50) as f32 / 50.0 - 0.5) * 0.4
        });
        let sha_a = "a".repeat(64);
        let db = base_con(&[(1, ruta.to_str().unwrap(), Some(&sha_a))]);
        assert_eq!(medir_pendientes(&db, Duration::ZERO).unwrap(), 1);
        db.conexion()
            .unwrap()
            .execute(
                "UPDATE pistas SET sha256 = ?1 WHERE id = 1",
                [&"b".repeat(64)],
            )
            .unwrap();
        assert_eq!(medir_pendientes(&db, Duration::ZERO).unwrap(), 1);
    }

    #[test]
    fn la_medida_llega_a_la_ganancia_del_reproductor() {
        let d = dir("ganancia");
        let ruta = d.join("bajo.wav");
        let _ = wav(&ruta, 44_100, 44_100 * 3, |i, _| {
            (2.0 * std::f32::consts::PI * 440.0 * i as f32 / 44_100.0).sin() * 0.02
        });
        let db = base_con(&[(1, ruta.to_str().unwrap(), None)]);
        let conn = db.conexion().unwrap();
        let antes = persistencia::resolver(&conn, 1, None, &d, true)
            .unwrap()
            .unwrap();
        assert_eq!(antes.ganancia_db, 0.0, "sin medida no se toca");
        drop(conn);
        medir_pendientes(&db, Duration::ZERO).unwrap();
        let conn = db.conexion().unwrap();
        let despues = persistencia::resolver(&conn, 1, None, &d, true)
            .unwrap()
            .unwrap();
        assert!(despues.ganancia_db > 3.0, "{}", despues.ganancia_db);
    }
}
