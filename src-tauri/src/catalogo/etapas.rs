//! La segunda y la tercera etapa (F4.1.6): `core/second_stage.py` y
//! `core/third_stage.py` de la V1, más iTunes (F4.1.5, `external/itunes_client.py`).
//!
//! Lo que quedó en revisión o en cuarentena recuperable tiene otra oportunidad,
//! siempre con una señal fuerte (el ISRC o la huella) y con distancia sobre el
//! segundo candidato: estas etapas son conservadoras a propósito. Son funciones
//! puras; la canalización hace las consultas y les pasa los candidatos.

use serde_json::Value;

use super::emparejador::{Contexto, UMBRAL_REVISAR};
use super::modelo::{CausaCuarentena, CausaRevision, Veredicto};
use super::musicbrainz::Candidato;
use super::texto::{limpiar_version_titulo, para_comparacion, redondear, similitud_combinada};

const MAX_CANDIDATOS_SEGUNDA: usize = 5;
const EVIDENCIA_MINIMA_SEGUNDA: f64 = 0.86;
const DISTANCIA_MINIMA_SEGUNDA: f64 = 0.12;
const EVIDENCIA_MINIMA_TERCERA: f64 = 0.90;
const DISTANCIA_MINIMA_TERCERA: f64 = 0.14;
const ACEPTADOS: [&str; 3] = ["Album", "Single", "EP"];

/// `_estrategia_para`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Estrategia {
    ConflictoVersion,
    AmbiguoSinIa,
    ScoreIntermedio,
    ConflictoAlias,
    ReleaseIncompleto,
    ConsistenciaEvidencias,
}

/// `_es_elegible` de la segunda etapa.
pub fn elegible_segunda(v: Veredicto) -> bool {
    match v {
        Veredicto::Revision(c) => matches!(
            c,
            CausaRevision::CandidatosAmbiguos
                | CausaRevision::PuntajeIntermedio
                | CausaRevision::FuentesDiscrepantes
        ),
        Veredicto::Cuarentena(c) => !matches!(
            c,
            CausaCuarentena::ArchivoCorrupto
                | CausaCuarentena::ArchivoIlegible
                | CausaCuarentena::ArchivoMuyPequeno
                | CausaCuarentena::DuracionInvalida
                | CausaCuarentena::BitrateInsuficiente
                | CausaCuarentena::MetadataInsuficiente
                | CausaCuarentena::SinCandidatos
                | CausaCuarentena::PuntajeBajo
                | CausaCuarentena::EscrituraFallida
                | CausaCuarentena::ValidacionPostEscritura
        ),
        _ => false,
    }
}

pub fn estrategia(v: Veredicto, titulo: &str, ia_activa: bool) -> Estrategia {
    let t = titulo.to_lowercase();
    if ["live", "remix", "remaster", "acoustic"]
        .iter()
        .any(|k| t.contains(k))
    {
        return Estrategia::ConflictoVersion;
    }
    match v {
        Veredicto::Revision(CausaRevision::CandidatosAmbiguos) if !ia_activa => {
            Estrategia::AmbiguoSinIa
        }
        Veredicto::Revision(CausaRevision::PuntajeIntermedio) => Estrategia::ScoreIntermedio,
        Veredicto::Revision(CausaRevision::FuentesDiscrepantes) => Estrategia::ConflictoAlias,
        Veredicto::Revision(CausaRevision::ClasificacionProvisional) => {
            Estrategia::ReleaseIncompleto
        }
        _ => Estrategia::ConsistenciaEvidencias,
    }
}

fn filtrar(candidatos: Vec<Candidato>, e: Estrategia, ctx: &Contexto<'_>) -> Vec<Candidato> {
    let n = ctx.norm;
    let filtrados: Vec<Candidato> = match e {
        Estrategia::ReleaseIncompleto => {
            let album = para_comparacion(&n.album);
            candidatos
                .iter()
                .filter(|c| !album.is_empty() && para_comparacion(&c.album) == album)
                .cloned()
                .collect()
        }
        Estrategia::ConflictoAlias => candidatos.iter().filter(|c| c.oficial).cloned().collect(),
        Estrategia::ConflictoVersion => {
            let base = para_comparacion(&limpiar_version_titulo(&n.titulo));
            candidatos
                .iter()
                .filter(|c| para_comparacion(&limpiar_version_titulo(&c.titulo)) == base)
                .cloned()
                .collect()
        }
        _ => return candidatos,
    };
    if filtrados.is_empty() {
        candidatos
    } else {
        filtrados
    }
}

fn isrc_archivo<'a>(ctx: &Contexto<'a>) -> Option<&'a str> {
    ctx.shazam
        .and_then(|s| s.isrc.as_deref())
        .or(ctx.norm.isrc.as_deref())
}

fn de_acoustid(ctx: &Contexto<'_>, c: &Candidato) -> bool {
    !c.mbid_grabacion.is_empty()
        && ctx
            .acoustid
            .is_some_and(|a| a.grabaciones.contains(&c.mbid_grabacion))
}

/// `_puntaje_evidencia`: título, artista, duración, ISRC y huella.
pub fn evidencia(ctx: &Contexto<'_>, c: &Candidato) -> f64 {
    let n = ctx.norm;
    let titulo = similitud_combinada(
        &para_comparacion(&limpiar_version_titulo(&n.titulo)),
        &para_comparacion(&limpiar_version_titulo(&c.titulo)),
    );
    let artista = similitud_combinada(&para_comparacion(&n.artista), &para_comparacion(&c.artista));
    let duracion = match (
        n.duracion_seg.filter(|d| *d != 0.0),
        c.duracion_seg.filter(|d| *d != 0.0),
    ) {
        (Some(a), Some(b)) => match (a - b).abs() {
            d if d <= 2.0 => 1.0,
            d if d <= 5.0 => 0.8,
            d if d <= 12.0 => 0.6,
            _ => 0.2,
        },
        _ => 0.5,
    };
    let isrc = match (isrc_archivo(ctx), c.isrc.as_deref()) {
        (Some(a), Some(b)) => f64::from(u8::from(a == b)),
        _ => 0.0,
    };
    let huella = f64::from(u8::from(ctx.acoustid.is_some() && de_acoustid(ctx, c)));
    redondear(
        titulo * 0.28 + artista * 0.26 + duracion * 0.18 + isrc * 0.18 + huella * 0.10,
        4,
    )
}

/// Un candidato que una etapa promueve: con qué puntuación y en qué estado.
#[derive(Debug, Clone, PartialEq)]
pub struct Promocion {
    pub candidato: Candidato,
    pub puntaje: f64,
    pub veredicto: Veredicto,
}

fn veredicto_promovido(c: &Candidato) -> Veredicto {
    if ACEPTADOS.contains(&c.tipo.as_str()) {
        Veredicto::Aceptado
    } else {
        Veredicto::Provisional(CausaRevision::ClasificacionProvisional)
    }
}

fn mejores(ctx: &Contexto<'_>, candidatos: Vec<Candidato>) -> Option<(Candidato, f64, f64)> {
    let mut a: Vec<(Candidato, f64)> = candidatos
        .into_iter()
        .map(|c| {
            let e = evidencia(ctx, &c);
            (c, e)
        })
        .collect();
    a.sort_by(|x, y| y.1.total_cmp(&x.1));
    let segundo = a.get(1).map_or(0.0, |x| x.1);
    let (mejor, e) = a.into_iter().next()?;
    Some((mejor, e, segundo))
}

/// `SegundaFaseResolucion._resolver`. `None` deja la decisión como estaba.
pub fn segunda(
    v: Veredicto,
    puntaje: f64,
    ctx: &Contexto<'_>,
    candidatos: Vec<Candidato>,
    ia_activa: bool,
) -> Option<Promocion> {
    if !elegible_segunda(v) {
        return None;
    }
    let e = estrategia(v, &ctx.norm.titulo, ia_activa);
    let candidatos = filtrar(
        candidatos
            .into_iter()
            .take(MAX_CANDIDATOS_SEGUNDA)
            .collect(),
        e,
        ctx,
    );
    let (mejor, ev, segundo) = mejores(ctx, candidatos)?;
    let distancia = ev - segundo;
    let base = f64::max(puntaje, mejor.puntaje);
    let nuevo = f64::min(1.0, base + (ev - 0.5) * 0.25);
    let senal = isrc_archivo(ctx).is_some_and(|i| mejor.isrc.as_deref() == Some(i))
        || de_acoustid(ctx, &mejor);
    let umbral = EVIDENCIA_MINIMA_SEGUNDA
        + match e {
            Estrategia::ScoreIntermedio => -0.03,
            Estrategia::ConflictoVersion => 0.04,
            Estrategia::ConflictoAlias => 0.02,
            _ => 0.0,
        };
    (ev >= umbral && distancia >= DISTANCIA_MINIMA_SEGUNDA && senal).then(|| Promocion {
        veredicto: veredicto_promovido(&mejor),
        puntaje: redondear(f64::max(nuevo, UMBRAL_REVISAR), 4),
        candidato: mejor,
    })
}

/// Lo que dice iTunes de una canción (`ItunesTrackHint`).
#[derive(Debug, Clone, Default, PartialEq)]
pub struct PistaItunes {
    pub artista: String,
    pub titulo: String,
    pub album: String,
    pub isrc: Option<String>,
    pub duracion_seg: Option<f64>,
}

/// La búsqueda de iTunes (`_build_url`), con la codificación de `urlencode`.
pub fn url_itunes(artista: &str, titulo: &str) -> String {
    let termino = format!("{artista} {titulo}");
    let mut t = String::new();
    for b in termino.trim().bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                t.push(b as char)
            }
            b' ' => t.push('+'),
            _ => t.push_str(&format!("%{b:02X}")),
        }
    }
    format!("https://itunes.apple.com/search?term={t}&entity=song&limit=5")
}

/// El primer resultado de una búsqueda (`buscar_hint`).
pub fn pista_itunes(respuesta: &Value) -> Option<PistaItunes> {
    let r = respuesta.get("results")?.as_array()?.first()?;
    let s = |k: &str| {
        r.get(k)
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned()
    };
    Some(PistaItunes {
        artista: s("artistName"),
        titulo: s("trackName"),
        album: s("collectionName"),
        isrc: r
            .get("isrc")
            .and_then(Value::as_str)
            .filter(|i| !i.is_empty())
            .map(str::to_owned),
        duracion_seg: r
            .get("trackTimeMillis")
            .and_then(Value::as_f64)
            .filter(|m| *m != 0.0)
            .map(|m| m / 1000.0),
    })
}

/// `_evidencia_itunes`.
pub fn evidencia_itunes(ctx: &Contexto<'_>, h: &PistaItunes) -> f64 {
    let n = ctx.norm;
    let titulo = similitud_combinada(
        &para_comparacion(&limpiar_version_titulo(&n.titulo)),
        &para_comparacion(&limpiar_version_titulo(&h.titulo)),
    );
    let artista = similitud_combinada(&para_comparacion(&n.artista), &para_comparacion(&h.artista));
    let duracion = match (n.duracion_seg.filter(|d| *d != 0.0), h.duracion_seg) {
        (Some(a), Some(b)) => match (a - b).abs() {
            d if d <= 3.0 => 1.0,
            d if d <= 8.0 => 0.8,
            _ => 0.35,
        },
        _ => 0.5,
    };
    let isrc = f64::from(u8::from(n.isrc.is_some() && n.isrc == h.isrc));
    redondear(
        titulo * 0.40 + artista * 0.35 + duracion * 0.15 + isrc * 0.10,
        4,
    )
}

pub fn elegible_tercera(v: Veredicto) -> bool {
    matches!(
        v,
        Veredicto::Revision(_)
            | Veredicto::Cuarentena(CausaCuarentena::SinCandidatos | CausaCuarentena::PuntajeBajo)
    )
}

/// Lo que hace la tercera etapa: promover, o al menos pasar de cuarentena a
/// revisión (`_degradar_si_aplica`, que en realidad mejora).
#[derive(Debug, Clone, PartialEq)]
pub enum Tercera {
    SinCambio,
    ARevision,
    Promovida(Box<Promocion>),
}

fn degradar(v: Veredicto) -> Tercera {
    if matches!(v, Veredicto::Cuarentena(_)) {
        Tercera::ARevision
    } else {
        Tercera::SinCambio
    }
}

/// `TerceraFaseResolucion._resolver`. Los candidatos son los de MusicBrainz
/// buscando otra vez con el ISRC que dio iTunes, si lo dio.
pub fn tercera(
    v: Veredicto,
    puntaje: f64,
    ctx: &Contexto<'_>,
    hint: Option<&PistaItunes>,
    candidatos: Vec<Candidato>,
) -> Tercera {
    let Some(h) = hint else {
        return Tercera::SinCambio;
    };
    let ev_hint = evidencia_itunes(ctx, h);
    if ev_hint < 0.75 {
        return degradar(v);
    }
    let candidatos: Vec<Candidato> = candidatos.into_iter().take(5).collect();
    let Some((mejor, mut ev, segundo)) = mejores(ctx, candidatos) else {
        return degradar(v);
    };
    let por_isrc = h.isrc.is_some() && h.isrc == mejor.isrc;
    if por_isrc {
        ev = f64::min(1.0, ev + 0.12);
    }
    let distancia = ev - segundo;
    let senal = por_isrc || de_acoustid(ctx, &mejor);
    if ev >= EVIDENCIA_MINIMA_TERCERA
        && distancia >= DISTANCIA_MINIMA_TERCERA
        && ev_hint >= 0.8
        && senal
    {
        return Tercera::Promovida(Box::new(Promocion {
            veredicto: veredicto_promovido(&mejor),
            puntaje: redondear(f64::max(puntaje, ev), 4),
            candidato: mejor,
        }));
    }
    degradar(v)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::catalogo::modelo::{DeAcoustid, Normalizada};

    fn norm() -> Normalizada {
        Normalizada {
            titulo: "Clavado en un bar".into(),
            artista: "Maná".into(),
            album: "Sueños líquidos".into(),
            duracion_seg: Some(300.0),
            isrc: Some("MXF019700001".into()),
            ..Normalizada::default()
        }
    }

    fn cand(id: &str, titulo: &str, isrc: Option<&str>, tipo: &str) -> Candidato {
        Candidato {
            mbid_grabacion: id.into(),
            titulo: titulo.into(),
            artista: "Maná".into(),
            album: "Sueños líquidos".into(),
            duracion_seg: Some(301.0),
            isrc: isrc.map(str::to_owned),
            tipo: tipo.into(),
            oficial: true,
            ..Candidato::default()
        }
    }

    #[test]
    fn la_segunda_etapa_promueve_con_isrc_y_distancia() {
        let n = norm();
        let ctx = Contexto {
            norm: &n,
            shazam: None,
            acoustid: None,
        };
        let p = segunda(
            Veredicto::Revision(CausaRevision::PuntajeIntermedio),
            0.7,
            &ctx,
            vec![
                cand("a", "Clavado en un bar", Some("MXF019700001"), "Album"),
                cand("b", "Otra", None, "Album"),
            ],
            false,
        )
        .unwrap();
        assert_eq!(p.candidato.mbid_grabacion, "a");
        assert_eq!(p.veredicto, Veredicto::Aceptado);
        assert_eq!(evidencia(&ctx, &p.candidato), 0.9);
        assert_eq!(p.puntaje, 0.8);
    }

    #[test]
    fn sin_senal_fuerte_no_promueve() {
        let mut n = norm();
        n.isrc = None;
        let ctx = Contexto {
            norm: &n,
            shazam: None,
            acoustid: None,
        };
        assert!(segunda(
            Veredicto::Revision(CausaRevision::PuntajeIntermedio),
            0.7,
            &ctx,
            vec![cand("a", "Clavado en un bar", Some("X"), "Album")],
            false
        )
        .is_none());
        let a = DeAcoustid {
            grabaciones: vec!["a".into()],
            confianzas: vec![0.9],
        };
        let ctx = Contexto {
            norm: &n,
            shazam: None,
            acoustid: Some(&a),
        };
        let p = segunda(
            Veredicto::Revision(CausaRevision::PuntajeIntermedio),
            0.7,
            &ctx,
            vec![cand("a", "Clavado en un bar", None, "")],
            false,
        );
        assert!(p.is_none(), "0,82 de evidencia no llega al umbral de 0,83");
    }

    #[test]
    fn la_cuarentena_por_archivo_no_tiene_segunda_oportunidad() {
        assert!(!elegible_segunda(Veredicto::Cuarentena(
            CausaCuarentena::ArchivoCorrupto
        )));
        assert!(elegible_segunda(Veredicto::Cuarentena(
            CausaCuarentena::OwnershipInvalido
        )));
        assert!(!elegible_segunda(Veredicto::Revision(
            CausaRevision::DuracionMarginal
        )));
        assert!(elegible_tercera(Veredicto::Cuarentena(
            CausaCuarentena::PuntajeBajo
        )));
        assert!(!elegible_tercera(Veredicto::Cuarentena(
            CausaCuarentena::ArchivoCorrupto
        )));
    }

    #[test]
    fn la_estrategia_sale_del_titulo_y_de_la_causa() {
        let r = |c| Veredicto::Revision(c);
        assert_eq!(
            estrategia(r(CausaRevision::PuntajeIntermedio), "Song (Live)", false),
            Estrategia::ConflictoVersion
        );
        assert_eq!(
            estrategia(r(CausaRevision::CandidatosAmbiguos), "Song", false),
            Estrategia::AmbiguoSinIa
        );
        assert_eq!(
            estrategia(r(CausaRevision::CandidatosAmbiguos), "Song", true),
            Estrategia::ConsistenciaEvidencias
        );
    }

    #[test]
    fn itunes_corrobora_o_al_menos_saca_de_cuarentena() {
        let n = norm();
        let ctx = Contexto {
            norm: &n,
            shazam: None,
            acoustid: None,
        };
        let r = serde_json::json!({"results": [{"artistName": "Maná", "trackName": "Clavado en un bar",
            "collectionName": "Sueños líquidos", "isrc": "MXF019700001", "trackTimeMillis": 300_500}]});
        let h = pista_itunes(&r).unwrap();
        assert_eq!(h.duracion_seg, Some(300.5));
        assert_eq!(evidencia_itunes(&ctx, &h), 1.0);
        let v = Veredicto::Cuarentena(CausaCuarentena::PuntajeBajo);
        match tercera(
            v,
            0.4,
            &ctx,
            Some(&h),
            vec![cand(
                "a",
                "Clavado en un bar",
                Some("MXF019700001"),
                "Single",
            )],
        ) {
            Tercera::Promovida(p) => assert_eq!(p.puntaje, 1.0),
            otro => panic!("{otro:?}"),
        }
        let flojo = PistaItunes {
            titulo: "Otra".into(),
            artista: "Otro".into(),
            ..PistaItunes::default()
        };
        assert_eq!(
            tercera(v, 0.4, &ctx, Some(&flojo), vec![]),
            Tercera::ARevision
        );
        assert_eq!(tercera(v, 0.4, &ctx, None, vec![]), Tercera::SinCambio);
        assert!(pista_itunes(&serde_json::json!({"results": []})).is_none());
    }

    #[test]
    fn la_url_de_itunes_es_la_de_urlencode() {
        assert_eq!(
            url_itunes("Maná", "Clavado en un bar"),
            "https://itunes.apple.com/search?term=Man%C3%A1+Clavado+en+un+bar&entity=song&limit=5"
        );
    }
}
