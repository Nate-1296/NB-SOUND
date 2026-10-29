# Investigación previa a la V2 (2026-10-29)

> Qué se comprobó, cómo y con qué fuente, para sostener los ADR 001 a 011. Lo que no se pudo comprobar se dice.

## 1. Medido en el código y en la instalación real

| Hecho | Cómo se midió |
|---|---|
| 83.569 líneas de Python versionadas (23.381 de pruebas) y 27.261 de QML/JS | `git ls-files` + `wc -l` |
| `ui/modelos_qml.py`: 11.844 líneas, 610 `@Slot`/`@Property`/`Signal` | `grep -c` |
| 18 vistas QML; Configuración 2.951 líneas, Importación 1.726, Karaoke 1.277, Estado del Sistema 587 | `wc -l ui/qml/vistas/*.qml` |
| Modo Pro/Simple: `ui_mode` en `NavLateral.qml` y `VistaImportacion.qml` | `grep` |
| Formatos aceptados: `.mp3 .flac .m4a .wav .ogg .aac` | `config/settings.py:345` |
| Essentia solo se usa para `MonoLoader` y `TensorflowPredict*` sobre 12 modelos `.pb` | `core/audio_intelligence_deep.py`, `infra/modelos_essentia.py` |
| librosa: tempo, RMS, centroide, ancho de banda, rolloff, ZCR, onset y croma; tonalidad por `argmax` del croma | `core/audio_features.py:170-185` |
| El DJ no cambia el tempo; técnicas `energy_blend`, `eq_kill_bass`, `filter_sweep`, `harmonic_mix` | `servicios/dj_privado/mix_engine.py` |
| Base V1: 2.397 pistas, 1.421 álbumes, 434 artistas, 56 playlists, 3.225 historial, 323 karaoke, 407 con análisis profundo, 12 dispositivos | Consulta de solo lectura |
| La base pesa 464 MB, de los cuales 441 MB son `track_deep_audio_features`; `raw_output_json` promedia 1,1 MB por pista | `dbstat` y `avg(length())` |
| Corpus: 2.397 MP3, 14 GB, en `~/Música/biblioteca` | `find` + `du` |
| Certificado del servidor móvil en `~/.config/nb_sound/sync/` | `infra/tls_local.py` |
| La V1 abre transacciones con `BEGIN` a secas | `db/conexion.py:639` |
| Más de 100 variables en `.env`, con claves de AcoustID, Anthropic, OpenAI y TheAudioDB en texto plano | Nombres de variable, sin leer valores |
| Contrato móvil: 11 endpoints + WebSocket, protocolo `1`, TLS con TOFU, mDNS `_nbsound._tcp.local.` | `NB_Sound_Mobile/docs/pc-contract.md` |

## 2. Comprobado fuera

| Pregunta | Respuesta | Fuente |
|---|---|---|
| ¿Qué decodifica Symphonia? | 0.6.1 (agosto de 2026). MP3, FLAC, PCM y Vorbis "Excellent" con reproducción sin cortes; AAC-LC "Great" sin ella; ALAC "Great" con ella; HE-AAC, HE-AACv2, Opus y WavPack "en desarrollo" | [README de Symphonia](https://github.com/pdeljanov/Symphonia), [crates.io](https://crates.io/crates/symphonia) |
| ¿Essentia tiene wheels para Windows? | **No.** 2.1b6.dev1438 (2026-05-19): solo `manylinux2014_x86_64` y `macosx_15_0` arm64/x86_64, tanto `essentia` como `essentia-tensorflow` | API JSON de PyPI |
| Licencia de Essentia | AGPL-3.0 para uso no comercial; licencia comercial a petición | [Licensing Essentia](https://essentia.upf.edu/licensing_information.html) |
| Licencia de los modelos de Essentia | Uso no comercial: CC BY-NC-SA 4.0 según la página de modelos, CC BY-NC-ND 4.0 según la de licencias; propietaria a petición | [Modelos](https://essentia.upf.edu/models.html), [Licencias](https://essentia.upf.edu/licensing_information.html) |
| ¿Hay modelos de Essentia en ONNX? | Solo `discogs-effnet-bs64`; MusiCNN, VGGish y las cabezas de clasificación solo en `.pb` | [Modelos](https://essentia.upf.edu/models.html) |
| ¿Demucs v4 funciona en ONNX? | Sí: `htdemucs` opset 17, 316 MB (fp32) o 166 MB (fp16), diferencia máxima con PyTorch 6,6·10⁻⁴, STFT dentro del grafo, entrada `(1, 2, 343980)`, ~1,6 s por segmento de 7,8 s en CPU (M4 Pro), MIT | [adowu/htdemucs-onnx](https://huggingface.co/adowu/htdemucs-onnx), [Mixxx GSoC 2025](https://mixxx.org/news/2025-10-27-gsoc2025-demucs-to-onnx-dhunstack/) |
| Versiones de PyPI relevantes | `demucs` 4.1.0 (MIT); `torch` 2.15.0 con wheels para Windows; `shazamio` 0.9.0 (MIT); `shazamio-core` 2.0.0, en Rust, MIT | API JSON de PyPI, `gh api` |
| ¿Kira sirve para EQ y sincronía? | 0.12.6 (2026-10-28), MIT/Apache-2.0. Efectos: `compressor`, `delay`, `distortion`, `eq_filter`, `filter`, `panning_control`, `reverb`, `volume_control`; reloj para programar sonidos; streaming en escritorio | [docs.rs/kira](https://docs.rs/kira/latest/kira/effect/index.html) |
| MPRIS en Rust | `mpris-server` 0.11.0 (2026-10-26), MPL-2.0, sobre `zbus` | [mpris-server](https://github.com/seadve/mpris-server) |
| Controles multimedia en Windows y macOS | `souvlaki` 0.9.3 (MIT) | [crates.io](https://crates.io/crates/souvlaki) |
| Chromaprint en Rust | `rusty-chromaprint` 0.3.0, MIT, port "en progreso"; sin garantía publicada de huella idéntica a `fpcalc` | [rusty-chromaprint](https://github.com/darksv/rusty-chromaprint) |
| Shazam en Rust | `songrec` 0.8.0 (GPL-3.0); `shazamio-core` (MIT) ya está en Rust | [SongRec](https://github.com/marin-m/SongRec), [shazamio-core](https://github.com/shazamio/shazamio-core) |
| Resto de crates | `lofty` 0.25.5, `ebur128` 0.1.11, `material-colors` 0.5.0, `cpal` 0.18.2, `ort` 2.0.0-rc.15 (ONNX Runtime 1.31), `rubato` 5.0.1, `axum` 0.8.9, `mdns-sd` 0.21.6, `rustls` 0.23.46, `rcgen` 0.14.10, `keyring` 4.2.0, `rusqlite` 0.41.1, `biquad` 0.6.0; todas MIT, Apache-2.0 o MPL-2.0 | API de crates.io |

## 3. Lo que no se pudo comprobar y queda para los prototipos

* Si Kira da precisión de muestra para la cola sin cortes y para el karaoke: F0.4.1.
* Si `tf2onnx` convierte los 12 `.pb` y si el preprocesado mel se replica con paridad: F0.4.3.
* El rendimiento de `htdemucs` ONNX en esta máquina frente al PyTorch de la V1: F0.4.2.
* Si `rusty-chromaprint` iguala a `fpcalc`: F0.4.6.
* El tamaño real del agregado de CUDA para ONNX Runtime: F5.1.5.
