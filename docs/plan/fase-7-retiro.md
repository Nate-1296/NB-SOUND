# Fase 7: Retiro de la V1 y publicación de la 2.0

> **Objetivo:** que no quede nada de la V1 en el repositorio y que NB Sound 2.0 se publique en las tres plataformas.
>
> **Prerrequisitos:** Fases 1 a 6.

## Estado de la fase

| Iteración | Estado |
|---|---|
| F7.1.1 Auditoría de paridad contra el [inventario de la V1](../contextual/inventario-v1.md) | Hecha: cada fila con su estado; la auditoría de la biblioteca, que faltaba, rediseñada en `catalogo/auditoria.rs`. Las automáticas de la V1 se regeneran con las inteligentes de F8.2 |
| F7.1.2 Borrar `legado/` y `docs/v1/` | Hecha: también los prototipos de Python y el generador de temas; `git ls-files "*.py" "*.qml"` no devuelve nada. Los enlaces apuntan a la etiqueta `v1.1.16` |
| F7.1.3 Borrar el guardián `check-sin-python` y sus excepciones, que ya no tienen sentido | Hecha: se quitaron las excepciones; el guardián se queda, sin ninguna y también para `.qml`, porque es el mecanismo del innegociable de CLAUDE.md |
| F7.2.1 Instaladores para Linux (AppImage, deb, rpm), Windows (MSI/NSIS) y macOS (dmg) | Pendiente |
| F7.2.2 Actualizaciones de la aplicación desde la propia aplicación | Hecha: `tauri-plugin-updater` detrás de la puerta de red, con el servicio Actualizaciones y "Buscar actualizaciones" en Acerca de; firma obligatoria con la clave pública de `tauri.conf.json`. Enmiendas en ADR-001 y ADR-009. Que una 2.0.x real se actualice sola, a las pruebas finales |
| F7.2.3 Avisos de terceros y atribución de modelos | Hecha: las cinco tipografías, el código portado (songrec, librosa, difflib y la V1) y los modelos; regenerados con las dependencias del actualizador |
| F7.2.4 Publicación de la 2.0.0 | Pendiente |

## Criterios

* **F7.1.1:** cada fila del inventario está Hecha, Rediseñada (con enlace a su ADR) o Eliminada (con motivo).
* **F7.1.2:** `git ls-files '*.py' '*.qml'` no devuelve nada.
* **F7.2.x:** la puerta de empaquetado completa en las tres plataformas, con máquina o CI real. Lo que no se pueda
  comprobar se dice antes de publicar.
