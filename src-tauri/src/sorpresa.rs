//! "Sorpréndeme" (tecla D): una canción elegida al azar entre las que conviene
//! redescubrir. Es `sorprenderme` de la V1 (`ui/modelos_qml.py`).
//!
//! No es un sorteo plano. La V1 aparta lo que acaba de sonar y lo que ya sugirió
//! hace poco, evita repetir el artista y el álbum que suenan, puntúa lo demás
//! (favoritas y algo escuchadas suben; lo escuchado hace poco y lo muy corto o
//! muy largo bajan) y elige con peso entre las mejores. Elegir siempre la mejor
//! era determinista y repetía la misma secuencia; el peso conserva el gusto sin
//! que cada pulsación empiece en el mismo sitio.
//!
//! La memoria de lo sugerido vive en el proceso, como en la V1: al reiniciar la
//! aplicación se olvida, y no hace falta más.

use std::collections::VecDeque;
use std::sync::Mutex;

use crate::db::BaseDeDatos;
use crate::dj::azar::Azar;
use crate::error::{NsError, NsResult};

/// Lo que la V1 recuerda de sus sugerencias: hasta 32 artistas y 48 álbumes.
const ARTISTAS_RECIENTES: usize = 32;
const ALBUMES_RECIENTES: usize = 48;

/// Una candidata, con lo que la puntuación necesita.
#[derive(Debug, Clone)]
pub struct Candidata {
    pub id: i64,
    pub artista: Option<i64>,
    pub album: Option<i64>,
    pub reproducciones: u32,
    pub favorita: bool,
    pub bitrate_kbps: u32,
    pub duracion_seg: f64,
    pub escuchada: bool,
}

/// Lo que se sugirió hace poco, para no volver a ello.
#[derive(Debug, Default)]
pub struct Memoria {
    pistas: VecDeque<i64>,
    artistas: VecDeque<i64>,
    albumes: VecDeque<i64>,
}

fn recordar(cola: &mut VecDeque<i64>, valor: Option<i64>, limite: usize) {
    let Some(v) = valor else { return };
    cola.retain(|x| *x != v);
    cola.push_back(v);
    while cola.len() > limite {
        cola.pop_front();
    }
}

/// `_limite_sugerencias_recientes`: una cuarta parte de lo elegible, entre 80 y 240.
fn limite_pistas(elegibles: usize) -> usize {
    (elegibles / 4).clamp(80, 240)
}

/// `_filtrar_con_fallback`: el filtro solo se aplica si deja algo.
fn filtrar(items: Vec<&Candidata>, condicion: impl Fn(&Candidata) -> bool) -> Vec<&Candidata> {
    let filtrados: Vec<_> = items.iter().copied().filter(|c| condicion(c)).collect();
    if filtrados.is_empty() {
        items
    } else {
        filtrados
    }
}

/// `_score_sugerencia`, sin el desempate de una milésima: lo da el peso al elegir.
fn puntuar(c: &Candidata, m: &Memoria) -> f64 {
    let mut p = 0.0;
    if m.pistas.contains(&c.id) {
        p -= 120.0;
    }
    if c.artista.is_some_and(|a| m.artistas.contains(&a)) {
        p -= 14.0;
    }
    if c.album.is_some_and(|a| m.albumes.contains(&a)) {
        p -= 10.0;
    }
    p += (f64::from(c.reproducciones) * 0.12).min(3.0);
    if c.favorita {
        p += 1.2;
    }
    p += ((f64::from(c.bitrate_kbps) - 160.0) / 128.0).clamp(0.0, 1.0);
    let d = c.duracion_seg.max(0.0);
    if (45.0..=540.0).contains(&d) {
        p += 0.4;
    } else if d > 0.0 && d < 30.0 {
        p -= 1.0;
    } else if d > 900.0 {
        p -= 2.0;
    }
    if c.escuchada {
        p -= 2.5;
    }
    p
}

/// Elige una candidata y la apunta en la memoria. `actual` es la que suena, que
/// nunca se sugiere. `None` si no hay ninguna otra.
pub fn elegir(
    candidatas: &[Candidata],
    actual: Option<&Candidata>,
    memoria: &mut Memoria,
    azar: &mut Azar,
) -> Option<i64> {
    let elegibles: Vec<&Candidata> = candidatas
        .iter()
        .filter(|c| actual.is_none_or(|a| a.id != c.id))
        .collect();
    if elegibles.is_empty() {
        return None;
    }
    let limite = limite_pistas(elegibles.len());
    if let Some(a) = actual {
        recordar(&mut memoria.pistas, Some(a.id), limite);
        recordar(&mut memoria.artistas, a.artista, ARTISTAS_RECIENTES);
        recordar(&mut memoria.albumes, a.album, ALBUMES_RECIENTES);
    }
    let m = &*memoria;
    let mut s = filtrar(elegibles, |c| !m.pistas.contains(&c.id));
    let artista = actual.and_then(|a| a.artista);
    let album = actual.and_then(|a| a.album);
    s = filtrar(s, |c| artista.is_none() || c.artista != artista);
    s = filtrar(s, |c| album.is_none() || c.album != album);
    s = filtrar(s, |c| c.artista.is_none_or(|a| !m.artistas.contains(&a)));
    s = filtrar(s, |c| c.album.is_none_or(|a| !m.albumes.contains(&a)));

    let mut puntuadas: Vec<(f64, &Candidata)> = s.into_iter().map(|c| (puntuar(c, m), c)).collect();
    puntuadas.sort_by(|a, b| b.0.total_cmp(&a.0).then(a.1.id.cmp(&b.1.id)));
    // Las 40 mejores (o las que haya), con peso decreciente: la primera pesa tantas
    // veces como candidatas hay, la última una.
    let top = &puntuadas[..puntuadas.len().min(40)];
    let total = (top.len() * (top.len() + 1) / 2) as f64;
    let mut tirada = azar.real() * total;
    let mut elegida = top[top.len() - 1].1;
    for (i, (_, c)) in top.iter().enumerate() {
        let peso = (top.len() - i) as f64;
        if tirada < peso {
            elegida = c;
            break;
        }
        tirada -= peso;
    }
    recordar(&mut memoria.pistas, Some(elegida.id), limite);
    recordar(&mut memoria.artistas, elegida.artista, ARTISTAS_RECIENTES);
    recordar(&mut memoria.albumes, elegida.album, ALBUMES_RECIENTES);
    Some(elegida.id)
}

/// Las candidatas: toda la biblioteca, como la V1 (que pedía hasta 3.000).
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn candidatas(db: &BaseDeDatos) -> NsResult<Vec<Candidata>> {
    let conn = db.conexion()?;
    let mut s = conn
        .prepare(
            "SELECT id, artista_id, album_id, reproducciones, favorita,
                    coalesce(bitrate_kbps, 0), coalesce(duracion_seg, 0),
                    ultima_reproduccion IS NOT NULL
             FROM pistas WHERE estado = 'biblioteca'",
        )
        .map_err(|_| NsError::StorageFailure)?;
    let filas = s
        .query_map([], |f| {
            Ok(Candidata {
                id: f.get(0)?,
                artista: f.get(1)?,
                album: f.get(2)?,
                reproducciones: f.get(3)?,
                favorita: f.get(4)?,
                bitrate_kbps: f.get(5)?,
                duracion_seg: f.get(6)?,
                escuchada: f.get(7)?,
            })
        })
        .map_err(|_| NsError::StorageFailure)?;
    filas
        .collect::<rusqlite::Result<_>>()
        .map_err(|_| NsError::StorageFailure)
}

/// La memoria y el azar de la sesión: los dos viven lo que vive el proceso.
pub struct Sorpresa(Mutex<(Memoria, Azar)>);

impl Default for Sorpresa {
    fn default() -> Self {
        Self(Mutex::new((Memoria::default(), Azar::sin_semilla())))
    }
}

impl Sorpresa {
    /// La siguiente sorpresa, sin repetir la que suena (`actual`).
    ///
    /// # Errors
    ///
    /// [`NsError::StorageFailure`] si no se puede leer la biblioteca.
    pub fn siguiente(&self, db: &BaseDeDatos, actual: Option<i64>) -> NsResult<Option<i64>> {
        let todas = candidatas(db)?;
        let sonando = actual.and_then(|id| todas.iter().find(|c| c.id == id));
        let mut g = self
            .0
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let (memoria, azar) = &mut *g;
        Ok(elegir(&todas, sonando, memoria, azar))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn c(id: i64, artista: i64, album: i64) -> Candidata {
        Candidata {
            id,
            artista: Some(artista),
            album: Some(album),
            reproducciones: 0,
            favorita: false,
            bitrate_kbps: 192,
            duracion_seg: 200.0,
            escuchada: false,
        }
    }

    #[test]
    fn nunca_sugiere_la_que_suena_ni_su_artista_si_hay_otro() {
        let todas = [c(1, 1, 10), c(2, 1, 10), c(3, 2, 20)];
        let mut m = Memoria::default();
        let mut azar = Azar::con_semilla(7);
        for _ in 0..20 {
            let mut m2 = Memoria::default();
            assert_eq!(elegir(&todas, Some(&todas[0]), &mut m2, &mut azar), Some(3));
        }
        // Sin otra opción, el mismo artista vale: el filtro nunca deja la lista vacía.
        let dos = [c(1, 1, 10), c(2, 1, 10)];
        assert_eq!(elegir(&dos, Some(&dos[0]), &mut m, &mut azar), Some(2));
    }

    #[test]
    fn no_repite_hasta_agotar_lo_elegible() {
        let todas: Vec<_> = (1..=10).map(|i| c(i, i, i * 10)).collect();
        let mut m = Memoria::default();
        let mut azar = Azar::con_semilla(42);
        let mut vistas = std::collections::BTreeSet::new();
        for _ in 0..10 {
            vistas.insert(elegir(&todas, None, &mut m, &mut azar).unwrap());
        }
        assert_eq!(vistas.len(), 10);
    }

    #[test]
    fn sin_otra_cancion_no_hay_sorpresa() {
        let una = [c(1, 1, 10)];
        assert_eq!(
            elegir(
                &una,
                Some(&una[0]),
                &mut Memoria::default(),
                &mut Azar::con_semilla(1)
            ),
            None
        );
        assert_eq!(
            elegir(
                &[],
                None,
                &mut Memoria::default(),
                &mut Azar::con_semilla(1)
            ),
            None
        );
    }

    #[test]
    fn lo_nunca_escuchado_y_favorito_puntua_por_encima_de_lo_reciente() {
        let m = Memoria::default();
        let mut nueva = c(1, 1, 1);
        nueva.favorita = true;
        let mut vieja = c(2, 2, 2);
        vieja.escuchada = true;
        assert!(puntuar(&nueva, &m) > puntuar(&vieja, &m));
    }

    #[test]
    fn las_candidatas_son_solo_las_de_la_biblioteca() {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO pistas (id, titulo, ruta) VALUES (1, 'a', 'a'), (2, 'b', 'b');
                 INSERT INTO pistas (id, titulo, ruta, estado) VALUES (3, 'c', 'c', 'duplicado');",
            )
            .unwrap();
        let ids: Vec<_> = candidatas(&db).unwrap().iter().map(|c| c.id).collect();
        assert_eq!(ids, [1, 2]);
    }
}
