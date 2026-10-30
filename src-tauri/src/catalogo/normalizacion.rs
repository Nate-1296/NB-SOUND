//! De las etiquetas crudas, Shazam, AcoustID y el nombre del archivo a unos datos
//! listos para buscar (F4.1.2): `core/normalizer.py` de la V1.
//!
//! Primero las etiquetas; Shazam rellena lo que falte y aporta su ISRC; AcoustID
//! sube la confianza; y el nombre del archivo es el último recurso, sin títulos
//! genéricos ni artistas que contradigan a Shazam.

use super::etiquetas::Cruda;
use super::modelo::{CausaCuarentena, DeAcoustid, DeShazam, Fuente, Normalizada};
use super::texto::{
    extraer_anio_del_texto, extraer_featuring_del_titulo, limpiar_numero_pista,
    limpiar_version_titulo, normalizar_artista, normalizar_base, normalizar_isrc,
    normalizar_titulo, para_comparacion, parsear_nombre_archivo, separar_artista_principal,
    similitud_combinada,
};

const MIN_ARTISTA: usize = 2;
const MIN_TITULO: usize = 1;
const MIN_ARTISTA_NOMBRE_ARCHIVO: usize = 3;
/// `_SIMILITUD_COINCIDENCIA`.
const COINCIDEN: f64 = 0.75;

const TITULOS_GENERICOS: [&str; 19] = [
    "track",
    "audio",
    "music",
    "song",
    "untitled",
    "sin titulo",
    "unknown",
    "pista",
    "tema",
    "cancion",
    "new recording",
    "recording",
    "new track",
    "vocal",
    "instrumental",
    "demo",
    "draft",
    "test",
    "sample",
];

fn largo(s: &str) -> usize {
    s.chars().count()
}

fn desde_etiquetas(c: &Cruda, n: &mut Normalizada) {
    let titulo = normalizar_base(c.titulo.as_deref().unwrap_or_default());
    let (sin_feat, feat_titulo) = extraer_featuring_del_titulo(&titulo);
    n.titulo = normalizar_titulo(&sin_feat);
    n.titulo_para_match = para_comparacion(&limpiar_version_titulo(&n.titulo));
    let artista = normalizar_base(c.artista.as_deref().unwrap_or_default());
    let (principal, feat_artista) = separar_artista_principal(&artista);
    n.artista = normalizar_artista(&principal);
    n.artista_para_match = para_comparacion(&n.artista);
    n.featuring = feat_titulo.or(feat_artista);
    n.album = normalizar_base(c.album.as_deref().unwrap_or_default());
    n.album_para_match = para_comparacion(&n.album);
    n.numero = limpiar_numero_pista(c.numero.as_deref().unwrap_or_default());
    n.anio = extraer_anio_del_texto(c.anio.as_deref().unwrap_or_default());
    let (t, a) = (
        largo(&n.titulo_para_match) >= MIN_TITULO,
        largo(&n.artista_para_match) >= MIN_ARTISTA,
    );
    n.confianza = match (t, a) {
        (true, true) => 0.40,
        (true, false) | (false, true) => 0.20,
        (false, false) => 0.0,
    };
}

/// `_calcular_bonus_confianza_shazam`.
fn bonus_shazam(
    titulo: &str,
    artista: &str,
    sh_titulo: &str,
    sh_artista: &str,
    con_isrc: bool,
) -> f64 {
    if con_isrc {
        return 0.30;
    }
    let mut b = 0.0;
    if !titulo.is_empty()
        && !sh_titulo.is_empty()
        && similitud_combinada(titulo, sh_titulo) >= COINCIDEN
    {
        b += 0.15;
    }
    if !artista.is_empty()
        && !sh_artista.is_empty()
        && similitud_combinada(artista, sh_artista) >= COINCIDEN
    {
        b += 0.15;
    }
    if titulo.is_empty() && !sh_titulo.is_empty() {
        b += 0.10;
    }
    if artista.is_empty() && !sh_artista.is_empty() {
        b += 0.10;
    }
    f64::min(0.35, b)
}

fn fusionar(n: &mut Normalizada, shazam: Option<&DeShazam>, acoustid: Option<&DeAcoustid>) {
    let tiene_artista = largo(&n.artista_para_match) >= MIN_ARTISTA;
    let tiene_titulo = largo(&n.titulo_para_match) >= MIN_TITULO;
    if let Some(s) = shazam.filter(|s| s.identificado) {
        let sh_titulo = para_comparacion(&normalizar_titulo(&s.titulo));
        let sh_artista = para_comparacion(&normalizar_artista(&s.artista));
        if let Some(i) = s.isrc.as_deref().and_then(normalizar_isrc) {
            n.isrc = Some(i);
        }
        if !tiene_titulo && !sh_titulo.is_empty() {
            n.titulo = normalizar_titulo(&s.titulo);
            n.titulo_para_match = para_comparacion(&limpiar_version_titulo(&n.titulo));
            n.fuente_titulo = Fuente::Shazam;
        }
        if !tiene_artista && !sh_artista.is_empty() {
            n.artista = normalizar_artista(&s.artista);
            n.artista_para_match = para_comparacion(&n.artista);
            n.fuente_artista = Fuente::Shazam;
        }
        if n.album.is_empty() {
            if let Some(a) = s.album.as_deref().filter(|a| !a.is_empty()) {
                n.album = a.to_owned();
                n.album_para_match = para_comparacion(a);
            }
        }
        if n.anio.is_none() {
            n.anio = s.anio.filter(|a| *a != 0);
        }
        let b = bonus_shazam(
            &n.titulo_para_match,
            &n.artista_para_match,
            &sh_titulo,
            &sh_artista,
            n.isrc.is_some(),
        );
        n.confianza = f64::min(1.0, n.confianza + b);
    }
    if let Some(a) = acoustid.filter(|a| !a.grabaciones.is_empty()) {
        let m = a.mejor();
        let b = if m >= 0.90 {
            0.25
        } else if m >= 0.75 {
            0.15
        } else {
            0.05
        };
        n.confianza = f64::min(1.0, n.confianza + b);
    }
}

fn desde_nombre(
    nombre: &str,
    n: &mut Normalizada,
    tiene_artista: bool,
    tiene_titulo: bool,
    shazam: Option<&DeShazam>,
) {
    let inferido = parsear_nombre_archivo(nombre);
    let shazam_con_artista = shazam.filter(|s| s.identificado && !s.artista.is_empty());
    if let (false, Some(t)) = (tiene_titulo, inferido.titulo.as_deref()) {
        let t = normalizar_titulo(t);
        let tn = para_comparacion(&t);
        let generico = TITULOS_GENERICOS.contains(&tn.as_str()) || largo(&tn) <= 2;
        if !generico || shazam_con_artista.is_some() {
            n.titulo_para_match = para_comparacion(&limpiar_version_titulo(&t));
            n.titulo = t;
            n.fuente_titulo = Fuente::NombreArchivo;
        }
    }
    if let (false, Some(a)) = (tiene_artista, inferido.artista.as_deref()) {
        let a = normalizar_artista(a);
        let an = para_comparacion(&a);
        let contradice = shazam_con_artista.is_some_and(|s| {
            similitud_combinada(&an, &para_comparacion(&normalizar_artista(&s.artista))) < COINCIDEN
        });
        if largo(&an) >= MIN_ARTISTA_NOMBRE_ARCHIVO && !contradice {
            n.artista = a;
            n.artista_para_match = an;
            n.fuente_artista = Fuente::NombreArchivo;
        }
    }
    if n.numero.is_none() {
        n.numero = inferido.numero.and_then(|x| x.parse().ok());
    }
}

/// `normalizar_metadata`: los datos, o la cuarentena si no queda ni título ni
/// artista. Con uno de los dos basta para buscar.
///
/// # Errors
///
/// [`CausaCuarentena::MetadataInsuficiente`] sin título ni artista utilizables.
pub fn normalizar(
    cruda: &Cruda,
    duracion_seg: f64,
    nombre_archivo: &str,
    shazam: Option<&DeShazam>,
    acoustid: Option<&DeAcoustid>,
) -> Result<Normalizada, CausaCuarentena> {
    let mut n = Normalizada {
        duracion_seg: Some(duracion_seg).filter(|d| *d > 0.0),
        ..Normalizada::default()
    };
    desde_etiquetas(cruda, &mut n);
    fusionar(&mut n, shazam, acoustid);
    let tiene = |n: &Normalizada| {
        (
            largo(&n.artista_para_match) >= MIN_ARTISTA,
            largo(&n.titulo_para_match) >= MIN_TITULO,
        )
    };
    let (a, t) = tiene(&n);
    if !a || !t {
        desde_nombre(nombre_archivo, &mut n, a, t, shazam);
    }
    match tiene(&n) {
        (false, false) => Err(CausaCuarentena::MetadataInsuficiente),
        _ => Ok(n),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cruda(titulo: &str, artista: &str) -> Cruda {
        Cruda {
            titulo: Some(titulo.to_owned()).filter(|s| !s.is_empty()),
            artista: Some(artista.to_owned()).filter(|s| !s.is_empty()),
            numero: Some("3/12".into()),
            anio: Some("2017-05-01".into()),
            ..Cruda::default()
        }
    }

    #[test]
    fn las_etiquetas_dan_titulo_artista_y_featuring() {
        let n = normalizar(
            &cruda(
                "Despacito (feat. Daddy Yankee) [Official Video]",
                "Luis Fonsi",
            ),
            228.0,
            "x.mp3",
            None,
            None,
        )
        .unwrap();
        assert_eq!(n.titulo, "Despacito");
        assert_eq!(n.titulo_para_match, "despacito");
        assert_eq!(
            (n.artista.as_str(), n.featuring.as_deref()),
            ("Luis Fonsi", Some("Daddy Yankee"))
        );
        assert_eq!((n.numero, n.anio), (Some(3), Some(2017)));
        assert_eq!(n.confianza, 0.40);
        assert_eq!(n.fuente_titulo, Fuente::TagLocal);
    }

    #[test]
    fn shazam_rellena_lo_que_falta_y_sube_la_confianza() {
        let s = DeShazam {
            identificado: true,
            titulo: "Despacito".into(),
            artista: "Luis Fonsi".into(),
            isrc: Some("us-um7-17-00001".into()),
            album: Some("Vida".into()),
            anio: Some(2019),
        };
        let n = normalizar(&cruda("", ""), 228.0, "01 - track.mp3", Some(&s), None).unwrap();
        assert_eq!(
            (n.titulo.as_str(), n.fuente_titulo),
            ("Despacito", Fuente::Shazam)
        );
        assert_eq!(n.isrc.as_deref(), Some("USUM71700001"));
        assert_eq!(n.album, "Vida");
        assert_eq!(n.anio, Some(2017), "el año de las etiquetas manda");
        assert!((n.confianza - 0.30).abs() < 1e-9, "{}", n.confianza);
    }

    #[test]
    fn acoustid_suma_segun_su_confianza() {
        let a = DeAcoustid {
            grabaciones: vec!["r".into()],
            confianzas: vec![0.93],
        };
        let n = normalizar(&cruda("Song", "Artist"), 200.0, "x.mp3", None, Some(&a)).unwrap();
        assert!((n.confianza - 0.65).abs() < 1e-9);
    }

    #[test]
    fn el_nombre_del_archivo_es_el_ultimo_recurso() {
        let n = normalizar(
            &Cruda::default(),
            200.0,
            "Maná - 03 - Clavado en un bar.mp3",
            None,
            None,
        )
        .unwrap();
        assert_eq!(
            (n.artista.as_str(), n.titulo.as_str(), n.numero),
            ("Maná", "Clavado en un bar", Some(3))
        );
        assert_eq!(n.fuente_artista, Fuente::NombreArchivo);
        assert_eq!(
            normalizar(&Cruda::default(), 200.0, "track.mp3", None, None),
            Err(CausaCuarentena::MetadataInsuficiente),
            "un título genérico sin artista no sirve"
        );
    }

    #[test]
    fn el_artista_del_nombre_no_contradice_a_shazam() {
        let s = DeShazam {
            identificado: true,
            titulo: String::new(),
            artista: "Shakira".into(),
            ..DeShazam::default()
        };
        let c = Cruda {
            titulo: Some("Hips".into()),
            ..Cruda::default()
        };
        let n = normalizar(&c, 200.0, "Otro Artista - Hips.mp3", Some(&s), None).unwrap();
        assert_eq!(n.artista, "Shakira");
    }
}
