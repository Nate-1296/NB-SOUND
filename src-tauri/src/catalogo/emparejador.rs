//! Puntuar a los candidatos y decidir (F4.1.6, primera etapa): `core/matcher.py`
//! de la V1, con sus pesos, penalizaciones, bonos y umbrales.
//!
//! El desempate por IA (F4.1.7) entra por [`Desempate`]: sin él, una ambigüedad
//! queda en revisión, como en la V1 sin clave de IA.

use super::modelo::{CausaCuarentena, CausaRevision, DeAcoustid, DeShazam, Normalizada, Veredicto};
use super::musicbrainz::{Candidato, MAX_CANDIDATOS};
use super::texto::{
    detectar_tipo_variante, limpiar_version_titulo, normalizar_artista, normalizar_titulo,
    para_comparacion, redondear, similitud_combinada,
};

/// `SCORE_WEIGHTS`, en el orden en que la V1 los suma.
const PESOS: [(Criterio, f64); 7] = [
    (Criterio::Titulo, 0.28),
    (Criterio::Artista, 0.23),
    (Criterio::Duracion, 0.18),
    (Criterio::Album, 0.10),
    (Criterio::Numero, 0.07),
    (Criterio::Tipo, 0.07),
    (Criterio::Isrc, 0.07),
];
pub const UMBRAL_ACEPTAR: f64 = 0.82;
pub const UMBRAL_REVISAR: f64 = 0.55;
const PENALIZACION_RECOPILATORIO: f64 = 0.25;
const PENALIZACION_VIVO_REMIX: f64 = 0.20;
const PENALIZACION_AMBIGUEDAD: f64 = 0.15;
const DISTANCIA_MINIMA: f64 = 0.10;
const BONO_ANIO: f64 = 0.04;
const BONO_ISRC: f64 = 0.22;
/// `IA_TIEBREAK_MIN_GAP`.
pub const DISTANCIA_PARA_IA: f64 = 0.12;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Criterio {
    Titulo,
    Artista,
    Duracion,
    Album,
    Numero,
    Tipo,
    Isrc,
}

/// Los puntos de cada criterio de un candidato (`puntaje_detalle`).
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct Detalle {
    pub titulo: f64,
    pub artista: f64,
    pub duracion: f64,
    pub album: f64,
    pub numero: f64,
    pub tipo: f64,
    pub isrc: f64,
}

impl Detalle {
    fn de(&self, c: Criterio) -> f64 {
        match c {
            Criterio::Titulo => self.titulo,
            Criterio::Artista => self.artista,
            Criterio::Duracion => self.duracion,
            Criterio::Album => self.album,
            Criterio::Numero => self.numero,
            Criterio::Tipo => self.tipo,
            Criterio::Isrc => self.isrc,
        }
    }

    fn escalar(&mut self, f: f64) {
        for v in [
            &mut self.titulo,
            &mut self.artista,
            &mut self.duracion,
            &mut self.album,
            &mut self.numero,
            &mut self.tipo,
            &mut self.isrc,
        ] {
            *v *= f;
        }
    }
}

/// Un candidato con sus puntos.
#[derive(Debug, Clone, PartialEq)]
pub struct Puntuado {
    pub candidato: Candidato,
    pub detalle: Detalle,
}

/// Lo que entra al emparejador además de los candidatos.
#[derive(Debug, Clone, Copy)]
pub struct Contexto<'a> {
    pub norm: &'a Normalizada,
    pub shazam: Option<&'a DeShazam>,
    pub acoustid: Option<&'a DeAcoustid>,
}

impl Contexto<'_> {
    /// `isrc_disponible`: el de Shazam y, si no, el de la normalización.
    fn isrc(&self) -> Option<&str> {
        self.shazam
            .and_then(|s| s.isrc.as_deref())
            .or(self.norm.isrc.as_deref())
    }
}

/// El desempate por IA: el lanzamiento que elige, o `None` para pedir revisión.
pub trait Desempate {
    fn desempatar(&self, ctx: &Contexto<'_>, candidatos: &[Puntuado]) -> Option<DecisionIa>;
}

#[derive(Debug, Clone, PartialEq)]
pub enum DecisionIa {
    Lanzamiento { id: String, confianza: f64 },
    RevisionManual,
}

/// La decisión: el veredicto, el candidato elegido y su puntuación final.
#[derive(Debug, Clone, PartialEq)]
pub struct Decision {
    pub veredicto: Veredicto,
    pub elegido: Option<Puntuado>,
    pub puntaje: f64,
    pub por_ia: bool,
}

pub fn puntuar_duracion(local: Option<f64>, candidato: Option<f64>) -> f64 {
    let (Some(l), Some(c)) = (local, candidato) else {
        return 0.5;
    };
    let d = (l - c).abs();
    if d <= 3.0 {
        1.0
    } else if d <= 10.0 {
        redondear(1.0 - 0.5 * ((d - 3.0) / 7.0), 4)
    } else if d <= 30.0 {
        redondear(f64::max(0.05, 0.5 - 0.45 * ((d - 10.0) / 20.0)), 4)
    } else {
        0.0
    }
}

pub fn puntuar_numero(local: Option<u32>, candidato: Option<u32>) -> f64 {
    match (local, candidato) {
        (Some(l), Some(c)) if l == c => 1.0,
        (Some(l), Some(c)) if l.abs_diff(c) == 1 => 0.4,
        (Some(_), Some(_)) => 0.0,
        _ => 0.5,
    }
}

const ACEPTADOS: [&str; 3] = ["Album", "Single", "EP"];
const PENALIZADOS: [&str; 10] = [
    "Compilation",
    "Live",
    "Remix",
    "DJ-mix",
    "Mixtape/Street",
    "Soundtrack",
    "Broadcast",
    "Audiobook",
    "Interview",
    "Spoken Word",
];

fn puntuar_tipo(c: &Candidato, variante: Option<&str>) -> (f64, Option<String>) {
    let coincide = variante.is_some_and(|v| v == c.tipo || c.secundarios.iter().any(|s| s == v));
    if ACEPTADOS.contains(&c.tipo.as_str()) {
        (1.0, None)
    } else if PENALIZADOS.contains(&c.tipo.as_str()) {
        if coincide {
            (0.65, Some(format!("tipo_penalizado_tolerado:{}", c.tipo)))
        } else {
            (0.2, Some(format!("tipo_penalizado:{}", c.tipo)))
        }
    } else if c.tipo.is_empty() {
        (0.4, None)
    } else {
        (0.5, None)
    }
}

/// `sum()` de CPython 3.12 para reales: suma de Neumaier.
fn suma_python(valores: impl Iterator<Item = f64>) -> f64 {
    let (mut s, mut c) = (0.0f64, 0.0f64);
    for x in valores {
        let t = s + x;
        if s.abs() >= x.abs() {
            c += (s - t) + x;
        } else {
            c += (x - t) + s;
        }
        s = t;
    }
    s + c
}

/// `_puntuar_candidato`: los criterios ponderados, y después penalizaciones y bonos.
pub fn puntuar(c: &mut Candidato, ctx: &Contexto<'_>) -> Detalle {
    let n = ctx.norm;
    let isrc_archivo = ctx.isrc();
    // La V1 empezaba cada puntuación con la lista vacía y la sustituía al final:
    // las marcas `tipo_secundario:` que puso el cliente de MusicBrainz no llegaban
    // nunca aquí, y la penalización por vivo o remix no se aplicaba. Se conserva
    // así hasta medir la paridad global (el tipo penalizado sí cuenta, por
    // `puntuar_tipo`).
    c.penalizaciones.clear();
    let mut d = Detalle {
        isrc: match (isrc_archivo, c.isrc.as_deref()) {
            (Some(a), Some(b)) if a == b => 1.0,
            (Some(_), Some(_)) => 0.1,
            (Some(_), None) => 0.4,
            _ => 0.5,
        },
        ..Detalle::default()
    };
    let variante = detectar_tipo_variante(&n.titulo);
    let mut titulo = similitud_combinada(
        &limpiar_version_titulo(&n.titulo_para_match),
        &para_comparacion(&limpiar_version_titulo(&c.titulo)),
    );
    if titulo < 0.7 {
        let completo = similitud_combinada(&n.titulo_para_match, &para_comparacion(&c.titulo));
        titulo = f64::max(titulo, completo * 0.95);
    }
    d.titulo = redondear(titulo, 4);
    let mut artista = similitud_combinada(&n.artista_para_match, &para_comparacion(&c.artista));
    if artista < 0.9 && !n.artista_para_match.is_empty() {
        for credito in &c.artistas {
            let b = similitud_combinada(&n.artista_para_match, &para_comparacion(credito));
            if b > artista {
                artista = f64::min(b, 0.82);
            }
        }
    }
    d.artista = redondear(artista, 4);
    d.duracion = puntuar_duracion(n.duracion_seg, c.duracion_seg);
    d.album = if !n.album_para_match.is_empty() && !c.album.is_empty() {
        redondear(
            similitud_combinada(
                &limpiar_version_titulo(&n.album_para_match),
                &para_comparacion(&limpiar_version_titulo(&c.album)),
            ),
            4,
        )
    } else if n.album_para_match.is_empty() {
        0.5
    } else {
        0.2
    };
    d.numero = puntuar_numero(n.numero, c.numero);
    let (tipo, pen_tipo) = puntuar_tipo(c, variante);
    d.tipo = tipo;
    c.penalizaciones.extend(pen_tipo);
    if !c.oficial && !c.estado.is_empty() {
        c.penalizaciones
            .push(format!("release_no_oficial:{}", c.estado));
        d.escalar(if c.estado == "Promotion" { 0.90 } else { 0.80 });
    }
    if c.recopilatorio {
        c.penalizaciones.push("compilacion".into());
    }
    // Como `sum()` de Python 3.12, que suma los reales con compensación (Neumaier):
    // con la suma directa, un 0,55 justo en el umbral sale 0,5499… y la decisión
    // cambia.
    let mut p = suma_python(PESOS.iter().map(|(k, w)| d.de(*k) * w));
    if c.penalizaciones.iter().any(|x| x == "compilacion") {
        p -= PENALIZACION_RECOPILATORIO;
    }
    let secundarios: Vec<String> = c
        .penalizaciones
        .iter()
        .filter_map(|x| x.strip_prefix("tipo_secundario:").map(str::to_owned))
        .collect();
    if !secundarios.is_empty() {
        match variante.filter(|v| secundarios.iter().any(|s| s == v)) {
            Some(v) => {
                p -= PENALIZACION_VIVO_REMIX * 0.30;
                c.penalizaciones.push(format!("variante_coincide:{v}"));
            }
            None => p -= PENALIZACION_VIVO_REMIX,
        }
    }
    if let (Some(a), Some(b)) = (n.anio, c.anio) {
        if a == b {
            p += BONO_ANIO;
            c.penalizaciones.push(format!("bonus_anio:{a}"));
        } else if (a - b).abs() <= 1 {
            p += BONO_ANIO * 0.5;
        }
    }
    if let (Some(a), Some(b)) = (isrc_archivo, c.isrc.as_deref()) {
        if a == b {
            p += BONO_ISRC;
            c.penalizaciones.push(format!("bonus_isrc_exacto:{a}"));
        }
    }
    if c.de_acoustid {
        p += 0.08;
        c.penalizaciones.push("bonus_acoustid".into());
    }
    if n.confianza > 0.7 {
        p += 0.03;
    } else if n.confianza > 0.5 {
        p += 0.01;
    }
    c.puntaje = p.clamp(0.0, 1.0);
    d
}

/// `_aplicar_bonus_validacion_cruzada`: Shazam confirma lo local.
fn validacion_cruzada(ctx: &Contexto<'_>, mejor: &mut Candidato) {
    let Some(s) = ctx.shazam.filter(|s| s.identificado) else {
        return;
    };
    let st = para_comparacion(&normalizar_titulo(&s.titulo));
    let sa = para_comparacion(&normalizar_artista(&s.artista));
    let n = ctx.norm;
    let titulo = !st.is_empty()
        && !n.titulo_para_match.is_empty()
        && similitud_combinada(&n.titulo_para_match, &st) >= 0.75;
    let artista = !sa.is_empty()
        && !n.artista_para_match.is_empty()
        && similitud_combinada(&n.artista_para_match, &sa) >= 0.70;
    let bono = match (titulo, artista) {
        (true, true) => 0.06,
        (true, false) | (false, true) => 0.03,
        (false, false) => return,
    };
    mejor.puntaje = f64::min(1.0, mejor.puntaje + bono);
    mejor
        .penalizaciones
        .push(format!("bonus_validacion_cruzada:{bono:.2}"));
}

fn identidad_solida(ctx: &Contexto<'_>, p: &Puntuado) -> bool {
    let (t, a) = (p.detalle.titulo, p.detalle.artista);
    if t < 0.75 || a < 0.65 {
        return false;
    }
    let shazam = ctx.shazam.is_some_and(|s| s.identificado);
    shazam || ctx.isrc().is_some() || (t >= 0.90 && a >= 0.85)
}

fn causa_revision(p: &Puntuado, variante: Option<&str>) -> CausaRevision {
    if p.candidato
        .penalizaciones
        .iter()
        .any(|x| x == "ambiguedad_entre_candidatos")
    {
        CausaRevision::CandidatosAmbiguos
    } else if !ACEPTADOS.contains(&p.candidato.tipo.as_str()) && variante.is_none() {
        CausaRevision::ReleaseTypeDudoso
    } else if p.detalle.duracion < 0.3 {
        CausaRevision::DuracionMarginal
    } else {
        CausaRevision::PuntajeIntermedio
    }
}

fn causa_cuarentena(p: &Puntuado) -> CausaCuarentena {
    if !p.candidato.oficial {
        CausaCuarentena::OwnershipInvalido
    } else if p.detalle.titulo < 0.3 {
        CausaCuarentena::MetadataInsuficiente
    } else {
        CausaCuarentena::PuntajeBajo
    }
}

/// `_aplicar_umbrales`.
fn umbrales(ctx: &Contexto<'_>, mejor: &Puntuado, puntaje: f64) -> Veredicto {
    let c = &mejor.candidato;
    let variante = detectar_tipo_variante(&ctx.norm.titulo);
    let variante_coincide =
        variante.is_some_and(|v| v == c.tipo || c.secundarios.iter().any(|s| s == v));
    let solida = identidad_solida(ctx, mejor);
    let ambiguo = c
        .penalizaciones
        .iter()
        .any(|x| x == "ambiguedad_entre_candidatos");
    let d = &mejor.detalle;
    if puntaje >= UMBRAL_ACEPTAR {
        if solida && c.tipo.is_empty() && c.album.is_empty() {
            return Veredicto::Provisional(CausaRevision::ClasificacionProvisional);
        }
        return Veredicto::Aceptado;
    }
    let umbral_provisional = UMBRAL_ACEPTAR - 0.10;
    if puntaje >= UMBRAL_REVISAR {
        let por_duracion = d.duracion < 0.35
            && d.titulo >= 0.75
            && d.artista >= 0.70
            && solida
            && puntaje >= umbral_provisional
            && !ambiguo;
        let por_variante = !por_duracion
            && variante_coincide
            && solida
            && puntaje >= umbral_provisional
            && d.titulo >= 0.70
            && d.artista >= 0.65
            && !ambiguo;
        if por_duracion {
            return Veredicto::Provisional(CausaRevision::DuracionMarginal);
        }
        if por_variante {
            return Veredicto::Provisional(CausaRevision::ClasificacionProvisional);
        }
        return Veredicto::Revision(causa_revision(mejor, variante));
    }
    if variante_coincide && solida && puntaje >= UMBRAL_REVISAR * 0.80 && d.titulo >= 0.65 {
        return Veredicto::Revision(causa_revision(mejor, variante));
    }
    Veredicto::Cuarentena(causa_cuarentena(mejor))
}

/// `evaluar_candidatos`: puntúa, aplica la validación cruzada y la penalización
/// por ambigüedad, consulta a la IA si hay empate y aplica los umbrales.
pub fn evaluar(
    candidatos: Vec<Candidato>,
    ctx: &Contexto<'_>,
    ia: Option<&dyn Desempate>,
) -> Decision {
    if candidatos.is_empty() {
        return Decision {
            veredicto: Veredicto::Cuarentena(CausaCuarentena::SinCandidatos),
            elegido: None,
            puntaje: 0.0,
            por_ia: false,
        };
    }
    let mut ps: Vec<Puntuado> = candidatos
        .into_iter()
        .take(MAX_CANDIDATOS)
        .map(|mut c| {
            let detalle = puntuar(&mut c, ctx);
            Puntuado {
                candidato: c,
                detalle,
            }
        })
        .collect();
    // Orden estable de mayor a menor, como `sort(reverse=True)` de Python.
    let ordenar = |ps: &mut Vec<Puntuado>| {
        ps.sort_by(|a, b| b.candidato.puntaje.total_cmp(&a.candidato.puntaje));
    };
    ordenar(&mut ps);
    validacion_cruzada(ctx, &mut ps[0].candidato);
    ordenar(&mut ps);
    let distancia = ps[0].candidato.puntaje - ps.get(1).map_or(0.0, |s| s.candidato.puntaje);
    let ambiguo = ps.len() > 1 && distancia < DISTANCIA_MINIMA;
    if ambiguo {
        let m = &mut ps[0].candidato;
        let antes = m.puntaje;
        m.puntaje -= PENALIZACION_AMBIGUEDAD;
        m.penalizaciones.push("ambiguedad_entre_candidatos".into());
        if antes >= UMBRAL_REVISAR {
            m.puntaje = f64::max(m.puntaje, UMBRAL_REVISAR);
        }
    }
    let mut mejor = ps[0].clone();
    let mut puntaje = f64::max(0.0, mejor.candidato.puntaje);
    let mut por_ia = false;
    if ambiguo && distancia < DISTANCIA_PARA_IA {
        match ia.and_then(|ia| ia.desempatar(ctx, &ps)) {
            Some(DecisionIa::Lanzamiento { id, confianza }) => {
                if let Some(e) = ps.iter().find(|p| p.candidato.mbid_lanzamiento == id) {
                    mejor = e.clone();
                    puntaje = f64::max(UMBRAL_ACEPTAR, confianza);
                    por_ia = true;
                }
            }
            Some(DecisionIa::RevisionManual) => {
                return Decision {
                    veredicto: Veredicto::Revision(CausaRevision::IaRevisionManual),
                    elegido: Some(mejor),
                    puntaje,
                    por_ia: false,
                };
            }
            None => {}
        }
    }
    Decision {
        veredicto: umbrales(ctx, &mejor, puntaje),
        elegido: Some(mejor),
        puntaje,
        por_ia,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::catalogo::etiquetas::Cruda;
    use crate::catalogo::normalizacion::normalizar;

    fn norm(titulo: &str, artista: &str, album: &str, duracion: f64) -> Normalizada {
        normalizar(
            &Cruda {
                titulo: Some(titulo.into()),
                artista: Some(artista.into()),
                album: Some(album.into()).filter(|a: &String| !a.is_empty()),
                numero: Some("3".into()),
                anio: Some("1997".into()),
                ..Cruda::default()
            },
            duracion,
            "x.mp3",
            None,
            None,
        )
        .unwrap()
    }

    fn cand(id: &str, titulo: &str, artista: &str, album: &str, tipo: &str) -> Candidato {
        Candidato {
            mbid_grabacion: id.into(),
            mbid_lanzamiento: format!("l-{id}"),
            titulo: titulo.into(),
            artista: artista.into(),
            artistas: vec![artista.into()],
            album: album.into(),
            numero: Some(3),
            anio: Some(1997),
            duracion_seg: Some(300.0),
            tipo: tipo.into(),
            estado: "Official".into(),
            oficial: true,
            ..Candidato::default()
        }
    }

    #[test]
    fn la_duracion_y_el_numero_puntuan_como_en_la_v1() {
        assert_eq!(puntuar_duracion(Some(200.0), Some(202.5)), 1.0);
        assert_eq!(puntuar_duracion(Some(200.0), Some(206.5)), 0.75);
        assert_eq!(puntuar_duracion(Some(200.0), Some(220.0)), 0.275);
        assert_eq!(puntuar_duracion(Some(200.0), Some(250.0)), 0.0);
        assert_eq!(puntuar_duracion(None, Some(250.0)), 0.5);
        assert_eq!(
            (
                puntuar_numero(Some(3), Some(3)),
                puntuar_numero(Some(3), Some(4)),
                puntuar_numero(None, Some(1))
            ),
            (1.0, 0.4, 0.5)
        );
    }

    #[test]
    fn una_coincidencia_clara_se_acepta() {
        let n = norm("Clavado en un bar", "Maná", "Sueños líquidos", 300.0);
        let ctx = Contexto {
            norm: &n,
            shazam: None,
            acoustid: None,
        };
        let d = evaluar(
            vec![
                cand("a", "Clavado en un bar", "Maná", "Sueños líquidos", "Album"),
                cand("b", "Otra canción", "Maná", "Otro disco", "Album"),
            ],
            &ctx,
            None,
        );
        assert_eq!(d.veredicto, Veredicto::Aceptado);
        assert_eq!(d.elegido.unwrap().candidato.mbid_grabacion, "a");
        assert!(d.puntaje >= UMBRAL_ACEPTAR, "{}", d.puntaje);
    }

    #[test]
    fn dos_candidatos_casi_iguales_quedan_en_revision_por_ambiguedad() {
        let n = norm("Clavado en un bar", "Maná", "", 300.0);
        let ctx = Contexto {
            norm: &n,
            shazam: None,
            acoustid: None,
        };
        let d = evaluar(
            vec![
                cand("a", "Clavado en un bar", "Maná", "Sueños líquidos", "Album"),
                cand("b", "Clavado en un bar", "Maná", "Sueños líquidos", "Album"),
            ],
            &ctx,
            None,
        );
        assert_eq!(
            d.veredicto,
            Veredicto::Revision(CausaRevision::CandidatosAmbiguos)
        );
        // 0,955 menos la penalización de 0,15: no llega a aceptarse sola.
        assert!((d.puntaje - 0.805).abs() < 1e-9, "{}", d.puntaje);
    }

    #[test]
    fn la_ia_desempata_cuando_puede() {
        struct Elige;
        impl Desempate for Elige {
            fn desempatar(&self, _: &Contexto<'_>, _: &[Puntuado]) -> Option<DecisionIa> {
                Some(DecisionIa::Lanzamiento {
                    id: "l-b".into(),
                    confianza: 0.9,
                })
            }
        }
        let n = norm("Clavado en un bar", "Maná", "", 300.0);
        let ctx = Contexto {
            norm: &n,
            shazam: None,
            acoustid: None,
        };
        let d = evaluar(
            vec![
                cand("a", "Clavado en un bar", "Maná", "Sueños líquidos", "Album"),
                cand("b", "Clavado en un bar", "Maná", "Sueños líquidos", "Album"),
            ],
            &ctx,
            Some(&Elige),
        );
        assert!(d.por_ia);
        assert_eq!(d.elegido.unwrap().candidato.mbid_grabacion, "b");
        assert_eq!(d.veredicto, Veredicto::Aceptado);
    }

    #[test]
    fn un_recopilatorio_en_vivo_cae_a_cuarentena_o_revision() {
        let n = norm("Clavado en un bar", "Maná", "Sueños líquidos", 300.0);
        let ctx = Contexto {
            norm: &n,
            shazam: None,
            acoustid: None,
        };
        let mut c = cand("a", "Clavado en un bar", "Maná", "MTV Unplugged", "Album");
        c.recopilatorio = true;
        c.secundarios = vec!["Compilation".into(), "Live".into()];
        c.penalizaciones = vec![
            "tipo_secundario:Compilation".into(),
            "tipo_secundario:Live".into(),
        ];
        let d = evaluar(vec![c], &ctx, None);
        assert!(!d.veredicto.entra(), "{d:?}");
    }

    #[test]
    fn sin_candidatos_es_cuarentena() {
        let n = norm("x", "y", "", 100.0);
        let ctx = Contexto {
            norm: &n,
            shazam: None,
            acoustid: None,
        };
        assert_eq!(
            evaluar(vec![], &ctx, None).veredicto,
            Veredicto::Cuarentena(CausaCuarentena::SinCandidatos)
        );
    }

    fn veredicto_v1(v: Veredicto) -> (&'static str, Option<String>) {
        let texto = |x: &dyn erased_serialize::A| x.texto();
        match v {
            Veredicto::Aceptado => ("aceptado", None),
            Veredicto::Provisional(c) => ("aceptado_provisional", Some(texto(&c))),
            Veredicto::Revision(c) => ("revision", Some(texto(&c))),
            Veredicto::Cuarentena(c) => ("cuarentena", Some(texto(&c))),
        }
    }

    mod erased_serialize {
        pub trait A {
            fn texto(&self) -> String;
        }
        impl<T: serde::Serialize> A for T {
            fn texto(&self) -> String {
                serde_json::to_value(self)
                    .unwrap()
                    .as_str()
                    .unwrap()
                    .to_owned()
            }
        }
    }

    /// Lo que decidió la V1 en los casos de `scripts/prototipos/emparejador/grabar.py`.
    #[test]
    fn la_normalizacion_y_la_decision_son_las_de_la_v1() {
        use crate::catalogo::modelo::Fuente;
        let v1: serde_json::Value =
            serde_json::from_str(include_str!("../../tests/fixtures/emparejador_v1.json")).unwrap();
        let txt = |v: &serde_json::Value| v.as_str().map(str::to_owned);
        let mut fallos = Vec::new();
        for (k, c) in v1["casos"].as_array().unwrap().iter().enumerate() {
            let cr = &c["cruda"];
            let cruda = Cruda {
                titulo: txt(&cr["titulo"]),
                artista: txt(&cr["artista"]),
                album: txt(&cr["album"]),
                numero: txt(&cr["numero"]),
                anio: txt(&cr["anio"]),
                ..Cruda::default()
            };
            let shazam = c["shazam"].as_object().map(|s| DeShazam {
                identificado: true,
                titulo: s["titulo"].as_str().unwrap_or_default().into(),
                artista: s["artista"].as_str().unwrap_or_default().into(),
                isrc: txt(&s["isrc"]),
                album: txt(&s["album"]),
                anio: s["anio"].as_i64().map(|a| a as i32),
            });
            let acoustid = c["acoustid"].as_object().map(|a| DeAcoustid {
                grabaciones: a["grabaciones"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .filter_map(txt)
                    .collect(),
                confianzas: a["confianzas"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .filter_map(|x| x.as_f64())
                    .collect(),
            });
            let esperado = &c["v1"];
            let r = normalizar(
                &cruda,
                c["duracion"].as_f64().unwrap(),
                c["nombre"].as_str().unwrap(),
                shazam.as_ref(),
                acoustid.as_ref(),
            );
            let Ok(n) = r else {
                if esperado["ok"].as_bool() != Some(false) {
                    fallos.push(format!("caso {k}: la V2 no normaliza y la V1 sí"));
                }
                continue;
            };
            if esperado["ok"].as_bool() != Some(true) {
                fallos.push(format!("caso {k}: la V2 normaliza y la V1 no"));
                continue;
            }
            let en = &esperado["normalizada"];
            let fuente = |f: Fuente| serde_json::to_value(f).unwrap();
            let nuestra = serde_json::json!({
                "titulo": n.titulo, "titulo_para_match": n.titulo_para_match, "artista": n.artista,
                "artista_para_match": n.artista_para_match, "featuring": n.featuring, "album": n.album,
                "numero": n.numero, "anio": n.anio, "isrc": n.isrc,
                "confianza": redondear(n.confianza, 6),
                "fuente_titulo": fuente(n.fuente_titulo), "fuente_artista": fuente(n.fuente_artista),
            });
            if *en != nuestra {
                fallos.push(format!("caso {k}: normalizada\n  V1 {en}\n  V2 {nuestra}"));
                continue;
            }
            let candidatos: Vec<Candidato> = c["candidatos"]
                .as_array()
                .unwrap()
                .iter()
                .map(|d| Candidato {
                    mbid_grabacion: d["recording_id"].as_str().unwrap().into(),
                    mbid_lanzamiento: d["release_id"].as_str().unwrap().into(),
                    titulo: d["titulo_oficial"].as_str().unwrap().into(),
                    artista: d["artista_principal"].as_str().unwrap().into(),
                    artistas: d["artistas_credito"]
                        .as_array()
                        .unwrap()
                        .iter()
                        .filter_map(txt)
                        .collect(),
                    album: d["album_oficial"].as_str().unwrap().into(),
                    numero: d["track_number"].as_u64().map(|x| x as u32),
                    anio: d["anio_release"].as_i64().map(|x| x as i32),
                    duracion_seg: d["duracion_seg"].as_f64(),
                    isrc: txt(&d["isrc"]),
                    tipo: d["tipo_release"].as_str().unwrap().into(),
                    secundarios: d["tipos_secundarios"]
                        .as_array()
                        .unwrap()
                        .iter()
                        .filter_map(txt)
                        .collect(),
                    estado: d["status_release"].as_str().unwrap().into(),
                    oficial: d["es_oficial"].as_bool().unwrap(),
                    recopilatorio: d["es_compilacion"].as_bool().unwrap(),
                    penalizaciones: d["penalizaciones"]
                        .as_array()
                        .unwrap()
                        .iter()
                        .filter_map(txt)
                        .collect(),
                    de_acoustid: d["procedencia_acoustid"].as_bool().unwrap(),
                    ..Candidato::default()
                })
                .collect();
            let ctx = Contexto {
                norm: &n,
                shazam: shazam.as_ref(),
                acoustid: acoustid.as_ref(),
            };
            let d = evaluar(candidatos, &ctx, None);
            let (tipo, causa) = veredicto_v1(d.veredicto);
            let nuestra = serde_json::json!({
                "tipo": tipo, "causa": causa, "puntaje": redondear(d.puntaje, 6),
                "elegido": d.elegido.map(|e| e.candidato.mbid_grabacion),
            });
            if esperado["decision"] != nuestra {
                fallos.push(format!(
                    "caso {k}: decisión\n  V1 {}\n  V2 {nuestra}",
                    esperado["decision"]
                ));
            }
        }
        assert!(
            fallos.is_empty(),
            "{} diferencias:\n{}",
            fallos.len(),
            fallos.join("\n")
        );
    }
}
