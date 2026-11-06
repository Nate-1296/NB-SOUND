//! Los permisos de red del sistema: si el cortafuegos deja que el teléfono y los
//! invitados del Modo fiesta lleguen al equipo, y pedirlo cuando no.
//!
//! El servidor del teléfono y el de la fiesta escuchan en la red local. Si el
//! cortafuegos del sistema los bloquea, la función parece rota: el teléfono no
//! encuentra el equipo o la página de la fiesta no carga, y nada lo dice. Pasaba en
//! Windows al decir "no" al aviso del cortafuegos, y pasa en Linux con `ufw` si sus
//! reglas no cubren los puertos. Aquí se comprueba sin pedir nada y, si hace falta,
//! se pide al sistema con su propia ventana de administrador: `pkexec` en Linux,
//! el control de cuentas en Windows y el diálogo de administrador en macOS.
//!
//! Solo se miran los cortafuegos que el sistema trae o que se instalan con él
//! (`ufw`, firewalld, el de Windows y el de aplicaciones de macOS), por su ruta
//! fija: nada se busca en el `PATH`.

use std::ops::RangeInclusive;
use std::path::Path;
use std::process::{Command, Stdio};

use serde::Serialize;
use ts_rs::TS;

/// Lo que se sabe de un servicio frente al cortafuegos.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub enum EstadoRed {
    /// El cortafuegos lo deja pasar.
    Abierto,
    /// El cortafuegos lo bloquea: desde fuera no se llega.
    Bloqueado,
    /// No hay cortafuegos activo que lo impida.
    SinCortafuegos,
    /// No se pudo saber (las reglas no se pueden leer sin ser administrador).
    Desconocido,
}

/// Los permisos de red, para Ajustes > Permisos y los avisos de Dispositivos.
#[derive(Debug, Clone, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct PermisosRed {
    /// `ufw`, `firewalld`, `windows`, `macos`, o `null` si no hay.
    pub cortafuegos: Option<String>,
    /// El teléfono (NB Sound Mobile): su servidor y el anuncio en la red.
    pub telefono: EstadoRed,
    /// La página del Modo fiesta para los invitados.
    pub fiesta: EstadoRed,
    /// Si NB Sound puede pedir al sistema que los abra.
    pub se_puede_pedir: bool,
}

/// Los puertos que hay que dejar pasar.
struct Puertos {
    telefono: RangeInclusive<u16>,
    fiesta: RangeInclusive<u16>,
    /// mDNS, para que el teléfono encuentre el equipo por su nombre.
    mdns: u16,
}

const PUERTOS: Puertos = Puertos {
    telefono: crate::movil::PUERTOS,
    fiesta: crate::fiesta::PUERTOS_FIESTA,
    mdns: 5353,
};

/// Ejecuta un programa del sistema por su ruta y devuelve si acabó bien y lo que
/// escribió. Sin ventana de consola en Windows.
fn ejecutar(programa: &Path, argumentos: &[&str]) -> Option<(bool, String)> {
    let mut c = Command::new(programa);
    c.args(argumentos)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt as _;
        // CREATE_NO_WINDOW: que no parpadee una consola al comprobar.
        c.creation_flags(0x0800_0000);
    }
    let salida = c.output().ok()?;
    Some((
        salida.status.success(),
        String::from_utf8_lossy(&salida.stdout).into_owned(),
    ))
}

/// Si la unión de rangos `permitidos` cubre entero `buscado`.
fn cubre(permitidos: &[RangeInclusive<u16>], buscado: &RangeInclusive<u16>) -> bool {
    let mut siguiente = u32::from(*buscado.start());
    let fin = u32::from(*buscado.end());
    loop {
        if siguiente > fin {
            return true;
        }
        let Some(r) = permitidos
            .iter()
            .filter(|r| u32::from(*r.start()) <= siguiente && siguiente <= u32::from(*r.end()))
            .max_by_key(|r| *r.end())
        else {
            return false;
        };
        siguiente = u32::from(*r.end()) + 1;
    }
}

// --- Linux: ufw y firewalld --------------------------------------------------------------

/// Las reglas de entrada de `ufw` que dejan pasar un protocolo desde cualquier
/// origen y por cualquier interfaz, sacadas de las líneas `### tuple ###` de
/// `user.rules` (legible sin ser administrador).
fn reglas_ufw(texto: &str, protocolo: &str) -> Vec<RangeInclusive<u16>> {
    let mut rangos = Vec::new();
    for linea in texto.lines() {
        let Some(tupla) = linea.strip_prefix("### tuple ### ") else {
            continue;
        };
        let campos: Vec<&str> = tupla.split_whitespace().collect();
        // allow <proto> <dport> <dst> <sport> <src> [aplicación...] <dirección>
        let (Some(&accion), Some(&proto), Some(&dport), Some(&origen), Some(&direccion)) = (
            campos.first(),
            campos.get(1),
            campos.get(2),
            campos.get(5),
            campos.last(),
        ) else {
            continue;
        };
        let origen_abierto = origen == "0.0.0.0/0" || origen == "::/0";
        if accion != "allow"
            || direccion != "in"
            || !origen_abierto
            || !(proto == protocolo || proto == "any")
        {
            continue;
        }
        if dport == "any" {
            rangos.push(0..=u16::MAX);
            continue;
        }
        for parte in dport.split(',') {
            let mut extremos = parte.split(':');
            let desde = extremos.next().and_then(|p| p.parse::<u16>().ok());
            let hasta = extremos.next().and_then(|p| p.parse::<u16>().ok());
            match (desde, hasta) {
                (Some(a), Some(b)) => rangos.push(a..=b),
                (Some(a), None) => rangos.push(a..=a),
                _ => {}
            }
        }
    }
    rangos
}

const UFW: [&str; 2] = ["/usr/sbin/ufw", "/usr/bin/ufw"];
const FIREWALL_CMD: &str = "/usr/bin/firewall-cmd";

fn ufw_activo() -> bool {
    UFW.iter().any(|r| Path::new(r).is_file())
        && std::fs::read_to_string("/etc/ufw/ufw.conf").is_ok_and(|c| {
            c.lines()
                .any(|l| l.trim().eq_ignore_ascii_case("ENABLED=yes"))
        })
}

/// La política de entrada por defecto de `ufw` deja pasar todo.
fn ufw_acepta_por_defecto() -> bool {
    std::fs::read_to_string("/etc/default/ufw").is_ok_and(|c| {
        c.lines().any(|l| {
            l.trim()
                .eq_ignore_ascii_case("DEFAULT_INPUT_POLICY=\"ACCEPT\"")
        })
    })
}

fn estado_ufw() -> (EstadoRed, EstadoRed) {
    if ufw_acepta_por_defecto() {
        return (EstadoRed::Abierto, EstadoRed::Abierto);
    }
    let Ok(reglas) = std::fs::read_to_string("/etc/ufw/user.rules") else {
        return (EstadoRed::Desconocido, EstadoRed::Desconocido);
    };
    let (tcp, udp) = (reglas_ufw(&reglas, "tcp"), reglas_ufw(&reglas, "udp"));
    let abierto = |si: bool| {
        if si {
            EstadoRed::Abierto
        } else {
            EstadoRed::Bloqueado
        }
    };
    let mdns = PUERTOS.mdns..=PUERTOS.mdns;
    (
        abierto(cubre(&tcp, &PUERTOS.telefono) && cubre(&udp, &mdns)),
        abierto(cubre(&tcp, &PUERTOS.fiesta)),
    )
}

fn firewalld_activo() -> bool {
    Path::new(FIREWALL_CMD).is_file()
        && ejecutar(Path::new(FIREWALL_CMD), &["--state"])
            .is_some_and(|(ok, s)| ok && s.trim() == "running")
}

fn estado_firewalld() -> (EstadoRed, EstadoRed) {
    let consulta = |puertos: &RangeInclusive<u16>, protocolo: &str| -> Option<bool> {
        let arg = format!(
            "--query-port={}-{}/{protocolo}",
            puertos.start(),
            puertos.end()
        );
        ejecutar(Path::new(FIREWALL_CMD), &[arg.as_str()]).map(|(ok, _)| ok)
    };
    let estado = |r: Option<bool>| match r {
        Some(true) => EstadoRed::Abierto,
        Some(false) => EstadoRed::Bloqueado,
        None => EstadoRed::Desconocido,
    };
    let mdns = PUERTOS.mdns..=PUERTOS.mdns;
    let telefono = match (consulta(&PUERTOS.telefono, "tcp"), consulta(&mdns, "udp")) {
        (Some(a), Some(b)) => Some(a && b),
        _ => None,
    };
    (estado(telefono), estado(consulta(&PUERTOS.fiesta, "tcp")))
}

/// El guion que se ejecuta como administrador en Linux. Solo toca lo de NB Sound:
/// su perfil de `ufw` o sus puertos en firewalld.
fn guion_linux(ufw: Option<&str>) -> String {
    let (t, f, m) = (&PUERTOS.telefono, &PUERTOS.fiesta, PUERTOS.mdns);
    match ufw {
        Some(ufw) => format!(
            "set -e\n\
             cat > /etc/ufw/applications.d/nb-sound <<'FIN'\n\
             [NBSound]\n\
             title=NB Sound\n\
             description=El teléfono (NB Sound Mobile) y el Modo fiesta de NB Sound\n\
             ports={}:{}/tcp|{}:{}/tcp|{m}/udp\n\
             FIN\n\
             {ufw} app update NBSound >/dev/null 2>&1 || true\n\
             {ufw} allow NBSound >/dev/null\n",
            t.start(),
            t.end(),
            f.start(),
            f.end()
        ),
        None => format!(
            "set -e\n\
             {FIREWALL_CMD} --permanent --add-port={}-{}/tcp --add-port={}-{}/tcp --add-port={m}/udp >/dev/null\n\
             {FIREWALL_CMD} --reload >/dev/null\n",
            t.start(),
            t.end(),
            f.start(),
            f.end()
        ),
    }
}

fn comprobar_linux() -> PermisosRed {
    if ufw_activo() {
        let (telefono, fiesta) = estado_ufw();
        return PermisosRed {
            cortafuegos: Some("ufw".into()),
            telefono,
            fiesta,
            se_puede_pedir: Path::new("/usr/bin/pkexec").is_file(),
        };
    }
    if firewalld_activo() {
        let (telefono, fiesta) = estado_firewalld();
        return PermisosRed {
            cortafuegos: Some("firewalld".into()),
            telefono,
            fiesta,
            se_puede_pedir: Path::new("/usr/bin/pkexec").is_file(),
        };
    }
    PermisosRed {
        cortafuegos: None,
        telefono: EstadoRed::SinCortafuegos,
        fiesta: EstadoRed::SinCortafuegos,
        se_puede_pedir: false,
    }
}

fn pedir_linux() -> bool {
    let ufw = if ufw_activo() {
        UFW.iter().find(|r| Path::new(r).is_file()).copied()
    } else {
        None
    };
    if ufw.is_none() && !firewalld_activo() {
        return true;
    }
    // `pkexec` enseña la ventana de contraseña del escritorio; si se cancela,
    // devuelve 126 y se vuelve a pedir la próxima vez.
    ejecutar(
        Path::new("/usr/bin/pkexec"),
        &["/bin/sh", "-c", guion_linux(ufw).as_str()],
    )
    .is_some_and(|(ok, _)| ok)
}

// --- Windows -----------------------------------------------------------------------------

const POWERSHELL: &str = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe";

/// Base64 de UTF-16LE: lo que espera `-EncodedCommand`, y así ninguna comilla de la
/// ruta del programa rompe la orden.
fn codificar_powershell(guion: &str) -> String {
    const ALFABETO: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let bytes: Vec<u8> = guion.encode_utf16().flat_map(u16::to_le_bytes).collect();
    let mut s = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for trozo in bytes.chunks(3) {
        let b = [
            trozo[0],
            trozo.get(1).copied().unwrap_or(0),
            trozo.get(2).copied().unwrap_or(0),
        ];
        let n = (u32::from(b[0]) << 16) | (u32::from(b[1]) << 8) | u32::from(b[2]);
        for (i, desplazamiento) in [18, 12, 6, 0].into_iter().enumerate() {
            if i <= trozo.len() {
                s.push(char::from(ALFABETO[((n >> desplazamiento) & 63) as usize]));
            } else {
                s.push('=');
            }
        }
    }
    s
}

fn programa_actual() -> Option<String> {
    std::env::current_exe()
        .ok()
        .map(|p| p.to_string_lossy().replace('\'', "''"))
}

fn comprobar_windows() -> PermisosRed {
    let desconocido = PermisosRed {
        cortafuegos: Some("windows".into()),
        telefono: EstadoRed::Desconocido,
        fiesta: EstadoRed::Desconocido,
        se_puede_pedir: true,
    };
    let Some(programa) = programa_actual() else {
        return desconocido;
    };
    // Una línea por cosa: si el cortafuegos está activo en algún perfil, y la
    // acción de cada regla de entrada activa para este programa.
    let guion = format!(
        "$a = @(Get-NetFirewallProfile | Where-Object Enabled).Count; \"activo:$a\"; \
         Get-NetFirewallApplicationFilter -Program '{programa}' -ErrorAction SilentlyContinue | \
         Get-NetFirewallRule | Where-Object {{ $_.Direction -eq 'Inbound' -and $_.Enabled -eq 'True' }} | \
         ForEach-Object {{ \"regla:$($_.Action)\" }}"
    );
    let Some((true, salida)) = ejecutar(
        Path::new(POWERSHELL),
        &[
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            &codificar_powershell(&guion),
        ],
    ) else {
        return desconocido;
    };
    let activo = salida
        .lines()
        .find_map(|l| l.trim().strip_prefix("activo:"))
        .and_then(|n| n.parse::<u32>().ok())
        .unwrap_or(1)
        > 0;
    if !activo {
        return PermisosRed {
            cortafuegos: None,
            telefono: EstadoRed::SinCortafuegos,
            fiesta: EstadoRed::SinCortafuegos,
            se_puede_pedir: false,
        };
    }
    // Un "Bloquear" gana a cualquier "Permitir": es lo que deja Windows al decir
    // que no a su aviso.
    let acciones: Vec<&str> = salida
        .lines()
        .filter_map(|l| l.trim().strip_prefix("regla:"))
        .collect();
    let estado = if acciones.iter().any(|a| a.eq_ignore_ascii_case("Block")) {
        EstadoRed::Bloqueado
    } else if acciones.iter().any(|a| a.eq_ignore_ascii_case("Allow")) {
        EstadoRed::Abierto
    } else {
        EstadoRed::Bloqueado
    };
    PermisosRed {
        cortafuegos: Some("windows".into()),
        telefono: estado,
        fiesta: estado,
        se_puede_pedir: true,
    }
}

fn pedir_windows() -> bool {
    let Some(programa) = programa_actual() else {
        return false;
    };
    // Quita los bloqueos que dejó decir "no" al aviso y permite la entrada al
    // programa en cualquier perfil de red. Se ejecuta elevado con el control de
    // cuentas; si se cancela, `Start-Process` falla y se vuelve a pedir otro día.
    let elevado = format!(
        "Get-NetFirewallApplicationFilter -Program '{programa}' -ErrorAction SilentlyContinue | \
         Get-NetFirewallRule | Where-Object {{ $_.Direction -eq 'Inbound' -and $_.Action -eq 'Block' }} | \
         Remove-NetFirewallRule; \
         Get-NetFirewallRule -DisplayName 'NB Sound' -ErrorAction SilentlyContinue | Remove-NetFirewallRule; \
         New-NetFirewallRule -DisplayName 'NB Sound' -Direction Inbound -Program '{programa}' -Action Allow -Profile Any | Out-Null"
    );
    let lanzar = format!(
        "$p = Start-Process -FilePath '{POWERSHELL}' -Verb RunAs -Wait -PassThru -WindowStyle Hidden \
         -ArgumentList '-NoProfile','-NonInteractive','-EncodedCommand','{}'; exit $p.ExitCode",
        codificar_powershell(&elevado)
    );
    ejecutar(
        Path::new(POWERSHELL),
        &[
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            &codificar_powershell(&lanzar),
        ],
    )
    .is_some_and(|(ok, _)| ok)
}

// --- macOS ---------------------------------------------------------------------------------

const SOCKETFILTERFW: &str = "/usr/libexec/ApplicationFirewall/socketfilterfw";

/// La aplicación (`NB Sound.app`), que es lo que el cortafuegos de macOS permite o
/// bloquea; fuera de un paquete, el propio ejecutable.
fn aplicacion_macos() -> Option<String> {
    let exe = std::env::current_exe().ok()?;
    let app = exe
        .ancestors()
        .find(|p| p.extension().is_some_and(|e| e == "app"))
        .map_or(exe.clone(), Path::to_path_buf);
    Some(app.to_string_lossy().into_owned())
}

fn comprobar_macos() -> PermisosRed {
    let fw = Path::new(SOCKETFILTERFW);
    let activo = ejecutar(fw, &["--getglobalstate"])
        .is_some_and(|(_, s)| s.contains("enabled") || s.contains("State = 1"));
    if !activo {
        return PermisosRed {
            cortafuegos: None,
            telefono: EstadoRed::SinCortafuegos,
            fiesta: EstadoRed::SinCortafuegos,
            se_puede_pedir: false,
        };
    }
    let estado = aplicacion_macos()
        .and_then(|app| ejecutar(fw, &["--getappblocked", &app]))
        .map_or(EstadoRed::Desconocido, |(_, s)| {
            if s.contains("permitted") {
                EstadoRed::Abierto
            } else if s.contains("blocked") {
                EstadoRed::Bloqueado
            } else {
                EstadoRed::Desconocido
            }
        });
    PermisosRed {
        cortafuegos: Some("macos".into()),
        telefono: estado,
        fiesta: estado,
        se_puede_pedir: true,
    }
}

fn pedir_macos() -> bool {
    let Some(app) = aplicacion_macos() else {
        return false;
    };
    // Una ruta con comillas o barras invertidas no existe en un paquete de macOS;
    // se quitan para que no puedan romper la orden.
    let ruta = app.replace(['"', '\\'], "");
    let guion = format!(
        "do shell script \"{SOCKETFILTERFW} --add \\\"{ruta}\\\" ; {SOCKETFILTERFW} --unblockapp \\\"{ruta}\\\"\" with administrator privileges"
    );
    ejecutar(Path::new("/usr/bin/osascript"), &["-e", &guion]).is_some_and(|(ok, _)| ok)
}

// --- Lo que se usa desde fuera ------------------------------------------------------------

/// Comprueba, sin pedir nada, si el cortafuegos deja pasar al teléfono y a la fiesta.
#[must_use]
pub fn comprobar() -> PermisosRed {
    if cfg!(target_os = "linux") {
        comprobar_linux()
    } else if cfg!(target_os = "windows") {
        comprobar_windows()
    } else if cfg!(target_os = "macos") {
        comprobar_macos()
    } else {
        PermisosRed {
            cortafuegos: None,
            telefono: EstadoRed::Desconocido,
            fiesta: EstadoRed::Desconocido,
            se_puede_pedir: false,
        }
    }
}

/// Pide al sistema que deje pasar al teléfono y a la fiesta, con su ventana de
/// administrador. Devuelve si se aceptó; el usuario puede decir que no, y entonces
/// se le vuelve a pedir la próxima vez que haga falta.
#[must_use]
pub fn pedir() -> bool {
    let aceptado = if cfg!(target_os = "linux") {
        pedir_linux()
    } else if cfg!(target_os = "windows") {
        pedir_windows()
    } else if cfg!(target_os = "macos") {
        pedir_macos()
    } else {
        false
    };
    if aceptado {
        tracing::info!("el cortafuegos deja pasar al teléfono y a la fiesta");
    } else {
        tracing::warn!("no se pudo abrir el cortafuegos o se dijo que no");
    }
    aceptado
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn un_perfil_de_ufw_que_cubre_el_telefono_no_cubre_la_fiesta() {
        // El caso real: el perfil "NBSound" abría los puertos del teléfono y no los
        // de la fiesta, y la página no cargaba en el móvil.
        let reglas = "\
### tuple ### allow udp 1714:1764 0.0.0.0/0 any 0.0.0.0/0 KDE%20Connect - in
### tuple ### allow udp 67 0.0.0.0/0 any 0.0.0.0/0 in_virbr0
### tuple ### allow tcp 8731:8799 0.0.0.0/0 any 0.0.0.0/0 NBSound - in
### tuple ### allow udp 5353 0.0.0.0/0 any 0.0.0.0/0 NBSound - in
### tuple ### deny tcp 8831 0.0.0.0/0 any 0.0.0.0/0 in
### tuple ### allow tcp 8081 0.0.0.0/0 any 0.0.0.0/0 in comment=736572
";
        let tcp = reglas_ufw(reglas, "tcp");
        let udp = reglas_ufw(reglas, "udp");
        assert!(cubre(&tcp, &PUERTOS.telefono));
        assert!(cubre(&udp, &(5353..=5353)));
        assert!(
            !cubre(&tcp, &PUERTOS.fiesta),
            "deny y otros puertos no cuentan"
        );
        assert!(
            !cubre(&udp, &(67..=67)),
            "una regla de una sola interfaz no abre la red"
        );
    }

    #[test]
    fn los_rangos_se_unen_para_cubrir() {
        assert!(cubre(&[8831..=8850, 8851..=8899], &(8831..=8899)));
        assert!(!cubre(&[8831..=8850, 8852..=8899], &(8831..=8899)));
        let todo = vec![0..=u16::MAX, 0..=0];
        assert!(cubre(&todo, &(8831..=8899)));
        let lista = reglas_ufw(
            "### tuple ### allow any 8831:8840,8841:8899 0.0.0.0/0 any 0.0.0.0/0 in\n",
            "tcp",
        );
        assert!(cubre(&lista, &(8831..=8899)));
    }

    #[test]
    fn el_guion_de_ufw_abre_el_telefono_la_fiesta_y_mdns() {
        let g = guion_linux(Some("/usr/sbin/ufw"));
        assert!(g.contains("ports=8731:8799/tcp|8831:8899/tcp|5353/udp"));
        assert!(g.contains("/usr/sbin/ufw allow NBSound"));
        let f = guion_linux(None);
        assert!(f.contains("--add-port=8831-8899/tcp"));
    }

    #[test]
    fn powershell_recibe_su_base64_de_utf16() {
        // `[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes('dir'))`
        assert_eq!(codificar_powershell("dir"), "ZABpAHIA");
        assert_eq!(codificar_powershell("a"), "YQA=");
    }
}
