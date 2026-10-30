//! El desempate por IA (F4.1.7): `external/ia_client.py` de la V1.
//!
//! Entra solo cuando el emparejador no puede decidir entre los dos mejores
//! candidatos ([`super::emparejador::DISTANCIA_PARA_IA`]). El modelo no crea
//! nada: elige uno de los candidatos que se le dan o pide revisión, y una
//! respuesta que nombra un lanzamiento que no estaba en la lista se descarta
//! entera. Se le mandan los metadatos de los candidatos y del archivo, nunca el
//! audio (ADR-009). Sin consentimiento o sin clave no se construye el cliente y
//! la ambigüedad queda en revisión, como en la V1 sin IA.

use serde_json::{json, Value};

use super::emparejador::{Contexto, DecisionIa, Desempate, Puntuado};
use crate::db::BaseDeDatos;
use crate::error::{NsError, NsResult};
use crate::net::{Red, Servicio};
use crate::privacidad::{self, ProveedorIa};

/// `IA_MAX_TOKENS` de la V1: la respuesta es un JSON corto.
const MAX_TOKENS: u32 = 512;

/// La versión de la API de mensajes de Anthropic que se habla.
const VERSION_ANTHROPIC: &str = "2023-06-01";

/// `_SYSTEM_PROMPT` de la V1, con sus siete reglas.
const SISTEMA: &str = "Eres un sistema de clasificacion musical de alta precision.
Tu unica funcion es elegir el release correcto de MusicBrainz para una cancion dada,
o indicar que ninguno es adecuado.

REGLAS ABSOLUTAS:
1. Solo puedes elegir un candidato de la lista proporcionada. Nunca inventes releases.
2. Si ningun candidato es adecuado, devuelve revision_manual en el campo decision.
3. Prefiere SIEMPRE releases con status Official sobre los demas.
4. Evita compilaciones, lives, remixes y bootlegs salvo que sean la unica opcion clara.
5. El artista principal del release debe coincidir con el artista del archivo.
6. En caso de duda real, devuelve revision_manual. Es mejor que un error.
7. Responde UNICAMENTE con el JSON solicitado, sin texto adicional, sin markdown.";

/// Lo que hace falta para consultar: quién, con qué modelo y con qué clave.
#[derive(Clone)]
pub struct ConfigIa {
    pub proveedor: ProveedorIa,
    pub modelo: String,
    clave: String,
}

// La clave no se imprime ni por descuido en un `{:?}`.
impl std::fmt::Debug for ConfigIa {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("ConfigIa")
            .field("proveedor", &self.proveedor)
            .field("modelo", &self.modelo)
            .finish_non_exhaustive()
    }
}

/// El desempate tal como lo dejó el usuario, si puede usarse: la red y el
/// servicio consentidos y una clave en el llavero. Se mira el consentimiento
/// antes que el llavero para no tocarlo si la IA está apagada.
#[must_use]
pub fn configurada(db: &BaseDeDatos, red: &Red) -> Option<ConfigIa> {
    let politica = red.politica();
    if !politica.general || !politica.servicios.contains(&Servicio::ProveedorIa) {
        return None;
    }
    let (proveedor, modelo) = privacidad::proveedor_y_modelo(db).ok()?;
    let clave = privacidad::clave(proveedor)?;
    Some(ConfigIa {
        proveedor,
        modelo,
        clave,
    })
}

/// Redondea como `round(x, n)` de Python para que el prompt diga lo mismo que
/// el de la V1.
fn redondear(x: f64, decimales: i32) -> f64 {
    let f = 10f64.powi(decimales);
    (x * f).round() / f
}

/// `_construir_prompt_usuario`: el archivo, la lista cerrada de candidatos y el
/// esquema de la respuesta, al final para que se cumpla mejor.
#[must_use]
pub fn prompt_usuario(ctx: &Contexto<'_>, candidatos: &[Puntuado]) -> String {
    let n = ctx.norm;
    let mut archivo = json!({
        "metadata_local": {
            "titulo": n.titulo,
            "artista": n.artista,
            "album": Some(&n.album).filter(|a| !a.is_empty()),
            "anio": n.anio,
            "duracion_seg": n.duracion_seg,
            "isrc": n.isrc,
        },
        "fuente_titulo": n.fuente_titulo,
        "fuente_artista": n.fuente_artista,
    });
    if let Some(s) = ctx.shazam.filter(|s| s.identificado) {
        archivo["shazam"] = json!({
            "titulo": s.titulo,
            "artista": s.artista,
            "album": s.album,
            "isrc": s.isrc,
        });
    }
    // De AcoustID, las tres primeras grabaciones: más solo infla el prompt.
    if let Some(a) = ctx.acoustid.filter(|a| !a.grabaciones.is_empty()) {
        archivo["acoustid"] = json!({
            "recording_ids": a.grabaciones.iter().take(3).collect::<Vec<_>>(),
            "mejor_score": a.mejor(),
        });
    }
    let lista: Vec<Value> = candidatos
        .iter()
        .map(|p| {
            let c = &p.candidato;
            let d = &p.detalle;
            json!({
                "release_id": c.mbid_lanzamiento,
                "recording_id": c.mbid_grabacion,
                "titulo": c.titulo,
                "artista": c.artista,
                "album": c.album,
                "tipo": c.tipo,
                "status": c.estado,
                "anio": c.anio,
                "duracion_seg": c.duracion_seg,
                "isrc": c.isrc,
                "es_compilacion": c.recopilatorio,
                "score_sistema": redondear(c.puntaje, 4),
                "detalle_score": {
                    "titulo": redondear(d.titulo, 3),
                    "artista": redondear(d.artista, 3),
                    "duracion": redondear(d.duracion, 3),
                    "album": redondear(d.album, 3),
                    "numero_pista": redondear(d.numero, 3),
                    "tipo_release": redondear(d.tipo, 3),
                    "isrc": redondear(d.isrc, 3),
                },
                "penalizaciones": c.penalizaciones,
            })
        })
        .collect();
    let bonito = |v: &Value| serde_json::to_string_pretty(v).unwrap_or_default();
    format!(
        "CONTEXTO DEL ARCHIVO A IDENTIFICAR:\n{}\n\nCANDIDATOS DISPONIBLES (elige uno o devuelve revision_manual):\n{}\n\nResponde UNICAMENTE con este JSON:\n{}",
        bonito(&archivo),
        bonito(&Value::from(lista)),
        r#"{"decision": "album|single|ep|revision_manual", "release_id": "<id o null>", "confianza": 0.0, "razones": ["razon1", "razon2"]}"#,
    )
}

/// La petición a cada proveedor: URL, cabeceras y cuerpo.
fn peticion(c: &ConfigIa, usuario: &str) -> (&'static str, Vec<(&'static str, String)>, Value) {
    match c.proveedor {
        ProveedorIa::Anthropic => (
            "https://api.anthropic.com/v1/messages",
            vec![
                ("x-api-key", c.clave.clone()),
                ("anthropic-version", VERSION_ANTHROPIC.to_owned()),
            ],
            json!({
                "model": c.modelo,
                "max_tokens": MAX_TOKENS,
                "system": SISTEMA,
                "messages": [{"role": "user", "content": usuario}],
            }),
        ),
        // `max_completion_tokens` y no `max_tokens`, que OpenAI dejó obsoleto y
        // sus modelos de razonamiento rechazan.
        ProveedorIa::Openai => (
            "https://api.openai.com/v1/chat/completions",
            vec![("Authorization", format!("Bearer {}", c.clave))],
            json!({
                "model": c.modelo,
                "max_completion_tokens": MAX_TOKENS,
                "messages": [
                    {"role": "system", "content": SISTEMA},
                    {"role": "user", "content": usuario},
                ],
            }),
        ),
    }
}

/// El texto del asistente en la respuesta de cada proveedor.
fn texto_de(proveedor: ProveedorIa, cuerpo: &Value) -> Option<String> {
    let t = match proveedor {
        ProveedorIa::Anthropic => cuerpo["content"]
            .as_array()?
            .iter()
            .find(|b| b["type"] == "text")?["text"]
            .as_str(),
        ProveedorIa::Openai => cuerpo["choices"][0]["message"]["content"].as_str(),
    };
    t.map(str::to_owned)
}

/// `_extraer_json_obj`: del primer `{` al último `}`, porque el modelo a veces
/// añade texto alrededor.
fn objeto_json(texto: &str) -> Option<Value> {
    let (i, f) = (texto.find('{')?, texto.rfind('}')?);
    if f < i {
        return None;
    }
    serde_json::from_str::<Value>(&texto[i..=f])
        .ok()
        .filter(Value::is_object)
}

/// `_parsear_y_validar_respuesta`: la decisión tiene que ser una de las cuatro
/// y, si no es revisión, el lanzamiento tiene que estar entre los candidatos.
#[must_use]
pub fn interpretar(texto: &str, candidatos: &[Puntuado]) -> Option<DecisionIa> {
    let datos = objeto_json(texto)?;
    let decision = datos["decision"].as_str()?;
    if !matches!(decision, "album" | "single" | "ep" | "revision_manual") {
        return None;
    }
    if decision == "revision_manual" {
        return Some(DecisionIa::RevisionManual);
    }
    let id = datos["release_id"].as_str()?;
    if !candidatos
        .iter()
        .any(|p| p.candidato.mbid_lanzamiento == id)
    {
        return None;
    }
    let confianza = match &datos["confianza"] {
        Value::Number(n) => n.as_f64().unwrap_or(0.0),
        Value::String(s) => s.trim().parse().unwrap_or(0.0),
        _ => 0.0,
    };
    Some(DecisionIa::Lanzamiento {
        id: id.to_owned(),
        confianza: confianza.clamp(0.0, 1.0),
    })
}

/// El cliente, con la puerta de red por la que sale.
pub struct ClienteIa<'a> {
    pub red: &'a Red,
    pub config: ConfigIa,
}

impl ClienteIa<'_> {
    fn consultar(&self, usuario: &str) -> NsResult<String> {
        let (url, cabeceras, cuerpo) = peticion(&self.config, usuario);
        let cabeceras: Vec<(&str, &str)> =
            cabeceras.iter().map(|(k, v)| (*k, v.as_str())).collect();
        let cuerpo = serde_json::to_vec(&cuerpo).map_err(|_| NsError::Internal)?;
        let (estado, respuesta) =
            self.red
                .enviar_json(Servicio::ProveedorIa, url, &cabeceras, &cuerpo)?;
        if !(200..300).contains(&estado) {
            // El estado basta para saber si es la clave (401), el saldo o el
            // modelo; el cuerpo puede repetir datos de la petición.
            tracing::warn!(estado, "el proveedor de IA rechazó el desempate");
            return Err(NsError::NetworkFailure);
        }
        let respuesta: Value =
            serde_json::from_slice(&respuesta).map_err(|_| NsError::NetworkFailure)?;
        texto_de(self.config.proveedor, &respuesta).ok_or(NsError::NetworkFailure)
    }
}

impl Desempate for ClienteIa<'_> {
    /// Un fallo de la IA nunca rompe la importación: sin respuesta válida, la
    /// ambigüedad queda en revisión.
    fn desempatar(&self, ctx: &Contexto<'_>, candidatos: &[Puntuado]) -> Option<DecisionIa> {
        if candidatos.is_empty() {
            return None;
        }
        let texto = self
            .consultar(&prompt_usuario(ctx, candidatos))
            .map_err(|error| {
                tracing::debug!(codigo = error.code(), "el desempate por IA no respondió");
            })
            .ok()?;
        let decision = interpretar(&texto, candidatos);
        if decision.is_none() {
            tracing::debug!("la IA devolvió una respuesta que no vale");
        }
        decision
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::catalogo::emparejador::Detalle;
    use crate::catalogo::modelo::{DeAcoustid, DeShazam, Normalizada};
    use crate::catalogo::musicbrainz::Candidato;

    fn puntuado(id: &str, puntaje: f64) -> Puntuado {
        Puntuado {
            candidato: Candidato {
                mbid_lanzamiento: id.into(),
                mbid_grabacion: format!("g-{id}"),
                titulo: "Canción".into(),
                artista: "Artista".into(),
                album: "Álbum".into(),
                tipo: "Album".into(),
                estado: "Official".into(),
                puntaje,
                ..Candidato::default()
            },
            detalle: Detalle::default(),
        }
    }

    fn norm() -> Normalizada {
        Normalizada {
            titulo: "Canción".into(),
            artista: "Artista".into(),
            ..Normalizada::default()
        }
    }

    #[test]
    fn solo_vale_un_lanzamiento_de_la_lista_cerrada() {
        let c = [puntuado("a", 0.7), puntuado("b", 0.65)];
        assert_eq!(
            interpretar(
                r#"Aquí va: {"decision": "album", "release_id": "b", "confianza": 0.9, "razones": []} fin"#,
                &c
            ),
            Some(DecisionIa::Lanzamiento {
                id: "b".into(),
                confianza: 0.9
            })
        );
        assert_eq!(
            interpretar(
                r#"{"decision": "album", "release_id": "inventado", "confianza": 1}"#,
                &c
            ),
            None
        );
        assert_eq!(
            interpretar(r#"{"decision": "album", "release_id": null}"#, &c),
            None
        );
    }

    #[test]
    fn la_revision_manual_vale_y_lo_demas_se_descarta() {
        let c = [puntuado("a", 0.7)];
        assert_eq!(
            interpretar(r#"{"decision": "revision_manual", "release_id": null}"#, &c),
            Some(DecisionIa::RevisionManual)
        );
        assert_eq!(
            interpretar(r#"{"decision": "quizas", "release_id": "a"}"#, &c),
            None
        );
        assert_eq!(interpretar("no sé", &c), None);
        assert_eq!(interpretar("} al revés {", &c), None);
    }

    #[test]
    fn la_confianza_se_lleva_al_intervalo_de_cero_a_uno() {
        let c = [puntuado("a", 0.7)];
        let confianza = |t: &str| match interpretar(t, &c) {
            Some(DecisionIa::Lanzamiento { confianza, .. }) => confianza,
            otra => panic!("{otra:?}"),
        };
        assert_eq!(
            confianza(r#"{"decision":"single","release_id":"a","confianza":7}"#),
            1.0
        );
        assert_eq!(
            confianza(r#"{"decision":"ep","release_id":"a","confianza":"0.4"}"#),
            0.4
        );
        assert_eq!(
            confianza(r#"{"decision":"ep","release_id":"a","confianza":"x"}"#),
            0.0
        );
    }

    #[test]
    fn el_prompt_lleva_la_lista_cerrada_y_solo_tres_grabaciones_de_acoustid() {
        let n = norm();
        let shazam = DeShazam {
            identificado: true,
            titulo: "Canción".into(),
            artista: "Artista".into(),
            ..DeShazam::default()
        };
        let acoustid = DeAcoustid {
            grabaciones: (1..=5).map(|i| format!("r{i}")).collect(),
            confianzas: vec![0.8, 0.95],
        };
        let ctx = Contexto {
            norm: &n,
            shazam: Some(&shazam),
            acoustid: Some(&acoustid),
        };
        let p = prompt_usuario(&ctx, &[puntuado("a", 0.71234), puntuado("b", 0.6)]);
        assert!(p.contains("\"release_id\": \"a\"") && p.contains("\"release_id\": \"b\""));
        assert!(p.contains("\"score_sistema\": 0.7123"));
        assert!(p.contains("\"r3\"") && !p.contains("\"r4\""));
        assert!(p.contains("\"mejor_score\": 0.95"));
        assert!(p.contains("\"fuente_titulo\": \"tag_local\""));
        assert!(p.ends_with(r#""razones": ["razon1", "razon2"]}"#));
    }

    #[test]
    fn cada_proveedor_recibe_su_forma_de_peticion_y_se_lee_su_respuesta() {
        let config = |proveedor| ConfigIa {
            proveedor,
            modelo: "m".into(),
            clave: "k".into(),
        };
        let (url, cab, cuerpo) = peticion(&config(ProveedorIa::Anthropic), "hola");
        assert_eq!(url, "https://api.anthropic.com/v1/messages");
        assert!(cab.contains(&("x-api-key", "k".to_owned())));
        assert_eq!(cuerpo["system"], SISTEMA);
        assert_eq!(cuerpo["messages"][0]["content"], "hola");
        let (url, cab, cuerpo) = peticion(&config(ProveedorIa::Openai), "hola");
        assert_eq!(url, "https://api.openai.com/v1/chat/completions");
        assert!(cab.contains(&("Authorization", "Bearer k".to_owned())));
        assert_eq!(cuerpo["messages"][0]["role"], "system");

        assert_eq!(
            texto_de(
                ProveedorIa::Anthropic,
                &json!({"content": [{"type": "text", "text": "{}"}]})
            )
            .as_deref(),
            Some("{}")
        );
        assert_eq!(
            texto_de(
                ProveedorIa::Openai,
                &json!({"choices": [{"message": {"content": "{}"}}]})
            )
            .as_deref(),
            Some("{}")
        );
        assert_eq!(texto_de(ProveedorIa::Openai, &json!({"error": {}})), None);
    }

    #[test]
    fn la_clave_no_sale_en_la_depuracion() {
        let c = ConfigIa {
            proveedor: ProveedorIa::Anthropic,
            modelo: "m".into(),
            clave: "sk-secreta".into(),
        };
        assert!(!format!("{c:?}").contains("sk-secreta"));
    }

    #[test]
    fn sin_consentimiento_no_hay_cliente_ni_se_mira_el_llavero() {
        let db = BaseDeDatos::en_memoria().unwrap();
        let red = Red::new(crate::net::PoliticaDeRed::default());
        assert!(configurada(&db, &red).is_none());
    }

    #[test]
    fn sin_red_el_desempate_no_decide_y_la_ambiguedad_queda_en_revision() {
        let n = norm();
        let ctx = Contexto {
            norm: &n,
            shazam: None,
            acoustid: None,
        };
        let red = Red::new(crate::net::PoliticaDeRed::default());
        let cliente = ClienteIa {
            red: &red,
            config: ConfigIa {
                proveedor: ProveedorIa::Anthropic,
                modelo: "m".into(),
                clave: "k".into(),
            },
        };
        assert_eq!(cliente.desempatar(&ctx, &[puntuado("a", 0.7)]), None);
    }
}
