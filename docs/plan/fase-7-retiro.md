# Fase 7: Publicación de la 2.0

> **Objetivo:** que NB Sound 2.0 se publique en las tres plataformas.
>
> **Prerrequisitos:** Fases 1 a 6.

## Estado de la fase

| Iteración | Estado |
|---|---|
| F7.2.1 Instaladores para Linux (AppImage, deb, rpm, tar.gz), Windows (MSI/NSIS) y macOS (dmg) | Hecha a falta de ejecutarla: `.github/workflows/publicacion.yml` compila las tres plataformas con `tauri-action`, empaqueta además el `.tar.gz` de sistema para Linux (`usr/bin`, `usr/lib`, `usr/share`), firma los artefactos del actualizador (`createUpdaterArtifacts` solo ahí), sube `latest.json` y deja la publicación en **borrador**. Ejecutada en cada publicación desde la 2.0.1; en la 2.0.7, 2.0.8 y 2.0.9, los 16 artefactos de las tres plataformas en verde. La puerta de máquina limpia sigue en las pruebas finales |
| F7.2.2 Actualizaciones de la aplicación desde la propia aplicación | Hecha: `tauri-plugin-updater` detrás de la puerta de red, con el servicio Actualizaciones y "Buscar actualizaciones" en Acerca de; firma obligatoria con la clave pública de `tauri.conf.json`. Enmiendas en ADR-001 y ADR-009. El `.tar.gz` firmado de la 2.0.7 a la 2.0.9 se comprobó contra esa clave y se instaló en el equipo de Nathan por el mismo camino que usa la aplicación. Que una 2.0.x real se actualice sola desde Acerca de, a las pruebas finales |
| F7.2.3 Avisos de terceros y atribución de modelos | Hecha: las cinco tipografías, el código portado y los modelos; regenerados con las dependencias del actualizador |
| F7.2.4 Publicación de la 2.0.0 | Hecha: publicada desde la 2.0.0; la última, la 2.0.15 (2026-11-09), tras las [pruebas finales](./pruebas-finales.md) hechas por IA, sin máquina limpia ni Windows y macOS por decisión de Nathan |

## Criterios

* **F7.2.x:** la puerta de empaquetado completa en las tres plataformas, con máquina o CI real. Lo que no se pueda
  comprobar se dice antes de publicar.
