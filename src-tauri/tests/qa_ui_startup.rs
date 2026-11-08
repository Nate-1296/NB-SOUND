//! Regresión del primer fotograma visible (QA-IA, 2026-11-08).
//!
//! La ventana principal no puede mostrarse antes de que la interfaz aplique la
//! apariencia guardada. Si vuelve a ser visible al crearse, el usuario ve el tema
//! negro de fábrica durante uno o dos fotogramas.

use serde_json::Value;

fn json(texto: &str) -> Value {
    serde_json::from_str(texto).expect("JSON válido")
}

#[test]
fn la_ventana_espera_a_que_la_apariencia_este_pintada() {
    let configuracion = json(include_str!("../tauri.conf.json"));
    let principal = configuracion["app"]["windows"]
        .as_array()
        .and_then(|ventanas| ventanas.iter().find(|v| v["label"] == "main"))
        .expect("la ventana main existe");
    assert_eq!(principal["visible"], false, "main nace oculta");

    let permisos = json(include_str!("../capabilities/default.json"));
    assert!(
        permisos["permissions"]
            .as_array()
            .is_some_and(|lista| lista.iter().any(|p| p == "core:window:allow-show")),
        "la interfaz necesita permiso explícito para mostrar la ventana"
    );

    let layout = include_str!("../../src/routes/+layout.svelte");
    assert!(layout.contains("mostrarVentanaTrasApariencia"));
    assert!(layout.contains("notificar.error"));

    let arranque = include_str!("../../src/lib/core/arranque.ts");
    assert!(arranque.contains("ESPERA_APARIENCIA_MS = 1500"));
    assert!(arranque.contains("finally"));
    assert!(arranque.contains("await mostrar()"));
}
