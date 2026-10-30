# ADR-001: Pila tecnológica de la V2

**Fecha:** 2026-10-29
**Estado:** Aceptado

## Contexto

La V1 (v1.1.16) son unas 111.000 líneas: 60.000 de Python de aplicación, 23.400 de pruebas y 27.261 de QML.
`ui/modelos_qml.py` tiene 11.844 líneas y 610 `@Slot`/`@Property`/`Signal`: es pegamento, no producto. Los cinco
últimos commits de la V1 arreglan MPRIS y el empaquetado con PyInstaller, que son los dos síntomas del problema de
fondo: un proceso Python que carga PySide6, LibVLC, PyTorch y TensorFlow a la vez.

NB Books ya resolvió la misma pregunta (sus ADR-001 y ADR-015, en `NB_Books/docs/adr/`, un repositorio aparte) y
la probó con 152.080 documentos reales. El objetivo explícito es que el ecosistema se sienta como uno solo.

## Alternativas consideradas

1. **Seguir con PySide6/QML y limpiar.** Rechazada: no resuelve la convivencia de runtimes nativos ni el
   empaquetado, y deja a NB Sound con una pila distinta a la del resto del ecosistema.
2. **Tauri v2 + Svelte 5 con el núcleo en Python.** Rechazada en [ADR-002](./ADR-002-sin-python.md): conserva el
   problema de distribución, que es el que más daño hizo.
3. **Tauri v2 + SvelteKit 2 (estático) + Svelte 5 + TypeScript estricto, núcleo en Rust.** Aceptada.

## Decisión

La misma pila que NB Books, con las mismas versiones mínimas y la misma configuración de herramientas:

| Capa | Elección |
|---|---|
| Ventana y sistema | Tauri 2, `protocol-asset` acotado a la caché |
| Interfaz | SvelteKit 2 con `adapter-static`, Svelte 5 (runas), TypeScript estricto |
| Diseño | Material 3 con `m3-svelte` y Material Color Utilities ([ADR-008](./ADR-008-sistema-de-diseno.md)) |
| Núcleo | Rust (`rust-toolchain` 1.98.0, edición 2021), `thiserror`, `tracing`, `serde` |
| Datos | SQLite con `rusqlite` (`bundled`) y `r2d2` ([ADR-004](./ADR-004-datos.md)) |
| Tipos del puente | Generados con `ts-rs`, nunca escritos a mano |
| Calidad | Biome + Prettier, `rustfmt`, Clippy con `-D warnings`, `cargo-deny`, Vitest, Playwright |
| Paquetes | `pnpm` ≥ 10, Node ≥ 22 |

La estructura de carpetas replica la de NB Books: `src/lib/core` (puente, estado), `src/lib/ui` (componentes),
`src/lib/bindings` (generado), `src/routes`, `src-tauri/src/<servicio>.rs`, `scripts/` (guardianes), `e2e/`.

## Consecuencias

- **Positivas:** un solo binario, sin intérprete; tipos de extremo a extremo; los guardianes y el método de NB
  Books se reutilizan en lugar de reinventarse.
- **Negativas:** hay que portar la lógica de Python a Rust (ver [ADR-002](./ADR-002-sin-python.md)).
- **Riesgos:** WebKitGTK en Linux. NB Books documentó sus trampas (medios por esquema propio, desenfoques, animación
  en reposo) y sus guardianes ya las vigilan; se portan desde la Fase 0.

## Enmienda del 2026-10-30: dos dependencias de la Fase 2

Aprobadas por Nathan antes de añadirlas:

* **`image` 0.25, solo con JPEG y PNG** (la misma variante que NB Books). Las portadas originales de la V1 pesan
  2,4 MB cada una; las listas necesitan miniaturas, y la vista de reproducción el color dominante de cada portada.
  Reducirlas en el webview costaría memoria y tiempo en cada desplazamiento.
* **`tauri-plugin-global-shortcut`** (plugin oficial de Tauri): las teclas multimedia y los atajos globales de
  F2.1.6. La bandeja usa la función `tray-icon` del propio Tauri, sin crate nuevo.
  **Al final no se añadió:** las teclas multimedia ya llegan a todo el sistema por MPRIS y SMTC (F2.1.5), y
  registrarlas además como atajo global las haría actuar dos veces. Los atajos de la V1 eran de la ventana
  (`Principal.qml`), y así se portan.
