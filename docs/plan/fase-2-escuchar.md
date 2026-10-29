# Fase 2: Escuchar

> **Objetivo:** que la V2 sea el reproductor de todos los días: la carcasa completa, la biblioteca, las playlists,
> la búsqueda, el reproductor y su integración con el sistema.
>
> **Prerrequisitos:** Fase 1. Contratos: [ADR-003](../adr/decisions/ADR-003-motor-de-audio.md),
> [ADR-007](../adr/decisions/ADR-007-arquitectura-de-informacion.md), [ADR-008](../adr/decisions/ADR-008-sistema-de-diseno.md).

## Estado de la fase

| Iteración | Estado |
|---|---|
| F2.1.1 `MotorAudio` de producción (a partir de F0.4.1) | Pendiente |
| F2.1.2 Cola, aleatorio y repetición | Pendiente |
| F2.1.3 Ecualizador con las 18 preselecciones y preamplificación con margen | Pendiente |
| F2.1.4 Normalización de volumen por LUFS | Pendiente |
| F2.1.5 Controles del sistema: MPRIS, SMTC y macOS | Pendiente |
| F2.1.6 Atajos globales, bandeja y cierre limpio | Pendiente |
| F2.2.1 Carcasa: barra lateral, barra superior con búsqueda, barra de reproducción | Pendiente |
| F2.2.2 Inicio | Pendiente |
| F2.2.3 Biblioteca: canciones, álbumes, artistas y sus detalles | Pendiente |
| F2.2.4 Playlists manuales (crear, ordenar, añadir desde cualquier sitio) | Pendiente |
| F2.2.5 Búsqueda global y `Ctrl+K` | Pendiente |
| F2.2.6 Reproducción expandida, letras sincronizadas y minirreproductor | Pendiente |
| F2.2.7 Color por portada | Pendiente |
| F2.2.8 Tu música (identidad, ánimo del día, actividad) con los datos ya migrados | Pendiente |
| F2.2.9 Ajustes: Biblioteca, Reproducción, Apariencia, Acerca de | Pendiente |

## Criterios

* **F2.1.2:** las 112 pruebas de `legado/tests/test_reproductor_ui_contract.py` se traducen a pruebas de Rust y
  pasan, incluida la regresión del 2026-10-29 (con aleatorio, la cola nueva arranca en la pista elegida).
* **F2.1.3:** las cifras de `legado/tests/test_reproductor_ecualizador.py` se reproducen; sin recorte a ningún
  volumen.
* **F2.1.4:** dos pistas con 10 LU de diferencia suenan con menos de 1 LU de diferencia con la opción activa.
* **F2.1.5:** KDE Plasma y GNOME muestran título, artista, portada, duración y posición, y sus botones controlan la
  aplicación; aleatorio y repetición se reflejan en los dos sentidos. Lo que no se pueda comprobar en Windows o
  macOS se dice.
* **F2.1.6:** cerrar la ventana durante la reproducción no deja audio sonando ni procesos (prueba de cierre).
* **F2.2.x:** recorridos de Playwright de cada destino sin errores de consola (aserción en `afterEach`, como en NB
  Books); `check-ui` y `check-paquete` pasan; la biblioteca real se desplaza sin fotogramas largos en WebKitGTK.

**Al cerrar la fase** la V2 se usa a diario para escuchar. **Puerta de empaquetado.**
