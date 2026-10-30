# Fase 0: Fundaciones y prototipos que deciden

> **Objetivo:** un repositorio con la estructura, las herramientas y los guardianes de NB Books, que compila,
> verifica y empaqueta una ventana vacía con todo dentro; y los prototipos que confirman o derriban
> [ADR-002](../adr/decisions/ADR-002-sin-python.md) y [ADR-003](../adr/decisions/ADR-003-motor-de-audio.md).
>
> **Prerrequisitos:** ninguno. Empieza hoy.
>
> **Regla de la fase:** aquí no se construye producto. Los prototipos (subfase 0.4) son código desechable dentro de
> `src-tauri/examples/` o `scripts/prototipos/`; lo que sobrevive es su informe en `docs/audit/` y sus pruebas.

## Estado de la fase

| Iteración | Estado | Nota |
|---|---|---|
| F0.1.1 Constitución, ADR y plan | Hecha | 2026-10-29 |
| F0.1.2 Contrato de trabajo (`CLAUDE.md`) | Hecha | 2026-10-29 |
| F0.1.3 Mover la V1 a `legado/` | Hecha | 2026-10-29. Desde `legado/`, archivo por archivo: 1.207 pruebas pasan y 5 fallan, las cinco por desajustes previos de la V1 (versión de `pyproject.toml` distinta de `infra/version.py`, una prueba de MPRIS desfasada, dos de Ajustes que dependen del `.env` local y una de karaoke). El modo con `pytest-forked` no funciona en este entorno: cada prueba sale con estado 3 |
| F0.1.4 Documentación de la V1 archivada en `docs/v1/` | Hecha | 2026-10-29 |
| F0.1.5 Repositorio público de distribución para agregados | Pendiente | |
| F0.2.1 Esqueleto Tauri 2 + SvelteKit 2 + Svelte 5 + m3-svelte | Hecha | Carcasa con los siete destinos, Por revisar condicional y reproductor inerte |
| F0.2.2 Herramientas idénticas a NB Books | Parcial | Falta `cargo-deny` en la máquina; `deny.toml` está escrito |
| F0.2.3 Contrato de errores, tipos generados y frontera del puente | Hecha | 14 códigos canónicos |
| F0.2.4 Registro con redacción | Hecha | |
| F0.2.5 Puerta de red con consentimiento | Hecha | De fábrica no sale nada; cada servicio con sus anfitriones |
| F0.2.6 Rutas estándar por plataforma | Hecha | Carpetas distintas de las de la V1, con prueba |
| F0.2.7 Tokens de Material 3 compartidos | Hecha | Los 63 temas de la V1 como acentos |
| F0.3.1 `pnpm verify` con los guardianes portados | Parcial | Doce activos; `check-transacciones` y `check-listas` se activan con la capa de datos; faltan `check-paquete`, `check-i18n` y los avisos de terceros |
| F0.3.2 Integración continua en tres plataformas | Parcial | `.github/workflows/ci.yml` escrito (convenciones, `pnpm verify`, runtime en Linux, Windows y macOS, `cargo-deny`). El 2026-10-29 GitHub no arrancó ningún trabajo: "recent account payments have failed or your spending limit needs to be increased" (lo mismo que le pasa a NB Books). Mientras tanto, `check-plataforma` es la única red multiplataforma |
| F0.3.3 Binarios empaquetados con hash fijado | Parcial | Linux y Windows fijados (`fpcalc` 1.6.2, ONNX Runtime 1.31.1); macOS pendiente de CI. `ffmpeg` sale del instalador (enmienda de ADR-006) |
| F0.3.4 Primera puerta de empaquetado | Pendiente | |
| F0.4.1 Prototipo del motor de audio | Hecha | ADR-003 confirmado con tres ajustes; ver el [informe](../audit/2026-10-29-prototipo-motor-audio.md) |
| F0.4.2 Prototipo de karaoke en ONNX | Pendiente | Decide ADR-002 (karaoke) |
| F0.4.3 Prototipo de análisis en ONNX | Pendiente | Decide ADR-002 (análisis) |
| F0.4.4 Prototipo de rasgos básicos en Rust | Pendiente | Decide ADR-002 (rasgos) |
| F0.4.5 Respuestas doradas del servidor móvil | Hecha | 36 respuestas (11 endpoints, errores, `Range`, selección y WebSocket) sobre un escenario inventado; grabar dos veces da lo mismo byte a byte. Revelaron campos que el contrato no documenta (las playlists traen `descripcion`, `categoria`, `etiqueta`, `num_pistas`, `cover_url`…), que la V2 también debe dar |
| F0.4.6 Huella acústica: `fpcalc` o `rusty-chromaprint` | Hecha | En 66 pistas del corpus, `rusty-chromaprint` 0.3 da la misma longitud pero **ninguna huella idéntica** (entre 96,8 % y 99,7 % de bits iguales; la diferencia está en el remuestreo). Se queda `fpcalc` 1.6.2, que son 5 MB |
| F0.4.7 Listas virtualizadas en WebKitGTK | Pendiente | |

---

## Subfase 0.1: Gobierno

**F0.1.3 Mover la V1 a `legado/`.**
Objetivo: dejar la raíz libre para la V2 sin perder la V1 ([ADR-011](../adr/decisions/ADR-011-transicion-del-repositorio.md)).
Criterio: un solo commit con `git mv` de todo el código, pruebas, empaquetado y requisitos de la V1 a `legado/`;
`cd legado && pytest` pasa igual que antes; los flujos de `.github/workflows/` de la V1 se retiran; en la raíz solo
quedan `docs/`, `LICENSE`, los archivos de comunidad y un `README.md` nuevo de la V2.

**F0.1.5 Repositorio público de distribución.**
Objetivo: un sitio público y estable desde el que descargar agregados e instaladores, porque `NB-SOUND` es privado.
Criterio: decidido entre un repositorio `NB-SOUND-DIST` público (como el ADR-011 de NB Books) y Hugging Face, con
una URL de prueba descargable sin credenciales.

## Subfase 0.2: Esqueleto

**F0.2.1 Esqueleto.** Tauri 2, SvelteKit 2 con `adapter-static`, Svelte 5 y TypeScript estricto, con la misma
estructura que NB Books (`src/lib/core`, `src/lib/ui`, `src/lib/bindings`, `src/routes`, `src-tauri/src`,
`scripts/`, `e2e/`). Criterio: `pnpm tauri dev` abre una ventana con la carcasa vacía (barra lateral con los siete
destinos de [ADR-007](../adr/decisions/ADR-007-arquitectura-de-informacion.md) y barra de reproducción inerte);
`default-run` y `mainBinaryName` fijados, con la prueba `identidad_del_binario` de NB Books.

**F0.2.2 Herramientas.** `rust-toolchain.toml` 1.98.0, `rustfmt.toml`, `clippy.toml`, `deny.toml`, `biome.json`,
`.prettierrc`, `.editorconfig`, `.nvmrc`, `.npmrc` y `.githooks` (pre-commit y commit-msg con Conventional Commits
y DCO), copiados de NB Books y adaptados. Criterio: `pnpm lint`, `cargo fmt --check` y `cargo clippy -D warnings`
pasan; un commit sin `-s` o con mensaje mal formado se rechaza.

**F0.2.3 Errores y puente.** `error.rs` con códigos canónicos y estables, nunca `Result<_, String>` en la
superficie pública; tipos con `ts-rs` en `src/lib/bindings`; toda llamada al puente pasa por `$core/ipc` (lint
`noRestrictedImports`, también en `.svelte`). Criterio: `check:errors` y `check:bindings` pasan, y fallan si se
introduce un `String` como error o un tipo escrito a mano.

**F0.2.4 Registro.** `tracing` con salida rotativa y `telemetry::redact_path` y `redact_text`. Criterio:
`check:registro` rechaza un campo de registro que nombre una ruta, un título o un artista sin redactar.

**F0.2.5 Red.** `net.rs` es el único sitio con cliente HTTP; cada salida declara servicio y propósito y respeta el
interruptor general y el del servicio ([ADR-009](../adr/decisions/ADR-009-configuracion-y-red.md)). Criterio:
`check:network` falla con un cliente HTTP fuera de `net.rs`; una prueba demuestra que con el interruptor apagado no
sale nada.

**F0.2.6 Rutas.** Directorios estándar del sistema operativo para datos, caché, registros y agregados; la única
ruta del usuario es la carpeta de música. Toda ruta que llega de fuera se canonicaliza y se acota
(`security::resolve_within`). Criterio: `check:rutas` y `check:plataforma` pasan; pruebas por plataforma de las
rutas resultantes.

**F0.2.7 Tokens.** `scripts/generar-paletas.mjs` y `src/paletas.css` como en NB Books, con las semillas de la V1
como acentos ([ADR-008](../adr/decisions/ADR-008-sistema-de-diseno.md)). Criterio: `check:paletas` pasa y
`check:ui` rechaza un color literal.

## Subfase 0.3: Verificación y empaquetado

**F0.3.1 `pnpm verify`.** Guardianes portados de NB Books con su origen citado en la cabecera: `check-docs`,
`check-ui`, `check-error-contract`, `check-bindings`, `check-comandos` (ningún comando síncrono), `check-transacciones`
(`BEGIN IMMEDIATE`), `check-listas` (colecciones con `limit`), `check-network`, `check-registro`, `check-rutas`,
`check-plataforma`, `check-puente`, `check-paquete` (arranque ≤ 250 KB), `check-paletas`, `check-i18n` y
`generate-notices --check`. Más un guardián propio, `check-sin-python`, que falla si aparece un intérprete o un
`.py` fuera de `legado/` y `scripts/prototipos/`. Criterio: `pnpm verify` pasa en limpio y cada guardián tiene una
prueba que demuestra que falla cuando debe.

**F0.3.2 Integración continua.** Flujo de verificación y de empaquetado para Linux, Windows y macOS. Criterio: el
flujo está escrito; si GitHub no lo ejecuta por ser privado, se dice en esta tabla (como pasó en NB Books) y
`check-plataforma` hace de red.

**F0.3.3 Binarios.** `scripts/fetch-binarios.mjs` descarga `fpcalc` y ONNX Runtime para cada
plataforma con el hash fijado, verifica antes de extraer y los declara como `externalBin` o recurso de Tauri.
Ningún binario entra al repositorio. Criterio: `pnpm check:binarios` falla si un hash no coincide.

**F0.3.4 Primera puerta de empaquetado.** Criterio: los cuatro puntos de la [sección 5.1](./README.md#51-la-puerta-de-empaquetado)
en Linux, con la ventana vacía arrancando en un contenedor sin VLC, sin Python y sin `ffmpeg`.

## Subfase 0.4: Prototipos que deciden

Cada prototipo deja un informe en `docs/audit/` con lo medido, la máquina y la conclusión, y actualiza el estado del
ADR que decide.

**F0.4.1 Motor de audio.** Symphonia 0.6 + Kira 0.12 sobre `cpal`, detrás de una interfaz `MotorAudio`. Criterio:
los seis puntos de la tabla de [ADR-003](../adr/decisions/ADR-003-motor-de-audio.md) (sin cortes entre pistas,
seek < 10 ms, karaoke con 0 muestras de deriva en 5 min, ecualizador dentro de ±0,5 dB, cero vacíos con la CPU al
100 %, menos del 2 % de un núcleo). Si Kira no pasa, se prueba el motor propio sobre `cpal` antes de cerrar.

**F0.4.2 Karaoke en ONNX.** `htdemucs` en ONNX (fp16 y fp32) con `ort`, en 20 pistas del corpus con stems ya
generados por la V1. Criterio: diferencia de SDR del instrumental < 0,1 dB respecto a la V1; tiempo por pista y
memoria pico medidos y no peores que los de la V1 en esta máquina; se elige fp16 o fp32 con esos datos.

**F0.4.3 Análisis en ONNX.** Conversión de los 12 modelos `.pb` con `tf2onnx` (script reproducible en
`scripts/prototipos/`), preprocesado mel de MusiCNN, VGGish y EffNet en Rust, inferencia con `ort`. Criterio: en
las 407 pistas con análisis en la base de la V1, cada salida difiere menos de 0,01 por clase.

**F0.4.4 Rasgos básicos.** Tempo, energía, centroide, ancho de banda, rolloff, ZCR, onset y croma en Rust; la
tonalidad con modo mayor o menor (perfiles de Krumhansl) en lugar del `argmax` de la V1. Criterio: tempo dentro de
±2 % (o 2× / 0,5×) del de la V1 en ≥ 95 % de las 2.397 pistas; el resto de rasgos con una correlación ≥ 0,95; la
tonalidad nueva se valida a oído en 30 pistas.

**F0.4.5 Respuestas doradas.** Con el servidor real de la V1 sobre un escenario inventado
(`src-tauri/tests/contrato_movil/escenario.json`, sin datos del usuario), se graban las respuestas de los 11
endpoints y del WebSocket, incluidos errores (token inválido, pista sin stems, `Range` parcial), en
`respuestas.json`, con lo volátil sustituido por marcadores. El grabador está en
`scripts/prototipos/contrato-movil/grabar.py`; con `--comprobar` vuelve a grabar y exige lo mismo. El arnés de la V2
(F3) siembra el mismo escenario en su base y compara con estas respuestas, admitiendo solo campos añadidos.
Criterio: el arnés pasa contra la V1, que es la referencia.

**F0.4.6 Huella acústica.** `rusty-chromaprint` 0.3 frente a `fpcalc` en 100 pistas. Criterio: si la huella
comprimida coincide exactamente y AcoustID devuelve los mismos resultados, se usa el crate y `fpcalc` deja de
viajar; si no, se empaqueta `fpcalc`.

**F0.4.7 Listas en WebKitGTK.** Lista virtualizada de 2.397 pistas y de 100.000 simuladas con portadas distintas,
con la técnica de NB Books. Criterio: desplazamiento sin fotogramas largos según `medir-en-webkitgtk.py` de NB
Books, y memoria en reposo dentro del suelo de WebKitGTK medido en la misma ejecución.

## Cierre de la fase

Se cierra cuando todas las iteraciones están Hechas o Parciales con lo que falta escrito, la puerta de empaquetado
pasa en Linux y ADR-002 y ADR-003 están confirmados o superados por ADR nuevos.
