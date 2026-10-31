//! Qué GPU tiene el equipo, para recomendar el agregado de aceleración (F5.1.5,
//! ADR-006): se recomienda con su motivo y nunca se instala solo.
//!
//! Sin bibliotecas de cada fabricante ni procesos externos: en Linux, el
//! controlador de NVIDIA publica `/proc/driver/nvidia`, que es justo lo que
//! necesita el proveedor CUDA de ONNX Runtime (sin controlador no hay CUDA, haya
//! la tarjeta que haya). En Windows, DirectML funciona con cualquier GPU de
//! DirectX 12, también las integradas. En macOS solo se publica para Apple
//! Silicon, donde CoreML está siempre. AMD en Linux no tiene proveedor en el plan.

use std::path::Path;

use serde::Serialize;
use ts_rs::TS;

/// El proveedor de ONNX Runtime que aprovecharía.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub enum Acelerador {
    Cuda,
    DirectMl,
    CoreMl,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct Gpu {
    pub acelerador: Acelerador,
    /// El modelo, si el sistema lo dice (`NVIDIA GeForce RTX 3060`).
    pub nombre: Option<String>,
}

/// La GPU de este equipo que el agregado de aceleración aprovecharía.
#[must_use]
pub fn detectar() -> Option<Gpu> {
    if cfg!(target_os = "windows") {
        return Some(Gpu {
            acelerador: Acelerador::DirectMl,
            nombre: None,
        });
    }
    if cfg!(all(target_os = "macos", target_arch = "aarch64")) {
        return Some(Gpu {
            acelerador: Acelerador::CoreMl,
            nombre: None,
        });
    }
    if cfg!(target_os = "linux") {
        return nvidia_en(Path::new("/proc/driver/nvidia"));
    }
    None
}

/// Lo que publica el controlador de NVIDIA en Linux: `gpus/<bus>/information`
/// lleva una línea `Model:` con el nombre de cada tarjeta.
fn nvidia_en(dir: &Path) -> Option<Gpu> {
    if !dir.join("version").is_file() {
        return None;
    }
    let nombre = std::fs::read_dir(dir.join("gpus"))
        .ok()?
        .flatten()
        .filter_map(|e| std::fs::read_to_string(e.path().join("information")).ok())
        .find_map(|info| {
            info.lines()
                .find_map(|l| l.strip_prefix("Model:"))
                .map(|m| m.trim().to_owned())
                .filter(|m| !m.is_empty())
        });
    Some(Gpu {
        acelerador: Acelerador::Cuda,
        nombre,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn el_controlador_de_nvidia_dice_la_tarjeta_y_sin_el_no_hay_cuda() {
        let d = std::env::temp_dir().join(format!("ns-gpu-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        assert_eq!(nvidia_en(&d), None);
        std::fs::create_dir_all(d.join("gpus/0000_01_00.0")).unwrap();
        std::fs::write(d.join("version"), "NVRM version: 550.120\n").unwrap();
        std::fs::write(
            d.join("gpus/0000_01_00.0/information"),
            "Model: \t\t NVIDIA GeForce RTX 3060\nIRQ:   142\n",
        )
        .unwrap();
        assert_eq!(
            nvidia_en(&d),
            Some(Gpu {
                acelerador: Acelerador::Cuda,
                nombre: Some("NVIDIA GeForce RTX 3060".into()),
            })
        );
        let _ = std::fs::remove_dir_all(&d);
    }
}
