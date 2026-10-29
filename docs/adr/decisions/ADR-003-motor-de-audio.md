# ADR-003: Motor de audio embebido en Rust

**Fecha:** 2026-10-29
**Estado:** Aceptado, sujeto a verificación por F0.4.1

## Contexto

La V1 reproduce con `python-vlc`. Eso obliga a tener VLC instalado o a empaquetar sus plugins; el karaoke mantiene
dos `MediaPlayer` sincronizados por sondeo desde Python; el DJ sostiene dos `vlc.AudioEqualizer` durante cada
transición; el GIL produce microcortes cuando el análisis satura la CPU. MPRIS, implementado a mano sobre Qt D-Bus,
ha necesitado cinco correcciones seguidas de firmas (`a{sv}`, `x`, `qint64`).

Lo que el motor tiene que cubrir, sacado del código de la V1:

* Formatos aceptados hoy: `.mp3 .flac .m4a .wav .ogg .aac` (`config/settings.py`). El corpus real son 2.397 MP3.
* Ecualizador de 10 bandas con las 18 preselecciones de libVLC y preamplificación con margen.
* Karaoke: original e instrumental sincronizados, con conmutación instantánea.
* DJ: cuatro técnicas (`energy_blend`, `eq_kill_bass`, `filter_sweep`, `harmonic_mix` con stems). Ninguna cambia el
  tempo, así que **no hace falta estirar el tiempo** para tener paridad.
* Cola con aleatorio y repetición; las 112 pruebas de `tests/test_reproductor_ui_contract.py` son su especificación.

## Alternativas consideradas

1. **Rodio.** Rechazada: no sincroniza pistas a nivel de muestra ni programa eventos en un reloj.
2. **GStreamer.** Rechazada: vuelve a depender de plugins del sistema, lo contrario de la regla 1.
3. **Motor propio sobre `cpal`.** Viable pero caro; queda como salida si Kira no pasa el prototipo.
4. **Symphonia + Kira sobre `cpal`, detrás de una interfaz `MotorAudio` propia.** Aceptada.

## Decisión

* **Decodificación:** Symphonia 0.6 con `mp3`, `flac`, `aac`, `alac`, `vorbis`, `pcm`, `wav` e `isomp4`. Según su
  tabla oficial, MP3, FLAC, PCM y Vorbis están en "Excellent" con reproducción sin cortes; AAC-LC en "Great" **sin**
  ella; ALAC en "Great" con ella. HE-AAC y Opus figuran como "en desarrollo".
* **Respaldo:** lo que Symphonia no decodifique (HE-AAC, Opus, WMA, APE) se decodifica con el `ffmpeg` que ya viaja
  en el instalador, entregando PCM al mismo motor. El usuario no ve la diferencia.
* **Mezcla:** Kira 0.12 (MIT/Apache-2.0): pistas de mezcla con efectos (`eq_filter`, `filter`, `volume_control`),
  transiciones con curvas, reloj para arrancar sonidos en un instante exacto y sonidos en streaming. El EQ de 10
  bandas son diez `eq_filter` en serie sobre la pista maestra.
* **Controles del sistema:** `mpris-server` 0.11 (MPL-2.0) en Linux; `souvlaki` 0.9 (MIT) en Windows (SMTC) y
  macOS (`MPNowPlayingInfoCenter`).
* **Sonoridad:** `ebur128` (MIT) calcula LUFS al importar; la ganancia se aplica al decodificar.
* Todo el audio vive en el proceso de Tauri: al cerrar la ventana se detiene. El webview nunca reproduce audio, lo
  que además evita el defecto de WebKitGTK con medios servidos desde el esquema propio que NB Books documentó.

## Criterios del prototipo F0.4.1

| Propiedad | Pasa si |
|---|---|
| Sin cortes entre pistas | Al renderizar fuera de línea un álbum en MP3 o FLAC, entre pistas no aparece silencio que no esté en los archivos |
| Seek | Error menor de 10 ms en MP3 con VBR |
| Karaoke | Original e instrumental con deriva de 0 muestras tras 5 minutos; conmutar no produce clic (transición ≥ 20 ms) |
| Ecualizador | Respuesta en frecuencia de las 18 preselecciones dentro de ±0,5 dB de la tabla de la V1 |
| Robustez | Cero vacíos de buffer en 10 minutos de reproducción con todos los núcleos al 100 % |
| Coste | Reproducción normal por debajo del 2 % de un núcleo |

## Consecuencias

- **Positivas:** desaparecen VLC, sus hilos huérfanos y el sondeo del karaoke; MPRIS deja de escribirse a mano.
- **Negativas:** Kira está pensado para juegos; la cola sin cortes se programa con su reloj, no viene hecha.
- **Riesgos:** si Kira no da la precisión necesaria, se sustituye detrás de `MotorAudio` sin tocar nada más.
