//! El arnés de respuestas doradas (ADR-005, F0.4.5 y Fase 3).
//!
//! Siembra en la base de la V2 el mismo escenario inventado que
//! `scripts/prototipos/contrato-movil/grabar.py` sembró en la V1, enciende el
//! servidor de la V2 y hace las mismas peticiones, como las haría el teléfono.
//! Compara con lo que respondió la V1 (`respuestas.json`) con las reglas de
//! `docs/engineering/contrato-movil.md`:
//!
//! * mismo código y mismas cabeceras de las cinco que se grabaron;
//! * mismo cuerpo, salvo los marcadores `<...>` (cualquier cadena)
//!   y los campos que la V2 añade;
//! * el `content-length` de la V1 tiene que salir exacto al quitar lo añadido:
//!   es lo que prueba que el JSON se escribe como lo escribía Python;
//! * las diferencias deliberadas con la V1 están en `DIFERENCIAS`, cada una con
//!   su motivo, y en el documento del contrato.

use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use futures_util::{SinkExt, StreamExt};
use nb_sound_lib::db::BaseDeDatos;
use nb_sound_lib::movil::{self, Opciones, Puente, ServidorMovil};
use nb_sound_lib::paths::Rutas;
use nb_sound_lib::reproductor::Instantanea;
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};

const CABECERAS: [&str; 5] = [
    "content-type",
    "content-length",
    "content-range",
    "accept-ranges",
    "x-nb-sound-hash",
];
/// Lo que la V2 hace distinto a propósito: la ruta del valor dentro de la
/// respuesta (`*` es cualquier índice) y por qué.
const DIFERENCIAS: [(&str, &str); 2] = [
    (
        "playlists.*.cover_url",
        "la V1 solo daba portada a las playlists con un mosaico ya generado, y en la \
         instalación real lo tenían todas; la V2 lo compone al pedirlo",
    ),
    (
        "frames.*.indice",
        "la V1 mandaba -1 como índice de la cola cuando era 0 (`int(x or -1)`)",
    ),
];

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

fn leer(nombre: &str) -> Value {
    let ruta = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/contrato_movil")
        .join(nombre);
    serde_json::from_str(&std::fs::read_to_string(ruta).unwrap()).unwrap()
}

/// Siembra el escenario como lo hace `grabar.py::sembrar` en la V1, con el
/// contador en pausa y las mismas versiones, en el mismo orden.
fn sembrar(e: &Value, db: &BaseDeDatos, rutas: &Rutas, musica: &Path) {
    let mut conn = db.conexion().unwrap();
    let tx = conn.transaction().unwrap();
    tx.execute_batch("UPDATE sincronizacion SET pausada = 1")
        .unwrap();
    let mut version = 0i64;
    let mut siguiente = || {
        version += 1;
        version
    };
    for a in e["artistas"].as_array().unwrap() {
        let nombre = a["nombre"].as_str().unwrap();
        tx.execute(
            "INSERT INTO artistas (id, nombre, clave, sync_version) VALUES (?1, ?2, ?3, ?4)",
            rusqlite::params![a["id"].as_i64(), nombre, nombre.to_lowercase(), siguiente()],
        )
        .unwrap();
    }
    for al in e["albums"].as_array().unwrap() {
        let id = al["id"].as_i64().unwrap();
        let portada = al.get("portada").and_then(Value::as_str).map(|contenido| {
            let nombre = format!("portada_{id}.jpg");
            std::fs::write(rutas.portadas().join(&nombre), contenido).unwrap();
            tx.execute(
                "INSERT INTO portadas (sha256, ruta, ancho, alto, bytes, mime, origen)
                 VALUES (?1, ?2, 1, 1, ?3, 'image/jpeg', 'prueba')",
                rusqlite::params![
                    hex(&Sha256::digest(contenido)),
                    nombre,
                    contenido.len() as i64
                ],
            )
            .unwrap();
            tx.last_insert_rowid()
        });
        let titulo = al["titulo"].as_str().unwrap();
        tx.execute(
            "INSERT INTO albumes (id, artista_id, titulo, clave, tipo, anio, portada_id, sync_version)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
            rusqlite::params![
                id,
                al["artista_id"].as_i64(),
                titulo,
                titulo.to_lowercase(),
                al.get("tipo").and_then(Value::as_str).unwrap_or("Album"),
                al["anio"].as_i64(),
                portada,
                siguiente()
            ],
        )
        .unwrap();
    }
    for p in e["pistas"].as_array().unwrap() {
        let id = p["id"].as_i64().unwrap();
        let contenido = p["audio"].as_str().unwrap().repeat(64);
        let nombre = format!("pista_{id}.mp3");
        std::fs::write(musica.join(&nombre), &contenido).unwrap();
        tx.execute(
            "INSERT INTO pistas (id, album_id, artista_id, titulo, artista_nombre, album_titulo, ruta,
                                 tamano, sha256, numero, duracion_seg, anio, genero, favorita,
                                 favorita_actualizada_en, sync_version)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16)",
            rusqlite::params![
                id,
                p["album_id"].as_i64(),
                p["artista_id"].as_i64(),
                p["titulo"].as_str(),
                p["artista_nombre"].as_str(),
                p["album_titulo"].as_str(),
                nombre,
                contenido.len() as i64,
                hex(&Sha256::digest(&contenido)),
                p["track_number"].as_i64(),
                p["duracion_seg"].as_f64(),
                p["anio"].as_i64(),
                p["genero"].as_str(),
                p["favorita"].as_bool().unwrap_or(false),
                p["favorita_actualizada_en"].as_str(),
                siguiente()
            ],
        )
        .unwrap();
        if let Some(inst) = p.get("instrumental").and_then(Value::as_str) {
            let nombre = format!("instrumental_{id}.mp3");
            std::fs::create_dir_all(rutas.stems()).unwrap();
            std::fs::write(rutas.stems().join(&nombre), inst.repeat(64)).unwrap();
            tx.execute(
                "INSERT INTO stems (pista_id, estado, instrumental) VALUES (?1, 'lista', ?2)",
                rusqlite::params![id, nombre],
            )
            .unwrap();
        }
        if let Some(l) = p.get("letras") {
            tx.execute(
                "INSERT INTO letras (pista_id, sincronizadas, planas) VALUES (?1, ?2, ?3)",
                rusqlite::params![id, l["synced_lyrics"].as_str(), l["plain_lyrics"].as_str()],
            )
            .unwrap();
        }
    }
    for pl in e["playlists"].as_array().unwrap() {
        let id = pl["id"].as_i64().unwrap();
        tx.execute(
            "INSERT INTO playlists (id, nombre, tipo, visible) VALUES (?1, ?2, ?3, ?4)",
            rusqlite::params![
                id,
                pl["nombre"].as_str(),
                pl.get("tipo").and_then(Value::as_str).unwrap_or("manual"),
                pl.get("visible").and_then(Value::as_bool).unwrap_or(true)
            ],
        )
        .unwrap();
        for (pos, pista) in pl["pista_ids"].as_array().unwrap().iter().enumerate() {
            tx.execute(
                "INSERT INTO playlist_pistas (playlist_id, pista_id, posicion) VALUES (?1, ?2, ?3)",
                rusqlite::params![id, pista.as_i64(), pos as i64],
            )
            .unwrap();
        }
        tx.execute(
            "UPDATE playlists SET sync_version = ?2 WHERE id = ?1",
            rusqlite::params![id, siguiente()],
        )
        .unwrap();
    }
    for (clave, valor) in e["perfil"].as_object().unwrap() {
        tx.execute(
            "INSERT INTO preferencias (clave, valor) VALUES (?1, ?2)",
            rusqlite::params![clave, valor.to_string()],
        )
        .unwrap();
    }
    for t in e["borrados"].as_array().unwrap() {
        tx.execute(
            "INSERT INTO tumbas (entidad, entidad_id, sync_version) VALUES (?1, ?2, ?3)",
            rusqlite::params![t["entidad"].as_str(), t["entidad_id"].as_i64(), siguiente()],
        )
        .unwrap();
    }
    tx.execute(
        "INSERT INTO preferencias (clave, valor) VALUES ('carpeta_musica', ?1)",
        [Value::from(musica.to_str().unwrap()).to_string()],
    )
    .unwrap();
    tx.execute(
        "UPDATE sincronizacion SET version = ?1, pausada = 0",
        [version],
    )
    .unwrap();
    tx.commit().unwrap();
}

/// El estado del reproductor del escenario, como lo publicaría el de la V2.
fn instantanea(e: &Value) -> Instantanea {
    let r = &e["reproductor"];
    let s = &r["estado"];
    Instantanea {
        estado: if s["reproduciendo"].as_bool().unwrap() {
            "reproduciendo"
        } else {
            "pausado"
        }
        .into(),
        pista_id: r["pista_activa"]["id"].as_i64(),
        posicion_seg: s["posicion_seg"].as_f64().unwrap(),
        duracion_seg: s["duracion_seg"].as_f64().unwrap(),
        indice_cola: s["indice_cola"].as_u64().map(|i| i as u32),
        cola: r["cola"]
            .as_array()
            .unwrap()
            .iter()
            .map(|p| p["id"].as_i64().unwrap())
            .collect(),
        aleatorio: s["aleatorio"].as_bool().unwrap(),
        repeticion: s["modo_repeticion"].as_str().unwrap().into(),
        volumen: s["volumen"].as_f64().unwrap() as f32 / 100.0,
        normalizar: true,
        karaoke_disponible: s["karaoke_disponible"].as_bool().unwrap(),
        karaoke_activo: s["karaoke_activo"].as_bool().unwrap(),
        dj: None,
        ciego: false,
    }
}

fn tolerada(ruta: &str) -> bool {
    DIFERENCIAS.iter().any(|(patron, _)| {
        let p: Vec<&str> = patron.split('.').collect();
        let r: Vec<&str> = ruta.split('.').collect();
        p.len() <= r.len()
            && r[r.len() - p.len()..]
                .iter()
                .zip(&p)
                .all(|(a, b)| *b == "*" || a == b)
    })
}

/// Compara lo de la V2 con lo de la V1 y devuelve lo de la V2 tal como lo habría
/// escrito la V1: sin los campos añadidos y con las diferencias deliberadas
/// devueltas a su valor. Con eso se recalcula el `content-length`.
fn comparar(ruta: &str, v1: &Value, v2: &Value, fallos: &mut Vec<String>) -> Value {
    if tolerada(ruta) {
        return v1.clone();
    }
    match (v1, v2) {
        (Value::String(m), _) if m.starts_with('<') && m.ends_with('>') => {
            if !v2.is_string() {
                fallos.push(format!("{ruta}: se esperaba una cadena, llegó {v2}"));
            }
            v2.clone()
        }
        (Value::Object(a), Value::Object(b)) => {
            let mut proyectado = Map::new();
            for (k, va) in a {
                match b.get(k) {
                    Some(vb) => {
                        proyectado
                            .insert(k.clone(), comparar(&format!("{ruta}.{k}"), va, vb, fallos));
                    }
                    None => fallos.push(format!("{ruta}.{k}: falta")),
                }
            }
            Value::Object(proyectado)
        }
        (Value::Array(a), Value::Array(b)) => {
            if a.len() != b.len() {
                fallos.push(format!(
                    "{ruta}: {} elementos en la V1, {} en la V2",
                    a.len(),
                    b.len()
                ));
            }
            Value::Array(
                a.iter()
                    .zip(b)
                    .enumerate()
                    .map(|(i, (x, y))| comparar(&format!("{ruta}.{i}"), x, y, fallos))
                    .collect(),
            )
        }
        (Value::Number(a), Value::Number(b))
            if a.as_f64() == b.as_f64() && a.is_f64() == b.is_f64() =>
        {
            v2.clone()
        }
        _ if v1 == v2 => v2.clone(),
        _ => {
            fallos.push(format!("{ruta}: la V1 dio {v1}, la V2 da {v2}"));
            v2.clone()
        }
    }
}

struct Respuesta {
    estado: u16,
    cabeceras: Map<String, Value>,
    cuerpo: Vec<u8>,
}

fn pedir(
    agente: &ureq::Agent,
    base: &str,
    paso: &Value,
    token: Option<&str>,
    qr: &str,
) -> Respuesta {
    let url = format!("{base}{}", paso["ruta"].as_str().unwrap());
    let metodo = paso["metodo"].as_str().unwrap();
    let mut cabeceras: Vec<(String, String)> = paso
        .get("cabeceras")
        .and_then(Value::as_object)
        .map(|c| {
            c.iter()
                .map(|(k, v)| (k.clone(), v.as_str().unwrap().to_owned()))
                .collect()
        })
        .unwrap_or_default();
    if paso.get("auth").and_then(Value::as_bool).unwrap_or(true) {
        if let Some(t) = token {
            cabeceras.push(("Authorization".into(), format!("Bearer {t}")));
        }
    }
    let mut cuerpo = paso.get("cuerpo").cloned();
    if let Some(c) = cuerpo.as_mut().and_then(Value::as_object_mut) {
        if c.get("token") == Some(&json!("<token>")) {
            c.insert("token".into(), json!(qr));
        }
    }
    let respuesta = if metodo == "POST" {
        let mut r = agente.post(&url).header("Content-Type", "application/json");
        for (k, v) in &cabeceras {
            r = r.header(k.as_str(), v.as_str());
        }
        r.send(serde_json::to_vec(&cuerpo.unwrap_or(Value::Null)).unwrap())
    } else {
        let mut r = agente.get(&url);
        for (k, v) in &cabeceras {
            r = r.header(k.as_str(), v.as_str());
        }
        r.call()
    };
    let mut respuesta = respuesta.unwrap();
    let mut grabadas = Map::new();
    for c in CABECERAS {
        if let Some(v) = respuesta.headers().get(c) {
            grabadas.insert(c.to_owned(), json!(v.to_str().unwrap()));
        }
    }
    Respuesta {
        estado: respuesta.status().as_u16(),
        cabeceras: grabadas,
        cuerpo: respuesta.body_mut().read_to_vec().unwrap(),
    }
}

/// El verificador del teléfono: confía en el certificado solo si su huella es la
/// que se fijó al emparejar (TOFU), sin mirar la cadena ni el nombre.
#[derive(Debug)]
struct PorHuella(String);

impl tokio_rustls::rustls::client::danger::ServerCertVerifier for PorHuella {
    fn verify_server_cert(
        &self,
        cert: &tokio_rustls::rustls::pki_types::CertificateDer<'_>,
        _: &[tokio_rustls::rustls::pki_types::CertificateDer<'_>],
        _: &tokio_rustls::rustls::pki_types::ServerName<'_>,
        _: &[u8],
        _: tokio_rustls::rustls::pki_types::UnixTime,
    ) -> Result<tokio_rustls::rustls::client::danger::ServerCertVerified, tokio_rustls::rustls::Error>
    {
        if hex(&Sha256::digest(cert.as_ref())) == self.0 {
            Ok(tokio_rustls::rustls::client::danger::ServerCertVerified::assertion())
        } else {
            Err(tokio_rustls::rustls::Error::General(
                "huella distinta".into(),
            ))
        }
    }

    fn verify_tls12_signature(
        &self,
        m: &[u8],
        c: &tokio_rustls::rustls::pki_types::CertificateDer<'_>,
        d: &tokio_rustls::rustls::DigitallySignedStruct,
    ) -> Result<
        tokio_rustls::rustls::client::danger::HandshakeSignatureValid,
        tokio_rustls::rustls::Error,
    > {
        tokio_rustls::rustls::crypto::verify_tls12_signature(
            m,
            c,
            d,
            &tokio_rustls::rustls::crypto::ring::default_provider()
                .signature_verification_algorithms,
        )
    }

    fn verify_tls13_signature(
        &self,
        m: &[u8],
        c: &tokio_rustls::rustls::pki_types::CertificateDer<'_>,
        d: &tokio_rustls::rustls::DigitallySignedStruct,
    ) -> Result<
        tokio_rustls::rustls::client::danger::HandshakeSignatureValid,
        tokio_rustls::rustls::Error,
    > {
        tokio_rustls::rustls::crypto::verify_tls13_signature(
            m,
            c,
            d,
            &tokio_rustls::rustls::crypto::ring::default_provider()
                .signature_verification_algorithms,
        )
    }

    fn supported_verify_schemes(&self) -> Vec<tokio_rustls::rustls::SignatureScheme> {
        tokio_rustls::rustls::crypto::ring::default_provider()
            .signature_verification_algorithms
            .supported_schemes()
    }
}

/// El siguiente frame de texto, como JSON. Los ping del servidor no cuentan.
async fn siguiente<S, E>(ws: &mut S) -> Value
where
    S: futures_util::Stream<Item = Result<tokio_tungstenite::tungstenite::Message, E>> + Unpin,
    E: std::fmt::Debug,
{
    loop {
        let m = tokio::time::timeout(std::time::Duration::from_secs(3), ws.next())
            .await
            .expect("un frame a tiempo")
            .expect("el control sigue abierto")
            .unwrap();
        if let tokio_tungstenite::tungstenite::Message::Text(t) = m {
            return serde_json::from_str(t.as_str()).unwrap();
        }
    }
}

async fn recorrer_ws(
    direccion: std::net::SocketAddr,
    huella: &str,
    token: &str,
    paso: &Value,
) -> Vec<Value> {
    use tokio_rustls::rustls::ClientConfig;
    use tokio_tungstenite::tungstenite::client::IntoClientRequest;
    use tokio_tungstenite::tungstenite::Message;

    let provider = Arc::new(tokio_rustls::rustls::crypto::ring::default_provider());
    let config = ClientConfig::builder_with_provider(provider)
        .with_safe_default_protocol_versions()
        .unwrap()
        .dangerous()
        .with_custom_certificate_verifier(Arc::new(PorHuella(huella.to_owned())))
        .with_no_client_auth();
    let tcp = tokio::net::TcpStream::connect(direccion).await.unwrap();
    let tls = tokio_rustls::TlsConnector::from(Arc::new(config))
        .connect("nbsound.local".try_into().unwrap(), tcp)
        .await
        .expect("el teléfono confía en el servidor por su huella");
    let mut peticion = format!("wss://{direccion}/api/v1/control")
        .into_client_request()
        .unwrap();
    peticion
        .headers_mut()
        .insert("Authorization", format!("Bearer {token}").parse().unwrap());
    let (mut ws, _) = tokio_tungstenite::client_async(peticion, tls)
        .await
        .unwrap();
    let mut frames = vec![siguiente(&mut ws).await];
    for m in paso["mensajes"].as_array().unwrap() {
        let texto = match m {
            Value::String(s) => s.clone(),
            otro => otro.to_string(),
        };
        ws.send(Message::Text(texto.into())).await.unwrap();
        let esperados = if m.get("accion") == Some(&json!("queue")) {
            2
        } else {
            1
        };
        let mut recibidos = Vec::new();
        for _ in 0..esperados {
            recibidos.push(siguiente(&mut ws).await);
        }
        // El orden entre el ack y la cola no forma parte del contrato.
        recibidos.sort_by_key(|f| f["tipo"].as_str().unwrap_or_default().to_owned());
        frames.extend(recibidos);
    }
    let _ = ws.close(None).await;
    frames
}

fn temporal(nombre: &str) -> PathBuf {
    let dir =
        std::env::temp_dir().join(format!("ns-contrato-movil-{nombre}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

#[test]
fn la_v2_responde_al_telefono_lo_mismo_que_la_v1() {
    let escenario = leer("escenario.json");
    let doradas = leer("respuestas.json");
    let dir = temporal("doradas");
    let rutas = Rutas::bajo(&dir).unwrap();
    std::fs::create_dir_all(rutas.portadas()).unwrap();
    let musica = dir.join("musica");
    std::fs::create_dir_all(&musica).unwrap();
    let db = BaseDeDatos::abrir(&rutas.base_de_datos()).unwrap();
    sembrar(&escenario, &db, &rutas, &musica);

    let puente = Puente::default();
    puente.publicar(&instantanea(&escenario));
    let ordenes = Arc::new(Mutex::new(Vec::new()));
    let o = Arc::clone(&ordenes);
    puente.conectar(move |orden| o.lock().unwrap().push(format!("{orden:?}")));
    let servidor = ServidorMovil::nuevo(
        db.clone(),
        rutas.clone(),
        puente,
        Opciones {
            host: Some("127.0.0.1".parse().unwrap()),
            mdns: false,
            puertos: 0..=0,
            identidad_v1: None,
        },
        || {},
    );
    servidor.encender().unwrap();
    let direccion = servidor.direccion().unwrap();
    let huella = nb_sound_lib::identidad_movil::huella_sha256(
        &std::fs::read_to_string(rutas.identidad_movil().join("sync_cert.pem")).unwrap(),
    )
    .unwrap();
    let base = format!("https://{direccion}");
    let agente: ureq::Agent = ureq::Agent::config_builder()
        .tls_config(
            ureq::tls::TlsConfig::builder()
                .disable_verification(true)
                .build(),
        )
        .http_status_as_error(false)
        .build()
        .into();

    let pasos = escenario["peticiones"].as_array().unwrap();
    let respuestas = doradas["respuestas"].as_array().unwrap();
    assert_eq!(pasos.len(), respuestas.len());
    let mut token: Option<String> = None;
    let mut fallos = Vec::new();
    for (paso, v1) in pasos.iter().zip(respuestas) {
        let nombre = paso["nombre"].as_str().unwrap();
        assert_eq!(nombre, v1["nombre"].as_str().unwrap());
        if paso.get("ws").is_some() {
            let runtime = tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .unwrap();
            let frames = runtime.block_on(recorrer_ws(
                direccion,
                &huella,
                token.as_deref().unwrap(),
                paso,
            ));
            comparar(
                nombre,
                &json!({"frames": v1["frames"]}),
                &json!({"frames": frames}),
                &mut fallos,
            );
            continue;
        }
        let qr = servidor.token_vigente().unwrap_or_default();
        let r = pedir(&agente, &base, paso, token.as_deref(), &qr);
        if r.estado != v1["estado"].as_u64().unwrap() as u16 {
            fallos.push(format!(
                "{nombre}: estado {} en la V1, {} en la V2",
                v1["estado"], r.estado
            ));
        }
        let tipo = r
            .cabeceras
            .get("content-type")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let cuerpo = if tipo.contains("json") {
            let c: Value = serde_json::from_slice(&r.cuerpo).unwrap();
            if nombre.starts_with("pair") && r.estado == 200 {
                token = c["device_token"].as_str().map(str::to_owned);
            }
            c
        } else {
            json!({"bytes": r.cuerpo.len(), "sha256": hex(&Sha256::digest(&r.cuerpo))})
        };
        let mut avisos = Vec::new();
        let como_v1 = comparar(nombre, &v1["cuerpo"], &cuerpo, &mut avisos);
        fallos.extend(avisos);
        let esperadas = v1["cabeceras"].as_object().unwrap();
        for c in CABECERAS {
            let (a, b) = (esperadas.get(c), r.cabeceras.get(c));
            if c == "content-length" && tipo.contains("json") {
                // Sin lo añadido, el cuerpo de la V2 tiene que medir lo mismo.
                let medido = if como_v1 == cuerpo {
                    r.cuerpo.len()
                } else {
                    movil::json_como_v1(&como_v1).len()
                };
                if a.and_then(Value::as_str) != Some(medido.to_string().as_str()) {
                    fallos.push(format!(
                        "{nombre}: content-length {a:?} en la V1, {medido} sin lo añadido"
                    ));
                }
                continue;
            }
            if a != b {
                fallos.push(format!(
                    "{nombre}: cabecera {c}: {a:?} en la V1, {b:?} en la V2"
                ));
            }
        }
    }
    servidor.apagar();
    assert!(
        fallos.is_empty(),
        "diferencias con la V1:\n{}",
        fallos.join("\n")
    );
    assert_eq!(
        *ordenes.lock().unwrap(),
        ["PausarReanudar", "Buscar(90.0)", "Volumen(0.7)"],
        "las órdenes del control remoto llegaron al reproductor"
    );
    let _ = std::fs::remove_dir_all(&dir);
}

/// Lo que las respuestas doradas no recorren: el estado y la cola que el equipo
/// empuja solo cuando cambian, y que quitar un teléfono lo echa al momento.
#[test]
fn el_telefono_recibe_los_cambios_y_quitarlo_lo_desconecta() {
    let escenario = leer("escenario.json");
    let dir = temporal("empuje");
    let rutas = Rutas::bajo(&dir).unwrap();
    std::fs::create_dir_all(rutas.portadas()).unwrap();
    let musica = dir.join("musica");
    std::fs::create_dir_all(&musica).unwrap();
    let db = BaseDeDatos::abrir(&rutas.base_de_datos()).unwrap();
    sembrar(&escenario, &db, &rutas, &musica);
    let puente = Puente::default();
    let inicial = instantanea(&escenario);
    puente.publicar(&inicial);
    let servidor = ServidorMovil::nuevo(
        db,
        rutas.clone(),
        puente.clone(),
        Opciones {
            host: Some("127.0.0.1".parse().unwrap()),
            mdns: false,
            puertos: 0..=0,
            identidad_v1: None,
        },
        || {},
    );
    servidor.encender().unwrap();
    let direccion = servidor.direccion().unwrap();
    let huella = nb_sound_lib::identidad_movil::huella_sha256(
        &std::fs::read_to_string(rutas.identidad_movil().join("sync_cert.pem")).unwrap(),
    )
    .unwrap();
    let agente: ureq::Agent = ureq::Agent::config_builder()
        .tls_config(
            ureq::tls::TlsConfig::builder()
                .disable_verification(true)
                .build(),
        )
        .http_status_as_error(false)
        .build()
        .into();
    let base = format!("https://{direccion}");
    let cuerpo = serde_json::to_vec(
        &json!({"token": servidor.token_vigente().unwrap(), "nombre_dispositivo": "P"}),
    )
    .unwrap();
    let par: Value = serde_json::from_slice(
        &agente
            .post(format!("{base}/api/v1/pair"))
            .send(cuerpo)
            .unwrap()
            .body_mut()
            .read_to_vec()
            .unwrap(),
    )
    .unwrap();
    let token = par["device_token"].as_str().unwrap().to_owned();
    let id = par["dispositivo_id"].as_i64().unwrap();

    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    runtime.block_on(async {
        use tokio_tungstenite::tungstenite::client::IntoClientRequest;
        let provider = Arc::new(tokio_rustls::rustls::crypto::ring::default_provider());
        let config = tokio_rustls::rustls::ClientConfig::builder_with_provider(provider)
            .with_safe_default_protocol_versions()
            .unwrap()
            .dangerous()
            .with_custom_certificate_verifier(Arc::new(PorHuella(huella.clone())))
            .with_no_client_auth();
        let tcp = tokio::net::TcpStream::connect(direccion).await.unwrap();
        let tls = tokio_rustls::TlsConnector::from(Arc::new(config))
            .connect("nbsound.local".try_into().unwrap(), tcp)
            .await
            .unwrap();
        let mut peticion = format!("wss://{direccion}/api/v1/control")
            .into_client_request()
            .unwrap();
        peticion
            .headers_mut()
            .insert("Authorization", format!("Bearer {token}").parse().unwrap());
        let (mut ws, _) = tokio_tungstenite::client_async(peticion, tls)
            .await
            .unwrap();
        assert_eq!(siguiente(&mut ws).await["tipo"], "estado");

        // Pausa y cola nueva: llegan un estado y una cola sin pedirlos.
        let mut cambio = inicial.clone();
        cambio.estado = "pausado".into();
        cambio.cola = vec![102];
        cambio.indice_cola = Some(0);
        cambio.pista_id = Some(102);
        puente.publicar(&cambio);
        let mut frames = [siguiente(&mut ws).await, siguiente(&mut ws).await];
        frames.sort_by_key(|f| f["tipo"].as_str().unwrap_or_default().to_owned());
        assert_eq!(frames[0]["tipo"], "cola");
        assert_eq!(frames[0]["items"][0]["id"], 102);
        assert_eq!(frames[1]["reproduciendo"], false);
        assert_eq!(frames[1]["pista"]["titulo"], "Sola");

        // Quitarlo desde Ajustes cierra su control y su token deja de valer.
        // El servidor corre en su propio runtime: bloquear este no lo detiene.
        servidor.quitar(id).unwrap();
        let cerrado = tokio::time::timeout(std::time::Duration::from_secs(3), async {
            loop {
                match ws.next().await {
                    None | Some(Err(_)) => break,
                    Some(Ok(tokio_tungstenite::tungstenite::Message::Close(_))) => break,
                    Some(Ok(_)) => {}
                }
            }
        })
        .await;
        assert!(
            cerrado.is_ok(),
            "el control se cierra al quitar el teléfono"
        );
    });
    let r = agente
        .get(format!("{base}/api/v1/manifest"))
        .header("Authorization", format!("Bearer {token}"))
        .call()
        .unwrap();
    assert_eq!(r.status().as_u16(), 401);
    servidor.apagar();
}
