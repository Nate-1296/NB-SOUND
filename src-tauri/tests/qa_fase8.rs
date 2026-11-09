//! Pruebas finales de la Fase 8 que en la aplicación pasan por un selector nativo
//! (la tarjeta SVG y la copia a un dispositivo): el arnés no puede manejarlo, así
//! que se llama a la misma función que el comando le pasa la ruta elegida, sobre
//! la base de la copia aislada. Las lanza `scripts/qa/ui-qa.sh fase8`.

use std::path::{Path, PathBuf};

use lofty::file::TaggedFileExt;
use nb_sound_lib::copia_dispositivo::{
    copiar, EstructuraCarpetas, OpcionesCopiaDispositivo, OrigenCopia,
};
use nb_sound_lib::db::BaseDeDatos;
use nb_sound_lib::paths::Rutas;

fn variable(nombre: &str) -> PathBuf {
    PathBuf::from(std::env::var_os(nombre).unwrap_or_else(|| panic!("falta {nombre}")))
}

fn informar(caso: &str, datos: serde_json::Value) {
    println!(
        "INFORME_QA {}",
        serde_json::json!({ "caso": caso, "datos": datos })
    );
}

#[test]
#[ignore = "lo ejecuta scripts/qa/ui-qa.sh fase8 sobre la copia aislada"]
fn la_tarjeta_svg_se_exporta_valida_y_con_las_cifras_del_resumen() {
    let db = BaseDeDatos::abrir(&variable("NB_QA_DB")).unwrap();
    let destino = variable("NB_QA_SALIDA").join("resumen.svg");
    nb_sound_lib::perfil::exportar_tarjeta(&db, None, &destino).unwrap();
    let svg = std::fs::read_to_string(&destino).unwrap();
    let resumen = nb_sound_lib::perfil::resumen_escucha(&db, None).unwrap();
    assert!(svg.trim_start().starts_with("<svg") || svg.trim_start().starts_with("<?xml"));
    assert!(svg.trim_end().ends_with("</svg>"));
    // Etiquetas equilibradas: cada apertura sin cierre propio tiene su cierre.
    let aperturas =
        svg.matches('<').count() - svg.matches("</").count() - svg.matches("<?").count();
    let autocerradas = svg.matches("/>").count();
    assert_eq!(
        aperturas - autocerradas,
        svg.matches("</").count(),
        "etiquetas sin cerrar"
    );
    let reproducciones = resumen.reproducciones.to_string();
    let con_puntos = {
        let s = reproducciones.as_bytes();
        let mut r = String::new();
        for (i, c) in s.iter().enumerate() {
            if i > 0 && (s.len() - i).is_multiple_of(3) {
                r.push('.');
            }
            r.push(*c as char);
        }
        r
    };
    assert!(
        svg.contains(&reproducciones) || svg.contains(&con_puntos),
        "la tarjeta no dice las {reproducciones} reproducciones"
    );
    informar(
        "tarjeta_svg",
        serde_json::json!({ "bytes": svg.len(), "reproducciones": resumen.reproducciones }),
    );
}

fn archivos(dir: &Path, ext: &str) -> Vec<PathBuf> {
    let mut v = Vec::new();
    for e in std::fs::read_dir(dir).unwrap().flatten() {
        let p = e.path();
        if p.is_dir() {
            v.extend(archivos(&p, ext));
        } else if p.extension().is_some_and(|x| x == ext) {
            v.push(p);
        }
    }
    v
}

#[test]
#[ignore = "lo ejecuta scripts/qa/ui-qa.sh fase8 sobre la copia aislada"]
fn la_copia_a_un_dispositivo_lleva_carpetas_portada_lista_y_wav() {
    std::env::set_var("NB_SOUND_TEST_DIR", variable("NB_QA_ROOT"));
    let rutas = Rutas::resolver().unwrap();
    let db = BaseDeDatos::abrir(&variable("NB_QA_DB")).unwrap();
    let salida = variable("NB_QA_SALIDA");

    // Las favoritas, con la portada dentro y su lista.
    let favoritas = salida.join("usb-favoritas");
    let _ = std::fs::remove_dir_all(&favoritas);
    let r = copiar(
        &db,
        &rutas,
        &OpcionesCopiaDispositivo {
            origen: OrigenCopia::Favoritas,
            playlist_id: None,
            estructura: EstructuraCarpetas::ArtistaAlbum,
            incrustar_portada: true,
            convertir_a_wav: false,
        },
        &favoritas,
    )
    .unwrap();
    assert!(r.copiadas > 0 && r.errores == 0, "{r:?}");
    let mp3 = archivos(&favoritas, "mp3");
    assert_eq!(mp3.len() as u32, r.copiadas);
    // Artista / Álbum / archivo.
    assert!(mp3
        .iter()
        .all(|p| p.strip_prefix(&favoritas).unwrap().components().count() == 3));
    let con_portada = mp3
        .iter()
        .filter(|p| {
            lofty::read_from_path(p)
                .ok()
                .and_then(|f| f.primary_tag().map(|t| !t.pictures().is_empty()))
                .unwrap_or(false)
        })
        .count();
    let lista = favoritas.join(r.lista_m3u8.clone().expect("lista de favoritas"));
    let texto = std::fs::read_to_string(&lista).unwrap();
    let entradas: Vec<&str> = texto
        .lines()
        .filter(|l| !l.starts_with('#') && !l.is_empty())
        .collect();
    assert_eq!(entradas.len() as u32, r.copiadas);
    assert!(
        entradas.iter().all(|e| favoritas.join(e).is_file()),
        "la lista apunta a archivos que no están"
    );

    // Una playlist corta, en WAV.
    let (id, n): (i64, i64) = db
        .conexion()
        .unwrap()
        .query_row(
            "SELECT p.id, count(*) FROM playlists p JOIN playlist_pistas pp ON pp.playlist_id = p.id
             GROUP BY p.id HAVING count(*) >= 2
             ORDER BY count(*) LIMIT 1",
            [],
            |f| Ok((f.get(0)?, f.get(1)?)),
        )
        .unwrap();
    let wav = salida.join("usb-wav");
    let _ = std::fs::remove_dir_all(&wav);
    let w = copiar(
        &db,
        &rutas,
        &OpcionesCopiaDispositivo {
            origen: OrigenCopia::Playlist,
            playlist_id: Some(id),
            estructura: EstructuraCarpetas::Plana,
            incrustar_portada: false,
            convertir_a_wav: true,
        },
        &wav,
    )
    .unwrap();
    let wavs = archivos(&wav, "wav");
    assert_eq!(wavs.len() as i64, n);
    for f in &wavs {
        let b = std::fs::read(f).unwrap();
        assert!(
            &b[..4] == b"RIFF" && &b[8..12] == b"WAVE" && b.len() > 1_000_000,
            "{}",
            f.display()
        );
    }
    informar(
        "copia_dispositivo",
        serde_json::json!({
            "favoritas": r.copiadas, "conPortada": con_portada, "bytes": r.bytes_escritos,
            "lista": r.lista_m3u8, "playlistWav": n, "wavCopiados": w.copiadas
        }),
    );
    assert!(
        con_portada * 10 >= mp3.len() * 9,
        "solo {con_portada} de {} con portada",
        mp3.len()
    );
}
