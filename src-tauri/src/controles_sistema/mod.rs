//! Los controles multimedia del sistema (F2.1.5, ADR-003): MPRIS en Linux, SMTC en
//! Windows y el centro de reproducción de macOS.
//!
//! El escritorio muestra lo que suena (título, artista, álbum, portada, duración y
//! posición) y sus botones y las teclas multimedia mandan órdenes al reproductor.
//! En Linux, aleatorio y repetición van en los dos sentidos. La V1 escribía MPRIS a
//! mano sobre Qt D-Bus y necesitó cinco correcciones de firmas; aquí lo hace
//! `mpris-server`.
//!
//! Recibe las instantáneas del reproductor y resuelve los datos de la pista en su
//! propio hilo: nada de esto pasa por el hilo de audio ni por el de la ventana.

#[cfg(target_os = "linux")]
mod linux;
#[cfg(any(target_os = "windows", target_os = "macos"))]
mod souvlaki_plataforma;

use std::path::PathBuf;

use crate::db::BaseDeDatos;
use crate::paths::Rutas;
use crate::reproductor::Instantanea;

/// Lo que el escritorio pinta de la pista que suena.
#[derive(Debug, Clone, PartialEq)]
pub struct Metadatos {
    pub id: i64,
    pub titulo: String,
    pub artista: String,
    pub album: String,
    pub duracion_seg: f64,
    /// Una miniatura en la caché: los escritorios quieren un `file://`.
    pub portada: Option<PathBuf>,
}

/// Los datos de una pista para el escritorio, con su portada en la caché.
pub fn metadatos(db: &BaseDeDatos, rutas: &Rutas, pista: i64) -> Option<Metadatos> {
    let r = crate::biblioteca::resumenes(db, &[pista])
        .ok()?
        .into_iter()
        .next()?;
    let portada = r.tiene_portada.then(|| {
        let peticion = crate::portadas::Peticion {
            clase: crate::portadas::Clase::Pista,
            id: pista,
            tamano: Some(320),
        };
        crate::portadas::servir(db, rutas, peticion)
            .ok()
            .and_then(|_| crate::portadas::ruta_en_cache(db, rutas, peticion))
    });
    Some(Metadatos {
        id: r.id,
        titulo: r.titulo,
        artista: r.artista,
        album: r.album,
        duracion_seg: r.duracion_seg,
        portada: portada.flatten(),
    })
}

/// La conexión con el escritorio. Sin escritorio (una sesión sin D-Bus, por
/// ejemplo) no existe, y la aplicación funciona igual.
pub struct ControlesSistema {
    #[cfg(target_os = "linux")]
    interior: linux::Controles,
    #[cfg(any(target_os = "windows", target_os = "macos"))]
    interior: souvlaki_plataforma::Controles,
}

impl ControlesSistema {
    /// Conecta con el escritorio.
    pub fn arrancar(
        app: &tauri::AppHandle,
        db: BaseDeDatos,
        rutas: Rutas,
        buzon: crate::reproductor::Buzon,
    ) -> Option<Self> {
        #[cfg(target_os = "linux")]
        {
            let _ = app;
            linux::Controles::arrancar(db, rutas, buzon).map(|interior| Self { interior })
        }
        #[cfg(any(target_os = "windows", target_os = "macos"))]
        {
            souvlaki_plataforma::Controles::arrancar(app, db, rutas, buzon)
                .map(|interior| Self { interior })
        }
        #[cfg(not(any(target_os = "linux", target_os = "windows", target_os = "macos")))]
        {
            let _ = (app, db, rutas, buzon);
            None
        }
    }

    /// Cuenta al escritorio lo que acaba de cambiar.
    pub fn actualizar(&self, i: &Instantanea) {
        self.interior.actualizar(i);
    }
}
