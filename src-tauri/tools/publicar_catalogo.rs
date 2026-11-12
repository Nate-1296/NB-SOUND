//! ADR-016: inventario editorial autenticado; nunca se incluye en la aplicación.
use base64::{engine::general_purpose::STANDARD, Engine};
use minisign_verify::{PublicKey, Signature};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::{
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::Path,
    process::ExitCode,
};

type Result<T> = std::result::Result<T, &'static str>;
const OWNER: &str = "nb.sound";
const REPOSITORY: &str = "Nate-1296/NB-SOUND";
const LIFETIME: u64 = 14 * 86400;

#[derive(Serialize)]
struct Catalog {
    schema: u32,
    owner: &'static str,
    repository: &'static str,
    version: String,
    issued_at: u64,
    expires_at: u64,
    artifacts: Vec<Artifact>,
}
#[derive(Serialize)]
struct Artifact {
    id: String,
    app: &'static str,
    version: String,
    repository: &'static str,
    tag: String,
    filename: String,
    platform: &'static str,
    architecture: &'static str,
    format: &'static str,
    bytes: u64,
    sha256: String,
    signature: String,
    public_key: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    managed_layout: Option<&'static str>,
}

fn bounded(path: &Path, limit: u64) -> Result<Vec<u8>> {
    if !fs::symlink_metadata(path).is_ok_and(|m| m.is_file() && m.len() <= limit) {
        return Err("CATALOG_INPUT_INVALID");
    }
    let mut bytes = Vec::new();
    File::open(path)
        .and_then(|file| file.take(limit + 1).read_to_end(&mut bytes))
        .map_err(|_| "CATALOG_INPUT_INVALID")?;
    if bytes.len() as u64 > limit {
        return Err("CATALOG_INPUT_INVALID");
    }
    Ok(bytes)
}
fn key(encoded: &str) -> Result<PublicKey> {
    let raw = STANDARD
        .decode(encoded)
        .map_err(|_| "CATALOG_KEY_INVALID")?;
    PublicKey::decode(std::str::from_utf8(&raw).map_err(|_| "CATALOG_KEY_INVALID")?)
        .map_err(|_| "CATALOG_KEY_INVALID")
}
fn signature(encoded: &str) -> Result<Signature> {
    let raw = STANDARD
        .decode(encoded)
        .map_err(|_| "CATALOG_SIGNATURE_INVALID")?;
    Signature::decode(std::str::from_utf8(&raw).map_err(|_| "CATALOG_SIGNATURE_INVALID")?)
        .map_err(|_| "CATALOG_SIGNATURE_INVALID")
}
fn config(path: &Path) -> Result<(String, String)> {
    let config: serde_json::Value = serde_json::from_slice(&bounded(path, 1024 * 1024)?)
        .map_err(|_| "CATALOG_CONFIG_INVALID")?;
    let version = config["version"]
        .as_str()
        .ok_or("CATALOG_VERSION_INVALID")?;
    let parts = version.split('.').collect::<Vec<_>>();
    if parts.len() != 3
        || parts
            .iter()
            .any(|p| p.parse::<u64>().map_or(true, |n| n.to_string() != *p))
    {
        return Err("CATALOG_VERSION_INVALID");
    }
    let numbers = parts
        .iter()
        .map(|p| p.parse::<u64>().unwrap())
        .collect::<Vec<_>>();
    if numbers.as_slice() < [2, 1, 3].as_slice() {
        return Err("CATALOG_VERSION_INVALID");
    }
    let public_key = config["plugins"]["updater"]["pubkey"]
        .as_str()
        .ok_or("CATALOG_KEY_INVALID")?;
    key(public_key)?;
    Ok((version.into(), public_key.into()))
}
fn inventory(
    version: &str,
) -> [(
    &'static str,
    String,
    &'static str,
    &'static str,
    &'static str,
); 7] {
    [
        (
            "sound-linux-x64-tar",
            format!("NB.Sound_{version}_amd64.tar.gz"),
            "linux",
            "x86_64",
            "tar-gz",
        ),
        (
            "sound-linux-x64-appimage",
            format!("NB.Sound_{version}_amd64.AppImage"),
            "linux",
            "x86_64",
            "appimage",
        ),
        (
            "sound-linux-x64-deb",
            format!("NB.Sound_{version}_amd64.deb"),
            "linux",
            "x86_64",
            "deb",
        ),
        (
            "sound-linux-x64-rpm",
            format!("NB.Sound-{version}-1.x86_64.rpm"),
            "linux",
            "x86_64",
            "rpm",
        ),
        (
            "sound-windows-x64-nsis",
            format!("NB.Sound_{version}_x64-setup.exe"),
            "windows",
            "x86_64",
            "nsis",
        ),
        (
            "sound-windows-x64-msi",
            format!("NB.Sound_{version}_x64_en-US.msi"),
            "windows",
            "x86_64",
            "msi",
        ),
        (
            "sound-macos-arm64-tar",
            "NB.Sound_aarch64.app.tar.gz".into(),
            "macos",
            "aarch64",
            "app-tar-gz",
        ),
    ]
}
fn artifact(
    directory: &Path,
    version: &str,
    public_key: &str,
    item: (
        &'static str,
        String,
        &'static str,
        &'static str,
        &'static str,
    ),
) -> Result<Artifact> {
    let (id, filename, platform, architecture, format) = item;
    let path = directory.join(&filename);
    let encoded = String::from_utf8(bounded(&directory.join(format!("{filename}.sig")), 4096)?)
        .map_err(|_| "CATALOG_SIGNATURE_INVALID")?;
    let encoded = encoded.trim().to_owned();
    let signature = signature(&encoded)?;
    let key = key(public_key)?;
    let mut verifier = key
        .verify_stream(&signature)
        .map_err(|_| "CATALOG_SIGNATURE_INVALID")?;
    if !fs::symlink_metadata(&path)
        .is_ok_and(|m| m.is_file() && m.len() > 0 && m.len() <= 1024 * 1024 * 1024)
    {
        return Err("CATALOG_INPUT_INVALID");
    }
    let mut file = File::open(path).map_err(|_| "CATALOG_INPUT_INVALID")?;
    let expected = file.metadata().map_err(|_| "CATALOG_INPUT_INVALID")?.len();
    let mut hash = Sha256::new();
    let mut bytes = 0u64;
    let mut buffer = [0; 65536];
    loop {
        let n = file
            .read(&mut buffer)
            .map_err(|_| "CATALOG_INPUT_INVALID")?;
        if n == 0 {
            break;
        }
        bytes += n as u64;
        if bytes > expected {
            return Err("CATALOG_INPUT_INVALID");
        }
        verifier.update(&buffer[..n]);
        hash.update(&buffer[..n]);
    }
    if bytes != expected {
        return Err("CATALOG_INPUT_INVALID");
    }
    verifier
        .finalize()
        .map_err(|_| "CATALOG_SIGNATURE_INVALID")?;
    Ok(Artifact {
        id: format!("{id}-v{version}"),
        app: OWNER,
        version: version.into(),
        repository: REPOSITORY,
        tag: format!("v{version}"),
        filename,
        platform,
        architecture,
        format,
        bytes,
        sha256: format!("{:x}", hash.finalize()),
        signature: encoded,
        public_key: public_key.into(),
        managed_layout: (platform == "linux" && format == "tar-gz").then_some("sound_linux_v1"),
    })
}
fn build(directory: &Path, config_path: &Path, issued_at: u64) -> Result<Vec<u8>> {
    let (version, public_key) = config(config_path)?;
    let artifacts = inventory(&version)
        .into_iter()
        .map(|item| artifact(directory, &version, &public_key, item))
        .collect::<Result<Vec<_>>>()?;
    let hashes = artifacts
        .iter()
        .map(|a| &a.sha256)
        .collect::<std::collections::BTreeSet<_>>();
    if hashes.len() != artifacts.len() {
        return Err("CATALOG_INPUT_INVALID");
    }
    let catalog = Catalog {
        schema: 1,
        owner: OWNER,
        repository: REPOSITORY,
        version,
        issued_at,
        expires_at: issued_at
            .checked_add(LIFETIME)
            .ok_or("CATALOG_TIME_INVALID")?,
        artifacts,
    };
    let mut json = serde_json::to_vec_pretty(&catalog).map_err(|_| "CATALOG_OUTPUT_INVALID")?;
    json.push(b'\n');
    if json.len() > 65536 {
        return Err("CATALOG_OUTPUT_INVALID");
    }
    Ok(json)
}
fn run(args: &[String]) -> Result<()> {
    match args {
        [operation, directory, config, issued_at, output] if operation == "build" => {
            let bytes = build(
                Path::new(directory),
                Path::new(config),
                issued_at.parse().map_err(|_| "CATALOG_TIME_INVALID")?,
            )?;
            let mut file = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(output)
                .map_err(|_| "CATALOG_OUTPUT_INVALID")?;
            file.write_all(&bytes)
                .and_then(|_| file.sync_all())
                .map_err(|_| "CATALOG_OUTPUT_INVALID")?;
        }
        [operation, payload, proof, config_path] if operation == "verify" => {
            let (_, public_key) = config(Path::new(config_path))?;
            let bytes = bounded(Path::new(payload), 65536)?;
            let proof = String::from_utf8(bounded(Path::new(proof), 4096)?)
                .map_err(|_| "CATALOG_SIGNATURE_INVALID")?;
            key(&public_key)?
                .verify(&bytes, &signature(proof.trim())?, false)
                .map_err(|_| "CATALOG_SIGNATURE_INVALID")?;
        }
        _ => return Err("CATALOG_ARGUMENTS_INVALID"),
    }
    Ok(())
}
fn main() -> ExitCode {
    match run(&std::env::args().skip(1).collect::<Vec<_>>()) {
        Ok(()) => {
            println!("CATALOG_PUBLICATION_VERIFIED");
            ExitCode::SUCCESS
        }
        Err(code) => {
            eprintln!("{code}");
            ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    // Vectores públicos con semilla de ensayo fija; no son una identidad editorial.
    const KEY: &str = "dW50cnVzdGVkIGNvbW1lbnQ6IGZpeHR1cmUga2V5ClJXUUJBZ01FQlFZSENCbC9heVBoYklVeXhxdklPUHJOWHFlSnZneDJzcElETkFPYitvczlObzFoCg==";
    const PROOF: &str = "dW50cnVzdGVkIGNvbW1lbnQ6IGZpeHR1cmUgc2lnbmF0dXJlClJVUUJBZ01FQlFZSENKelR3cFhrS0k1SzAvYTIybEhBdlROa0QvV1dmdTdqY095RGxyRS9qVUJMUUpWNjRmNW82eU5VUEJMY0dYVDl3aFdQbVhvK3cwU2pmSkpaVnhrR0lBOD0KdHJ1c3RlZCBjb21tZW50OiB0aW1lc3RhbXA6MQlmaWxlOmZpeHR1cmUKd0VGVzNRWmNMOHlIcU1ZN0NYbzFaKzdEWlF6M1BCKy9FWXhrYktPbjB1WEVjWnoyMXVIazBZUkw3OXJZN2tnQVV5RDBHQ09tNlJQVXB1WHdzREZzQmc9PQo=";

    struct Temp(std::path::PathBuf);
    impl std::ops::Deref for Temp {
        type Target = Path;
        fn deref(&self) -> &Path {
            &self.0
        }
    }
    impl Drop for Temp {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
    fn temporary(label: &str) -> Temp {
        let unique = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "nb-catalog-{label}-{}-{unique}",
            std::process::id()
        ));
        #[cfg(unix)]
        {
            use std::os::unix::fs::DirBuilderExt;
            fs::DirBuilder::new().mode(0o700).create(&path).unwrap();
        }
        #[cfg(not(unix))]
        fs::create_dir(&path).unwrap();
        Temp(path)
    }

    #[test]
    fn los_formatos_publicados_son_unicos_y_no_incluyen_un_instalador_no_firmado() {
        let inventory = inventory("2.1.3");
        let names = inventory
            .iter()
            .map(|i| &i.1)
            .collect::<std::collections::BTreeSet<_>>();
        assert_eq!(names.len(), 7);
        assert!(!inventory.iter().any(|i| i.1.ends_with(".dmg")));
        assert_eq!(inventory.iter().filter(|i| i.4 == "tar-gz").count(), 1);
    }
    #[test]
    fn un_inventario_incompleto_no_genera_un_catalogo() {
        let temp = temporary("incomplete");
        let config = Path::new(env!("CARGO_MANIFEST_DIR")).join("tauri.conf.json");
        let result = build(&temp, &config, 1);
        assert!(result.is_err());
    }
    #[test]
    fn no_se_acepta_una_clave_descargada_como_configuracion() {
        assert!(key("not-a-key").is_err());
        assert!(signature("not-a-signature").is_err());
    }

    #[test]
    fn el_hash_sale_de_los_bytes_firmados_y_un_paquete_alterado_se_rechaza() {
        let temp = temporary("signed");
        let item = inventory("2.1.3").into_iter().next().unwrap();
        let filename = item.1.clone();
        fs::write(temp.join(&filename), b"paquete de prueba").unwrap();
        fs::write(temp.join(format!("{filename}.sig")), PROOF).unwrap();
        let verified = artifact(&temp, "2.1.3", KEY, item.clone()).unwrap();
        assert_eq!(verified.bytes, 17);
        assert_eq!(
            verified.sha256,
            format!("{:x}", Sha256::digest(b"paquete de prueba"))
        );
        fs::write(temp.join(&filename), b"paquete alterado!").unwrap();
        assert!(artifact(&temp, "2.1.3", KEY, item.clone()).is_err());
        fs::write(temp.join(&filename), b"paquete de prueba").unwrap();
        let foreign = include_str!("../tauri.conf.json");
        let foreign: serde_json::Value = serde_json::from_str(foreign).unwrap();
        assert!(artifact(
            &temp,
            "2.1.3",
            foreign["plugins"]["updater"]["pubkey"].as_str().unwrap(),
            item
        )
        .is_err());
    }

    #[test]
    fn una_version_invalida_o_anterior_no_publica_un_contrato_inexistente() {
        let temp = temporary("versions");
        let path = temp.join("config.json");
        for version in ["2.1.2", "2.1", "02.1.3", "2.1.3-beta.1", "2.1.3+repacked"] {
            fs::write(
                &path,
                serde_json::to_vec(
                    &serde_json::json!({"version":version,"plugins":{"updater":{"pubkey":KEY}}}),
                )
                .unwrap(),
            )
            .unwrap();
            assert!(config(&path).is_err());
        }
    }
    #[test]
    fn un_mismo_contenido_no_se_presenta_como_siete_formatos_distintos() {
        let temp = temporary("duplicates");
        let path = temp.join("config.json");
        fs::write(
            &path,
            serde_json::to_vec(
                &serde_json::json!({"version":"2.1.3","plugins":{"updater":{"pubkey":KEY}}}),
            )
            .unwrap(),
        )
        .unwrap();
        for (_, name, _, _, _) in inventory("2.1.3") {
            fs::write(temp.join(&name), b"paquete de prueba").unwrap();
            fs::write(temp.join(format!("{name}.sig")), PROOF).unwrap();
        }
        assert!(matches!(
            build(&temp, &path, 1),
            Err("CATALOG_INPUT_INVALID")
        ));
    }
}
