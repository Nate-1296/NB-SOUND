//! El hilo del DJ: dueño del [`Dj`] y de la sesión activa.
//!
//! Los comandos del puente le mandan trabajo y esperan la respuesta fuera del hilo
//! de la ventana. Entre petición y petición, si la sesión activa no está completa,
//! construye su siguiente bloque, lo guarda y avisa: al reproductor, para que la
//! sesión que suena vea sus pistas nuevas, y a la vista. Es lo que la V1 hacía con
//! un worker de Qt tras entregar el primer bloque.

use std::sync::mpsc::{self, RecvTimeoutError, Sender};
use std::sync::Arc;
use std::time::Duration;

use super::servicio::Dj;
use crate::error::{NsError, NsResult};

type Trabajo = Box<dyn FnOnce(&mut Dj) + Send>;

/// Lo que el director avisa al terminar un bloque: el id de la sesión.
pub type Aviso = Arc<dyn Fn(i64) + Send + Sync>;

#[derive(Clone)]
pub struct Director {
    trabajos: Sender<Trabajo>,
}

impl Director {
    /// Arranca el hilo con su [`Dj`].
    ///
    /// # Errors
    ///
    /// [`NsError::Internal`] si el hilo no arranca.
    pub fn arrancar(mut dj: Dj, avisar: Aviso) -> NsResult<Self> {
        let (tx, rx) = mpsc::channel::<Trabajo>();
        std::thread::Builder::new()
            .name("dj".into())
            .spawn(move || loop {
                // Con una sesión a medias no se espera: se construye en cuanto no
                // hay peticiones.
                let pendiente = dj.activa().is_some_and(|a| !a.completada);
                let espera = if pendiente {
                    Duration::ZERO
                } else {
                    Duration::from_secs(3600)
                };
                match rx.recv_timeout(espera) {
                    Ok(trabajo) => trabajo(&mut dj),
                    Err(RecvTimeoutError::Timeout) => {
                        let id = dj.activa().map(|a| a.id);
                        match dj.continuar() {
                            Ok(Some(_)) | Ok(None) => {
                                if let Some(id) = id {
                                    avisar(id);
                                }
                            }
                            Err(error) => {
                                tracing::error!(
                                    codigo = error.code(),
                                    "no se pudo seguir la sesión"
                                );
                                // Sin base no hay forma de seguir: se deja la sesión
                                // como esté y se espera a la próxima petición.
                                if let Ok(trabajo) = rx.recv() {
                                    trabajo(&mut dj);
                                }
                            }
                        }
                    }
                    Err(RecvTimeoutError::Disconnected) => return,
                }
            })
            .map_err(|_| NsError::Internal)?;
        Ok(Self { trabajos: tx })
    }

    /// Hace `f` en el hilo del DJ y espera su resultado. Bloquea: se llama desde
    /// un hilo de trabajo, nunca desde el de la ventana.
    ///
    /// # Errors
    ///
    /// Los de `f`; [`NsError::Internal`] si el hilo murió.
    pub fn con<T: Send + 'static>(
        &self,
        f: impl FnOnce(&mut Dj) -> NsResult<T> + Send + 'static,
    ) -> NsResult<T> {
        let (tx, rx) = mpsc::channel();
        self.trabajos
            .send(Box::new(move |dj| {
                let _ = tx.send(f(dj));
            }))
            .map_err(|_| NsError::Internal)?;
        rx.recv().map_err(|_| NsError::Internal)?
    }
}

#[cfg(test)]
mod pruebas {
    use std::sync::Mutex;
    use std::time::Instant;

    use super::*;
    use crate::db::BaseDeDatos;
    use crate::dj::embeddings::Determinista;
    use crate::dj::planificador::Candidata;
    use crate::dj::servicio::Inicio;

    fn pool() -> Vec<Candidata> {
        (1..=60)
            .map(|id| Candidata {
                id,
                artista_id: Some(id),
                duracion_seg: 200.0,
                energia: Some((id % 10) as f64 / 10.0),
                ..Candidata::default()
            })
            .collect()
    }

    #[test]
    fn tras_el_primer_bloque_la_sesion_se_completa_sola_y_avisa() {
        let db = BaseDeDatos::en_memoria().unwrap();
        let conn = db.conexion().unwrap();
        for id in 1..=60 {
            conn.execute(
                "INSERT INTO pistas (id, titulo, ruta, duracion_seg) VALUES (?1, 'x', ?2, 200)",
                rusqlite::params![id, format!("{id}.mp3")],
            )
            .unwrap();
        }
        drop(conn);
        let avisos = Arc::new(Mutex::new(Vec::new()));
        let a = Arc::clone(&avisos);
        let director = Director::arrancar(
            Dj::new(db.clone(), Box::new(|| Box::new(Determinista))),
            Arc::new(move |id| a.lock().unwrap().push(id)),
        )
        .unwrap();
        let inicio = director
            .con(|dj| dj.iniciar("de todo", 60, Some(4), Some(pool())))
            .unwrap();
        let Inicio::Lista { id } = inicio else {
            panic!("sin candidatas");
        };
        let limite = Instant::now() + Duration::from_secs(10);
        while director
            .con(|dj| Ok(dj.activa().is_some_and(|a| !a.completada)))
            .unwrap()
            && Instant::now() < limite
        {
            std::thread::sleep(Duration::from_millis(5));
        }
        assert!(!avisos.lock().unwrap().is_empty());
        assert!(avisos.lock().unwrap().iter().all(|s| *s == id));
        assert_eq!(
            crate::dj::sesiones::una(&db, id).unwrap().unwrap().estado,
            "lista"
        );
        // Con 60 pistas de 200 s hay de sobra para la hora pedida.
        assert!(crate::dj::sesiones::pistas(&db, id).unwrap().len() >= 15);
    }
}
