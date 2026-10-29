# NB Sound: contrato de trabajo

Este archivo es el contrato operativo del proyecto. Lo que está aquí **se aplica sin que nadie lo recuerde**.
Sigue el mismo modelo que `../NB_Books/CLAUDE.md`: si algo no está aquí, se hace como en NB Books.

---

## 1. La regla que gobierna todas las demás

**`docs/` es la fuente única de verdad.** Si el código y `docs/` discrepan, hay un defecto: se corrige el código o
se cambia el documento por el proceso de decisión. Nunca se deja la contradicción viva.

## 2. Antes de escribir código, en este orden

| Paso | Documento | Qué se busca |
|---|---|---|
| 1 | [Constitución](docs/contextual/constitution/README.md) | Las ocho reglas. Nada las incumple |
| 2 | [Plan](docs/plan/README.md) | Qué iteración toca y su criterio de aceptación |
| 3 | [Preguntas abiertas](docs/contextual/open-questions/README.md) | Si el trabajo depende de algo no decidido |
| 4 | [ADR](docs/adr/README.md) | Por qué las cosas son como son |
| 5 | [Inventario de la V1](docs/contextual/inventario-v1.md) | Qué hacía la V1 y qué destino tiene |

Si el trabajo depende de una decisión no tomada, **no se empieza**: se plantea la decisión.

## 3. Estado del repositorio

* **La V1 está congelada en `v1.1.16`.** Hasta F0.1.3 vive en la raíz; después, en `legado/`. No se le añaden
  funciones. Sirve para consultar la lógica, grabar las respuestas doradas y medir la paridad.
* **La V2 se construye en la raíz** con la estructura de NB Books ([ADR-011](docs/adr/decisions/ADR-011-transicion-del-repositorio.md)).
* **Solo existe la rama `main`.** No se crean ramas.
* **NB Sound Mobile no se toca** ([ADR-005](docs/adr/decisions/ADR-005-contrato-movil.md)). Su
  `docs/pc-contract.md` es el contrato que la V2 cumple byte a byte.

## 4. Innegociables

| Regla | Mecanismo |
|---|---|
| Nada que instalar fuera de la aplicación; lo opcional es un agregado de un clic | Puerta de empaquetado en máquina limpia; `check-plataforma` |
| Ningún intérprete de Python en la V2 | `check-sin-python` |
| Un solo producto, sin modos ni vistas de diagnóstico | [ADR-007](docs/adr/decisions/ADR-007-arquitectura-de-informacion.md) |
| Ningún error viaja como cadena | `check-error-contract` |
| Los tipos del puente se generan | `ts-rs` + `check-bindings` |
| Ningún componente llama al puente fuera de `$core/ipc` | Lint `noRestrictedImports` |
| Ningún comando del puente es síncrono | `check-comandos` |
| Toda escritura abre `BEGIN IMMEDIATE` | `check-transacciones` |
| El webview nunca reproduce audio; el audio es del motor de Rust | `check-ui` y [ADR-003](docs/adr/decisions/ADR-003-motor-de-audio.md) |
| Nada sale a la red fuera de `net.rs` ni sin consentimiento | `check-network` |
| Ningún registro contiene rutas, títulos, artistas ni claves | `check-registro` |
| Los secretos van al llavero del sistema | `secrets.rs` con `keyring` |
| Ninguna regresión del contrato móvil | Respuestas doradas en `cargo test` |
| Ningún binario nativo ni modelo entra al repositorio | `.gitignore` y gancho de pre-commit |
| Sin colores literales, desenfoques en cromo permanente, `will-change` ni animación en reposo | `check-ui` |

## 5. Registro y estilo

* **Español**, registro profesional, **sin emojis** en código, documentación ni commits.
* Los comentarios explican **por qué**, no qué. Cuando una decisión no es obvia, dicen qué se descartó y por qué.
* Las pruebas se nombran por la propiedad que verifican, no por la función que llaman.
* Lo que se porta de la V1 cita en un comentario el archivo de origen solo cuando ayuda a entender una regla rara.

## 6. Verificación

Se ejecuta **antes** de dar nada por terminado:

```bash
pnpm verify
cd src-tauri
cargo fmt --all -- --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test
```

Hasta que exista el esqueleto (F0.2.1), la verificación de la V1 es `pytest` desde su carpeta.

## 7. Los corpus reales

| Corpus | Ruta |
|---|---|
| Música | `/home/nathan/Música/biblioteca/` (2.397 MP3, 14 GB) |
| Base de la V1 | `/home/nathan/.local/share/nb_sound/biblioteca/nb_sound.sqlite3` |
| Identidad del servidor móvil de la V1 | `/home/nathan/.config/nb_sound/sync/` |

**Jamás se escribe en esas rutas** durante el desarrollo; se leen en solo lectura. `.claude/settings.json` lo
deniega. Nada derivado de ellas entra al repositorio ni a los registros. Las pruebas que las usan se saltan solas si
no existen.

## 8. Commits

```bash
git commit -s -m "feat(reproductor): cola sin cortes entre pistas (F2.1.2)"
```

* Conventional Commits, firmados con `-s` (DCO), con el identificador de la iteración.
* El cuerpo explica **por qué** y qué se verificó, no lista archivos.
* Cada commit termina con la línea `Co-Authored-By` del modelo que lo escribió.

## 9. Qué hacer sin preguntar

* Ejecutar la verificación y corregir formato, lints y pruebas.
* Escribir pruebas de la lógica añadida y una de regresión por cada defecto.
* Actualizar el documento afectado y la tabla de estado de la fase.
* Registrar en preguntas abiertas lo que no se resuelva.
* Empujar a `origin/main` al terminar una iteración verificada.

## 10. Qué requiere preguntar

* Aprobar o cambiar un ADR, o contradecir la Constitución.
* Añadir una dependencia que no esté en un ADR.
* Ampliar el alcance de una fase o adelantar trabajo de otra.
* Cualquier cambio en NB Sound Mobile.
* Publicar una versión.
