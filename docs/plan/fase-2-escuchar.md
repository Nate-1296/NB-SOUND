# Fase 2: Escuchar

> **Objetivo:** que la V2 sea el reproductor de todos los días: la carcasa completa, la biblioteca, las playlists,
> la búsqueda, el reproductor y su integración con el sistema.
>
> **Prerrequisitos:** Fase 1. Contratos: [ADR-003](../adr/decisions/ADR-003-motor-de-audio.md),
> [ADR-007](../adr/decisions/ADR-007-arquitectura-de-informacion.md), [ADR-008](../adr/decisions/ADR-008-sistema-de-diseno.md).

## Estado de la fase

| Iteración | Estado |
|---|---|
| F2.1.1 `MotorAudio` de producción (a partir de F0.4.1) | Hecha |
| F2.1.2 Cola, aleatorio y repetición | Hecha: las 31 pruebas de cola de la V1; el resto de las 112, en su iteración ([contrato](../engineering/contrato-reproductor.md)) |
| F2.1.3 Ecualizador con las 18 preselecciones y preamplificación con margen | Hecha |
| F2.1.4 Normalización de volumen por LUFS | Hecha: medida, ganancia y medición de la biblioteca en segundo plano (`medicion.rs`, tabla `sonoridad` de V8) |
| F2.1.5 Controles del sistema: MPRIS, SMTC y macOS | Hecha: lo de Windows y macOS solo se compila en el CI |
| F2.1.6 Atajos globales, bandeja y cierre limpio | Hecha: los atajos son los de la ventana de la V1; las teclas multimedia, por F2.1.5 |
| F2.1.7 Servicio de reproducción: cola, motor, sesión guardada, historial y avisos al puente | Hecha |
| F2.2.1 Carcasa con la disposición de la V1: barra lateral, barra superior con búsqueda, barra de reproducción | Hecha |
| F2.2.2 Inicio | Hecha: Sorpréndeme llega con las recomendaciones (F5.3.3) |
| F2.2.3 Biblioteca: canciones, álbumes, artistas y sus detalles | Hecha |
| F2.2.4 Playlists manuales (crear, ordenar, añadir desde cualquier sitio) | Hecha |
| F2.2.5 Búsqueda global y `Ctrl+K` | Hecha |
| F2.2.6 Reproducción expandida, letras sincronizadas y minirreproductor | Hecha |
| F2.2.7 Los 63 temas de la V1 completos, la tipografía elegible y el color por portada como opción | Hecha: el selector, en Ajustes (F2.2.9) |
| F2.2.8 Tu música (identidad, ánimo del día, actividad) con los datos ya migrados | Hecha: el resumen anual llega con las recomendaciones (F5.3.3) |
| F2.2.9 Ajustes: Biblioteca, Reproducción, Apariencia, Acerca de | Hecha |

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
* **Todas las vistas de F2.2** se comparan con su captura de la V1 (`legado/assets/screens/`): misma disposición y
  mismos elementos, salvo lo que ADR-007 rediseña.
* **F2.2.x:** recorridos de Playwright de cada destino sin errores de consola (aserción en `afterEach`, como en NB
  Books); `check-ui` y `check-paquete` pasan; la biblioteca real se desplaza sin fotogramas largos en WebKitGTK.

**Al cerrar la fase** la V2 se usa a diario para escuchar. **Puerta de empaquetado.**
