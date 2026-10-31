# Cierre de la Fase 7: retiro de la V1 y 2.0 preparada (2026-10-31)

> Evaluación de la [Fase 7](../plan/fase-7-retiro.md) contra sus criterios: la V1 fuera del repositorio, cada fila
> del inventario con su destino, y la 2.0 lista para publicarse en las tres plataformas.

## Resultado

**La Fase 7 se cierra en lo que se puede hacer sin publicar.** Las siete iteraciones están hechas o preparadas. La
2.0.0 no se ha publicado: eso, y lo que solo se comprueba con la instalación real o con máquinas limpias, queda en
manos de Nathan.

| Iteración | Estado | Commit |
|---|---|---|
| F7.1.1 Auditoría de paridad contra el inventario | Hecha | `e9e5c98` |
| F7.1.2 Borrar `legado/` y `docs/v1/` | Hecha: `git ls-files '*.py' '*.qml'` no devuelve nada | `e9e5c98` |
| F7.1.3 Guardián `check-sin-python` sin excepciones | Hecha | `e9e5c98` |
| F7.2.1 Instaladores de las tres plataformas | Hecha a falta de ejecutarla (`publicacion.yml`, en borrador) | `d62be50` |
| F7.2.2 Actualizaciones desde la aplicación | Hecha, con enmiendas en ADR-001 y ADR-009 | `276424f`, `985d605` |
| F7.2.3 Avisos de terceros | Hecha | `65b17e2`, `985d605` |
| F7.2.4 Publicación de la 2.0.0 | Preparada, sin publicar | `cd50bc5` |

Verificación al cerrar: `pnpm verify`, `cargo fmt`, `clippy -D warnings` y `cargo test` (548 pruebas) en verde.

## Lo que falta para publicar

En este orden, todo de Nathan:

1. **Las pruebas finales** con la instalación real y máquinas limpias
   ([pruebas-finales.md](../plan/pruebas-finales.md)): la importación de la V1, el contrato móvil con el teléfono, el
   DJ a oído y con la misma sesión que la V1, A ciegas, y la puerta de empaquetado en las tres plataformas.
2. **P13 (hecho el 2026-10-31):** publicada la Release `agregados-1` con `karaoke-1.zip`, `analisis-1.zip` y `texto-dj-1.zip`, y fijados sus URLs, tamaños y SHA-256 en `src-tauri/src/agregados.rs`.
3. **Empujar la etiqueta `v2.0.0`.** Lanza `publicacion.yml`, que compila, firma y deja un borrador con
   `latest.json`. Es la primera ejecución real del workflow: si falla algo de la firma o del empaquetado, se ve ahí.
4. **Publicar el borrador** en GitHub. Desde ese momento, el actualizador de las instalaciones lo encuentra.

## Riesgos que conviene saber

* **El actualizador nunca se ha probado de punta a punta:** hace falta una 2.0.0 publicada y una 2.0.1 para ver que
  una instalación se actualiza sola. Los paquetes deb y rpm no se actualizan solos (lo hace el gestor de paquetes),
  y la aplicación lo dice.
* **La contraseña de la clave de firma apareció una vez en la salida de un comando** en la sesión local del
  2026-10-31. No está en ningún archivo del repositorio. Si esa salida pudo quedar registrada en algún sitio, lo
  prudente es generar otra clave antes de la primera publicación: una vez publicada una versión firmada, cambiar la
  clave obliga a que las instalaciones existentes se actualicen a mano.
* **macOS con Intel** queda fuera: ONNX Runtime 1.31 no publica binario para esa arquitectura.

## Prompt para la Fase 8

> Lee `CLAUDE.md` y `docs/plan/README.md`. La Fase 7 está cerrada salvo la publicación, que es de Nathan
> (`docs/audit/2026-10-31-cierre-fase-7.md`); no crees etiquetas ni publiques nada. Empieza la
> [Fase 8](../plan/fase-8-nuevas.md). Antes de cada iteración escribe su ficha completa (objetivo, criterio de
> aceptación, dependencias) en `fase-8-nuevas.md` y súbela en su propio commit; F8.5 necesita además un ADR del
> modelo de confianza aprobado por Nathan antes de escribir código, así que plantéalo y no lo empieces. Orden
> sugerido: F8.1 (la forma de onda sale de la pasada de LUFS de F4.1.12), F8.2, F8.3 y F8.4. Cada iteración verificada
> (`pnpm verify`, fmt, clippy y `cargo test`) es un commit firmado con `-s` y se sube al terminar. Anota cada commit
> en `docs/plan/bitacora.md` y lo que solo se compruebe con la instalación real en `docs/plan/pruebas-finales.md`.
> Pregunta antes de añadir una dependencia que no esté en un ADR.
