//! La auditoría de la biblioteca, rediseñada (inventario de la V1, `core/audit.py`).
//!
//! La V1 tenía un "doctor" que el usuario lanzaba y que listaba avisos técnicos
//! (portadas huérfanas, referencias rotas, manifiestos que faltan). La V2 lo hace
//! sola, una vez por arranque y en segundo plano, y solo arregla lo que es suyo:
//!
//! - **Portadas huérfanas**: archivos de la carpeta de portadas que ninguna fila
//!   usa. Son datos internos de la aplicación y se borran.
//! - **Portadas rotas**: filas cuyo archivo falta. Se quita la referencia, para que
//!   el álbum vuelva a buscar portada la próxima vez que se complete.
//!
//! Lo que es del usuario (una pista cuyo archivo no está, quizá en un disco sin
//! montar) no se toca: solo se cuenta en el registro. No hay nada que el usuario
//! tenga que decidir aquí, así que no llega a Por revisar.

use std::collections::HashSet;
use std::path::Path;

use crate::db::{self, BaseDeDatos};
use crate::error::{NsError, NsResult};
use crate::paths::Rutas;

/// Una portada sin fila se borra solo si tiene al menos esta antigüedad.
const ANTIGUEDAD_HUERFANA: std::time::Duration = std::time::Duration::from_secs(3600);

/// Lo que hizo una pasada.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct Informe {
    pub portadas_huerfanas: usize,
    pub portadas_rotas: usize,
    pub pistas_sin_archivo: usize,
}

fn archivos(dir: &Path) -> Vec<std::path::PathBuf> {
    let mut salida = Vec::new();
    let mut pila = vec![dir.to_path_buf()];
    while let Some(d) = pila.pop() {
        let Ok(entradas) = std::fs::read_dir(&d) else {
            continue;
        };
        for e in entradas.filter_map(Result::ok) {
            let p = e.path();
            if p.is_dir() {
                pila.push(p);
            } else {
                salida.push(p);
            }
        }
    }
    salida
}

/// Una pasada de la auditoría.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base falla.
pub fn auditar(db: &BaseDeDatos, rutas: &Rutas, musica: Option<&Path>) -> NsResult<Informe> {
    let mut informe = Informe::default();
    let dir = rutas.portadas();
    let filas: Vec<(i64, String)> = {
        let conn = db.conexion()?;
        let mut s = conn
            .prepare("SELECT id, ruta FROM portadas")
            .map_err(|_| NsError::StorageFailure)?;
        let v = s
            .query_map([], |f| Ok((f.get(0)?, f.get(1)?)))
            .map_err(|_| NsError::StorageFailure)?
            .collect::<rusqlite::Result<Vec<_>>>()
            .map_err(|_| NsError::StorageFailure)?;
        v
    };
    let usadas: HashSet<std::path::PathBuf> = filas.iter().map(|(_, r)| dir.join(r)).collect();
    for f in archivos(&dir) {
        // Lo reciente puede ser de una importación en curso (la de la V1 copia las
        // portadas antes de dar de alta sus filas): solo cuenta lo de hace una hora.
        let reciente = std::fs::metadata(&f)
            .and_then(|m| m.modified())
            .ok()
            .and_then(|t| t.elapsed().ok())
            .is_none_or(|e| e < ANTIGUEDAD_HUERFANA);
        if !reciente && !usadas.contains(&f) && std::fs::remove_file(&f).is_ok() {
            informe.portadas_huerfanas += 1;
        }
    }
    let rotas: Vec<i64> = filas
        .iter()
        .filter(|(_, r)| !dir.join(r).is_file())
        .map(|(id, _)| *id)
        .collect();
    if !rotas.is_empty() {
        let mut conn = db.conexion()?;
        let tx = db::transaccion_de_escritura(&mut conn)?;
        for id in &rotas {
            for sql in [
                "UPDATE albumes SET portada_id = NULL WHERE portada_id = ?1",
                "UPDATE pistas SET portada_id = NULL WHERE portada_id = ?1",
                "UPDATE artistas SET imagen_id = NULL WHERE imagen_id = ?1",
                "DELETE FROM portadas WHERE id = ?1",
            ] {
                tx.execute(sql, [id]).map_err(|_| NsError::StorageFailure)?;
            }
        }
        tx.commit().map_err(|_| NsError::StorageFailure)?;
        informe.portadas_rotas = rotas.len();
    }
    // Si la carpeta de música no está (un disco sin montar), no se cuenta nada:
    // todas faltarían y no sería verdad.
    if let Some(m) = musica.filter(|m| m.is_dir()) {
        let conn = db.conexion()?;
        let mut s = conn
            .prepare("SELECT ruta FROM pistas WHERE estado = 'biblioteca'")
            .map_err(|_| NsError::StorageFailure)?;
        let rutas_pistas = s
            .query_map([], |f| f.get::<_, String>(0))
            .map_err(|_| NsError::StorageFailure)?
            .collect::<rusqlite::Result<Vec<_>>>()
            .map_err(|_| NsError::StorageFailure)?;
        informe.pistas_sin_archivo = rutas_pistas
            .iter()
            .filter(|r| {
                let p = Path::new(r);
                !(if p.is_absolute() {
                    p.to_path_buf()
                } else {
                    m.join(p)
                })
                .is_file()
            })
            .count();
    }
    Ok(informe)
}

/// Una pasada al arrancar, en su hilo y sin prisa.
pub fn arrancar(db: BaseDeDatos, rutas: Rutas) {
    let lanzado = std::thread::Builder::new()
        .name("auditoria".into())
        .spawn(move || {
            // Que arranquen antes la ventana y el reproductor.
            std::thread::sleep(std::time::Duration::from_secs(30));
            let musica = db
                .conexion()
                .ok()
                .and_then(|c| crate::reproductor::carpeta_musica(&c).ok().flatten());
            match auditar(&db, &rutas, musica.as_deref()) {
                Ok(i) => tracing::info!(
                    // no es del usuario: son tres cuentas.
                    portadas_huerfanas = i.portadas_huerfanas,
                    portadas_rotas = i.portadas_rotas,
                    pistas_sin_archivo = i.pistas_sin_archivo,
                    "auditoría de la biblioteca"
                ),
                Err(e) => tracing::error!(codigo = e.code(), "no se pudo auditar la biblioteca"),
            }
        });
    if lanzado.is_err() {
        tracing::error!("no se pudo lanzar la auditoría");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn se_arregla_lo_interno_y_solo_se_cuenta_lo_del_usuario() {
        let d = std::env::temp_dir().join(format!("ns-auditoria-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        let rutas = Rutas::bajo(&d).unwrap();
        let musica = d.join("musica");
        std::fs::create_dir_all(rutas.portadas().join("ab")).unwrap();
        std::fs::create_dir_all(&musica).unwrap();
        std::fs::write(rutas.portadas().join("ab/usada.jpg"), b"x").unwrap();
        let huerfana = rutas.portadas().join("ab/huerfana.jpg");
        std::fs::write(&huerfana, b"x").unwrap();
        let reciente = rutas.portadas().join("ab/reciente.jpg");
        std::fs::write(&reciente, b"x").unwrap();
        let hace_dos_horas = std::time::SystemTime::now() - std::time::Duration::from_secs(7200);
        std::fs::File::options()
            .write(true)
            .open(&huerfana)
            .unwrap()
            .set_modified(hace_dos_horas)
            .unwrap();
        std::fs::write(musica.join("esta.mp3"), b"x").unwrap();
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(&format!(
                "INSERT INTO portadas (id, sha256, ruta, ancho, alto, bytes, mime, origen) VALUES
                     (1, '{a}', 'ab/usada.jpg', 1, 1, 1, 'image/jpeg', 'x'),
                     (2, '{b}', 'ab/falta.jpg', 1, 1, 1, 'image/jpeg', 'x');
                 INSERT INTO artistas (id, nombre, clave, imagen_id) VALUES (1, 'a', 'a', 2);
                 INSERT INTO pistas (titulo, ruta) VALUES ('uno', 'esta.mp3'), ('dos', 'no-esta.mp3');",
                a = "a".repeat(64),
                b = "b".repeat(64)
            ))
            .unwrap();
        let i = auditar(&db, &rutas, Some(&musica)).unwrap();
        assert_eq!(
            i,
            Informe {
                portadas_huerfanas: 1,
                portadas_rotas: 1,
                pistas_sin_archivo: 1
            }
        );
        assert!(rutas.portadas().join("ab/usada.jpg").is_file());
        assert!(!huerfana.exists());
        assert!(
            reciente.exists(),
            "lo reciente puede ser de una importación en curso"
        );
        let imagen: Option<i64> = db
            .conexion()
            .unwrap()
            .query_row("SELECT imagen_id FROM artistas", [], |f| f.get(0))
            .unwrap();
        assert_eq!(imagen, None);
        let sin_disco = auditar(&db, &rutas, Some(&d.join("disco-sin-montar"))).unwrap();
        assert_eq!(sin_disco.pistas_sin_archivo, 0);
    }
}
