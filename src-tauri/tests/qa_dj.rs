//! Pruebas finales del DJ que necesitan el agregado de texto real. Las lanza
//! `scripts/qa/ui-qa.sh fase6`; sin sus variables se saltan.

use std::path::PathBuf;

use nb_sound_lib::dj::embeddings::{Proveedor, Real, Tokenizador};

/// Ids del tokenizador propio y vectores del modelo de texto para cada frase, en
/// JSON, para compararlos con los de la referencia (`tokenizers` de HuggingFace).
#[test]
#[ignore = "lo ejecuta scripts/qa/ui-qa.sh fase6 con el agregado de texto instalado"]
fn el_tokenizador_y_los_vectores_salen_para_cada_frase() {
    let dir = PathBuf::from(std::env::var_os("NB_QA_TEXTO_DJ").expect("NB_QA_TEXTO_DJ"));
    let frases = std::fs::read_to_string(std::env::var_os("NB_QA_FRASES").expect("NB_QA_FRASES"))
        .expect("frases");
    nb_sound_lib::onnx::fijar_ruta(&PathBuf::from(
        std::env::var_os("NB_QA_ONNXRUNTIME").expect("NB_QA_ONNXRUNTIME"),
    ));
    let json: serde_json::Value =
        serde_json::from_slice(&std::fs::read(dir.join("tokenizer.json")).expect("tokenizer"))
            .expect("json");
    let tokenizador = Tokenizador::desde_json(&json).expect("tokenizador");
    let mut real = Real::abrir(&dir).expect("modelo");
    let salida: Vec<serde_json::Value> = frases
        .lines()
        .map(|f| {
            serde_json::json!({
                "frase": f,
                "ids": tokenizador.codificar(f, 256),
                "vector": real.de_texto(f),
            })
        })
        .collect();
    std::fs::write(
        std::env::var_os("NB_QA_SALIDA").expect("NB_QA_SALIDA"),
        serde_json::to_vec(&salida).expect("salida"),
    )
    .expect("escribir");
}
