//! MPRIS con `mpris-server`.
//!
//! `mpris-server` no es `Send`: el reproductor de D-Bus vive en su propio hilo,
//! dentro de un `block_on`, y le llegan las instantáneas por un canal asíncrono
//! hecho con la biblioteca estándar (no hace falta una dependencia para eso).

use std::cell::Cell;
use std::collections::VecDeque;
use std::future::Future;
use std::pin::pin;
use std::rc::Rc;
use std::sync::{Arc, Mutex};
use std::task::{Poll, Waker};

use mpris_server::{LoopStatus, Metadata, PlaybackStatus, Player, Time};

use super::{metadatos, Metadatos};
use crate::cola::Repeticion;
use crate::db::BaseDeDatos;
use crate::paths::Rutas;
use crate::reproductor::{Buzon, Instantanea, Orden};

/// Un canal de un solo consumidor que se puede esperar con `.await`.
#[derive(Default)]
struct Canal {
    cola: Mutex<VecDeque<Instantanea>>,
    despertar: Mutex<Option<Waker>>,
}

impl Canal {
    fn enviar(&self, i: Instantanea) {
        if let Ok(mut c) = self.cola.lock() {
            // Solo importa la última: si el escritorio va por detrás, se salta.
            c.clear();
            c.push_back(i);
        }
        if let Some(w) = self.despertar.lock().ok().and_then(|mut d| d.take()) {
            w.wake();
        }
    }

    fn recibir(&self) -> impl Future<Output = Instantanea> + '_ {
        std::future::poll_fn(move |cx| {
            if let Some(i) = self.cola.lock().ok().and_then(|mut c| c.pop_front()) {
                return Poll::Ready(i);
            }
            if let Ok(mut d) = self.despertar.lock() {
                *d = Some(cx.waker().clone());
            }
            // Pudo llegar algo entre mirar y apuntar el despertador.
            match self.cola.lock().ok().and_then(|mut c| c.pop_front()) {
                Some(i) => Poll::Ready(i),
                None => Poll::Pending,
            }
        })
    }
}

pub struct Controles {
    canal: Arc<Canal>,
}

fn repeticion(texto: &str) -> LoopStatus {
    match Repeticion::desde_v1(texto) {
        Some(Repeticion::Todo) => LoopStatus::Playlist,
        Some(Repeticion::Uno) => LoopStatus::Track,
        _ => LoopStatus::None,
    }
}

fn a_metadata(m: &Metadatos) -> Metadata {
    let mut b = Metadata::builder()
        .trackid(
            mpris_server::TrackId::try_from(format!("/org/nbsound/pista/{}", m.id))
                .unwrap_or(mpris_server::TrackId::NO_TRACK),
        )
        .title(m.titulo.clone())
        .artist([m.artista.clone()])
        .album(m.album.clone())
        .length(Time::from_micros((m.duracion_seg * 1e6) as i64));
    if let Some(p) = &m.portada {
        b = b.art_url(format!("file://{}", p.display()));
    }
    b.build()
}

impl Controles {
    pub fn arrancar(db: BaseDeDatos, rutas: Rutas, buzon: Buzon) -> Option<Self> {
        let canal = Arc::new(Canal::default());
        let (listo_tx, listo_rx) = std::sync::mpsc::channel();
        let canal_hilo = Arc::clone(&canal);
        std::thread::Builder::new()
            .name("controles-sistema".into())
            .spawn(move || {
                tauri::async_runtime::block_on(async move {
                    let player = match Player::builder("nbsound")
                        .identity("NB Sound")
                        .desktop_entry("nb-sound")
                        .can_play(true)
                        .can_pause(true)
                        .can_go_next(true)
                        .can_go_previous(true)
                        .can_seek(true)
                        .can_control(true)
                        .build()
                        .await
                    {
                        Ok(p) => p,
                        Err(error) => {
                            tracing::info!(error = %error, "sin MPRIS: no hay sesión de D-Bus");
                            let _ = listo_tx.send(false);
                            return;
                        }
                    };
                    let _ = listo_tx.send(true);
                    let sonando = Rc::new(Cell::new(false));
                    let posicion = Rc::new(Cell::new(0.0f64));
                    conectar(&player, &buzon, &sonando, &posicion);

                    let correr = pin!(player.run());
                    let actualizar = pin!(async {
                        let mut pista: Option<i64> = None;
                        loop {
                            let i = canal_hilo.recibir().await;
                            aplicar(&player, &i, &mut pista, (&db, &rutas), &sonando, &posicion)
                                .await;
                        }
                    });
                    // Los dos a la vez, sin una dependencia para unirlos.
                    let (mut correr, mut actualizar) = (correr, actualizar);
                    std::future::poll_fn(|cx| {
                        if correr.as_mut().poll(cx).is_ready() {
                            return Poll::Ready(());
                        }
                        let _ = actualizar.as_mut().poll(cx);
                        Poll::Pending
                    })
                    .await;
                });
            })
            .ok()?;
        listo_rx.recv().ok().filter(|ok| *ok)?;
        Some(Self { canal })
    }

    pub fn actualizar(&self, i: &Instantanea) {
        self.canal.enviar(i.clone());
    }
}

fn conectar(player: &Player, buzon: &Buzon, sonando: &Rc<Cell<bool>>, posicion: &Rc<Cell<f64>>) {
    let b = buzon.clone();
    player.connect_play_pause(move |_| b.enviar(Orden::PausarReanudar));
    let (b, s) = (buzon.clone(), Rc::clone(sonando));
    player.connect_play(move |_| {
        if !s.get() {
            b.enviar(Orden::PausarReanudar);
        }
    });
    let (b, s) = (buzon.clone(), Rc::clone(sonando));
    player.connect_pause(move |_| {
        if s.get() {
            b.enviar(Orden::PausarReanudar);
        }
    });
    let (b, s) = (buzon.clone(), Rc::clone(sonando));
    player.connect_stop(move |_| {
        if s.get() {
            b.enviar(Orden::PausarReanudar);
        }
    });
    let b = buzon.clone();
    player.connect_next(move |_| b.enviar(Orden::Siguiente));
    let b = buzon.clone();
    player.connect_previous(move |_| b.enviar(Orden::Anterior));
    let (b, p) = (buzon.clone(), Rc::clone(posicion));
    player.connect_seek(move |_, desplazamiento| {
        b.enviar(Orden::Buscar(
            p.get() + desplazamiento.as_micros() as f64 / 1e6,
        ));
    });
    let b = buzon.clone();
    player.connect_set_position(move |_, _, t| b.enviar(Orden::Buscar(t.as_micros() as f64 / 1e6)));
    let b = buzon.clone();
    player.connect_set_shuffle(move |_, activo| b.enviar(Orden::Aleatorio(activo)));
    let b = buzon.clone();
    player.connect_set_loop_status(move |_, l| {
        b.enviar(Orden::Repeticion(match l {
            LoopStatus::None => Repeticion::Ninguno,
            LoopStatus::Track => Repeticion::Uno,
            LoopStatus::Playlist => Repeticion::Todo,
        }));
    });
    let b = buzon.clone();
    player.connect_set_volume(move |_, v| b.enviar(Orden::Volumen(v.clamp(0.0, 1.0) as f32)));
}

async fn aplicar(
    player: &Player,
    i: &Instantanea,
    pista: &mut Option<i64>,
    (db, rutas): (&BaseDeDatos, &Rutas),
    sonando: &Cell<bool>,
    posicion: &Cell<f64>,
) {
    sonando.set(i.estado == "reproduciendo");
    let estado = match i.estado.as_str() {
        "reproduciendo" => PlaybackStatus::Playing,
        "pausado" => PlaybackStatus::Paused,
        _ => PlaybackStatus::Stopped,
    };
    let _ = player.set_playback_status(estado).await;
    if *pista != i.pista_id {
        *pista = i.pista_id;
        let m = i
            .pista_id
            .and_then(|id| metadatos(db, rutas, id))
            .map_or_else(Metadata::new, |m| a_metadata(&m));
        let _ = player.set_metadata(m).await;
    }
    // Un salto de más de segundo y medio es una búsqueda, y los clientes de MPRIS
    // solo se enteran si se les avisa.
    let anterior = posicion.replace(i.posicion_seg);
    let t = Time::from_micros((i.posicion_seg * 1e6) as i64);
    player.set_position(t);
    if (i.posicion_seg - anterior).abs() > 1.5 {
        let _ = player.seeked(t).await;
    }
    let _ = player.set_shuffle(i.aleatorio).await;
    let _ = player.set_loop_status(repeticion(&i.repeticion)).await;
    let _ = player.set_volume(f64::from(i.volumen)).await;
    let _ = player.set_can_go_next(!i.cola.is_empty()).await;
    let _ = player.set_can_go_previous(!i.cola.is_empty()).await;
}

#[cfg(test)]
mod tests {
    use super::*;

    fn instantanea(pista: Option<i64>) -> Instantanea {
        Instantanea {
            estado: "reproduciendo".into(),
            pista_id: pista,
            posicion_seg: 0.0,
            duracion_seg: 0.0,
            indice_cola: None,
            cola: Vec::new(),
            aleatorio: false,
            repeticion: "ninguno".into(),
            volumen: 1.0,
            normalizar: true,
            karaoke_disponible: false,
            karaoke_activo: false,
        }
    }

    #[test]
    fn el_canal_entrega_la_ultima_y_despierta_a_quien_espera() {
        let canal = Arc::new(Canal::default());
        canal.enviar(instantanea(Some(1)));
        canal.enviar(instantanea(Some(2)));
        let c = Arc::clone(&canal);
        let hilo = std::thread::spawn(move || {
            let primera = tauri::async_runtime::block_on(c.recibir());
            let segunda = tauri::async_runtime::block_on(c.recibir());
            (primera.pista_id, segunda.pista_id)
        });
        std::thread::sleep(std::time::Duration::from_millis(50));
        canal.enviar(instantanea(Some(3)));
        assert_eq!(
            hilo.join().unwrap(),
            (Some(2), Some(3)),
            "solo importa la última"
        );
    }

    #[test]
    fn la_repeticion_se_traduce_a_mpris_en_los_dos_sentidos() {
        assert_eq!(repeticion("todo"), LoopStatus::Playlist);
        assert_eq!(repeticion("uno"), LoopStatus::Track);
        assert_eq!(repeticion("ninguno"), LoopStatus::None);
    }
}
