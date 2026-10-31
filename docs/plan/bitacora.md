# Bitácora de trabajo

> Registro de lo que se hace en cada sesión, en orden: qué se terminó, con qué commit, qué se verificó y qué quedó
> pendiente o decidido por el camino. El estado de cada iteración sigue viviendo **solo** en la tabla de su fase
> ([plan](./README.md), sección 4); esto es el diario que explica cómo se llegó ahí. Cada entrada nueva va al final.

## Cómo se lee

* **Commit**: el identificador corto en la rama de trabajo.
* **Verificado**: lo que pasó antes de subirlo. Salvo que se diga otra cosa, la verificación completa de la
  sección 6 de `CLAUDE.md`: `pnpm verify`, `cargo fmt --check`, `cargo clippy -D warnings` y `cargo test`.
* **Pendiente**: lo que no se pudo comprobar en el entorno de trabajo y se apuntó en
  [pruebas finales](./pruebas-finales.md), o lo que espera una decisión en
  [preguntas abiertas](../contextual/open-questions/README.md).

## 2026-10-30 y 2026-10-31: cierre de la Fase 4

Se retomó desde `3aa802c` (F4.2.2 a medias, subido sin verificar). Todo se trabajó en la rama
`claude/exciting-carson-39m9r0` con el borrador de PR `Nate-1296/NB-SOUND#2`, porque la sesión no podía empujar a
`main`; fusionarlo deja `main` como pide `CLAUDE.md`.

Para compilar en el contenedor hicieron falta las librerías de sistema de Tauri (`libwebkit2gtk-4.1-dev`,
`libgtk-3-dev` y compañía) y `node scripts/fetch-binarios.mjs`, que descarga `fpcalc` y ONNX Runtime fuera del
repositorio.

| Commit | Iteración | Qué se hizo | Pruebas nuevas |
|---|---|---|---|
| `0e80ca2` | F4.2.2 | Carpeta vigilada terminada. Defecto corregido: también se excluye lo que espera en la cola, que dejaba una importación sin terminar. Sin carpeta fijada, espera a la primera importación en vez de exigir reinicio | El vigilante real con `notify` y un álbum copiado en dos tiempos |
| `4993346` | F4.2.7 | Ajustes > Privacidad (interruptor general y por servicio, con lo que envía) e Inteligencia artificial (proveedor, modelo y clave en el llavero, que nunca vuelve al webview). La política se aplica a la puerta en el acto | La política guardada y aplicada; validación del modelo; cuentas del llavero iguales a las del importador de la V1 |
| `f624727` | F4.1.7 | `catalogo/ia.rs`: desempate por IA con el prompt y la validación de `external/ia_client.py`; un lanzamiento fuera de la lista cerrada descarta la respuesta | Lista cerrada, revisión manual, confianza acotada, forma de la petición de cada proveedor, la clave fuera del `Debug` |
| `caac72c` | F4.2.8 | "Completar datos" sin cambiar el `id`. La identificación de la canalización pasa a `identificar_y_decidir`, compartida | La letra añadida sin cambiar el `id`; la fila rehecha y los vacíos borrados |
| `e8dec4f` | F4.2.7 | Los textos de lo que se carga aparte salen del arranque (`es-aparte.ts`): de 248,1 a 246 KB | `check-paquete` |
| `f33c072` | F4.2.5 | Editar pista y álbum sin cambiar `id`; renombrar un álbum conserva su fila y su portada, y solo se junta con otro igual del mismo artista | Renombrar, juntar, cambiar de artista, editar una pista, rechazos |
| `683edb4` | F4.2.5 | Las correcciones (`overrides` de la V1): lo editado se recuerda por huella e ISRC y la importación lo aplica antes de ir a la red, también lo que trajo la V1 | Claves de la V1, orden huella > ISRC > artista y título, importación de punta a punta sin red |
| `02d169a` | F4.2.6 | Copia de seguridad `.nbsound-backup` con el formato de la V1 más la versión de esquema; restaurar valida entera y se aplica al reiniciar; copias automáticas. Entra `zip` (ADR-002) | Ida y vuelta completa; rechazo de una copia de la V1, una más nueva, una dañada y una con ruta trampa |
| `d35ce3b` | F4.1.12 | `rasgos.rs`: el modo `light` de la V1, con el seguidor de pulsos de librosa 0.11 leído en su código y la tonalidad con perfiles de Krumhansl, en el hilo de la sonoridad | Tempo exacto en la rejilla, pulsos cada periodo, tono puro, acordes mayor y menor, preferencias |
| `cba2eef` | Fase 4 | Cierre de lo automático y lo real apuntado en pruebas finales | `check-docs` |
| `6b01e24` | F5.1.1 | P13 registrada: los agregados no están publicados | `check-docs` |

**Decisiones tomadas por el camino.**

* La carpeta vigilada no vigila por su cuenta la carpeta de música del sistema: importaría sin preguntar toda la
  música que ya hubiera en ella.
* "Completar datos" y "Editar datos" ponen las etiquetas en el archivo pero no lo mueven.
* Editar a mano no marca una pista como verificada.
* Restaurar una copia nunca cambia la base con la aplicación abierta.
* Las filas de rasgos que trajo la V1 se respetan; solo se analiza lo que no tiene.
* El recorte de pulsos de librosa 0.11, que quita de más en los extremos, se replica porque es lo que contaba la
  V1.

**Avisos.** El arranque quedó en 248,6 KB de 250: lo próximo de interfaz se carga aparte. `cargo-deny` no está en
el contenedor; las licencias nuevas (MIT y Apache-2.0) se revisaron a mano.

## 2026-10-31: Fase 5

Nathan delegó la decisión sobre P13 y pidió seguir con la Fase 5. Se construye la mecánica de agregados con el
catálogo preparado y sus entradas marcadas como no publicadas: en cuanto haya una Release con los archivos, basta con
rellenar URL, tamaño y SHA-256.

| Commit | Iteración | Qué se hizo | Pruebas nuevas |
|---|---|---|---|
| `832a152` | — | Esta bitácora, con todo lo anterior | `check-docs` |
| `2e037ea` | F5.1.1, F5.1.2 | `agregados.rs`: catálogo compilado sin publicar (P13) e instalación reanudable, verificada y atómica; `Red::descargar` a disco con `Range` | Corte y reanudación, `Range` ignorado, hash alterado, ruta trampa, quitar y reinstalar |
| (siguiente) | F5.1.3 | Ajustes > Agregados con su gestor y progreso. Para dar margen al arranque (249,2 KB de 250), lo del puente que solo usan pantallas diferidas pasa a `$core/ipc/aparte.ts` y Dispositivos se carga aparte: 245,4 KB. Se devuelve a su función un comentario de documentación que una inserción anterior había separado | El gestor con el catálogo sin publicar |
