# Reproductor global — ecualizador y opciones de audio

> Estado: **IMPLEMENTADO**. Ecualizador (18 presets + 10 bandas + preamp) y
> "Estabilizar volumen" (normvol) en `Configuración → Personalización`, aplicando
> **solo al reproductor global**. El DJ Privado no se ve afectado en ningún caso.
>
> Alcance estricto: **solo el reproductor global**. El DJ Privado tiene su
> propia cadena de audio (mezcla/transiciones) y **no se tocó**.

## 0. Resumen de implementación

- **Backend** ([servicios/reproductor.py](../servicios/reproductor.py)):
  constantes verificadas contra libVLC (`EQ_PRESETS`, `EQ_BANDAS_HZ`, rangos),
  funciones puras `bandas_de_preset`/`preamp_de_preset`, estado del EQ + normvol,
  `set_ecualizador_*`, `set_normalizar_volumen`, `_aplicar_equalizer_a_media_player`
  (reaplicado en cada `_reproducir_pista` y en el swap de karaoke), `_crear_media`
  (inyecta normvol per-media) y `_cargar_config_audio` (restaura al arrancar).
  Los **preajustes** se aplican con `libvlc_audio_equalizer_new_from_preset(idx)`
  (API de la librería, balance banda/preamp correcto); solo "Personalizado" arma
  el EQ a mano. Nombres de preajuste en español para la UI (`EQ_PRESET_NOMBRES_ES`,
  conservando géneros sin traducción: Pop, Rock, Reggae, Ska, Techno, Club…).
- **Modelo** ([ui/modelos_qml.py](../ui/modelos_qml.py) · `ModeloReproductor`):
  propiedades reactivas `eq_activo`, `eq_preset` (-1 = Personalizado), `eq_bandas`,
  `eq_preamp`, `normalizar_volumen` + metadatos `eq_presets_nombres`/`eq_bandas_hz`
  /rangos, y slots `set_ecualizador_activo|preset|banda|preamp` y
  `set_normalizar_volumen`. Persisten al instante.
- **UI** ([VistaConfiguracion.qml](../ui/qml/vistas/VistaConfiguracion.qml)):
  subtítulo actualizado + `GrupoConfig` "Ecualizador del reproductor" antes de
  "Tipografía" (toggle, chips de preset + "Personalizado", 10 sliders verticales
  `EqBandaSlider`, slider de pre-amp con `SliderLine`, toggle normvol con nota).
  Las barras se atenúan/deshabilitan con el EQ apagado.
- **Persistencia** (config_ui, sin cambio de esquema): `eq_activo`, `eq_preset`
  (índice o `custom`), `eq_bandas` (JSON 10 floats), `eq_preamp`, `audio_normalizar`.
- **Tests**: [tests/test_reproductor_ecualizador.py](../tests/test_reproductor_ecualizador.py)
  (tabla contrastada contra libVLC, funciones puras, preset→custom, round-trip de
  persistencia, normvol per-media, aislamiento del DJ) y smoke QML en
  [tests/test_ui_configuracion_runtime.py](../tests/test_ui_configuracion_runtime.py).

### Desviación respecto al plan: normvol per-media (no recreación de instancia)

El plan original (§4.2) preveía recrear la instancia VLC para activar normvol.
Al revisar el código se confirmó que **la instancia VLC del reproductor global se
comparte con el DJ** (`ModeloDjPrivado` toma `reproductor._instancia_vlc`). Poner
normvol como arg de instancia (o recrearla) **filtraría el filtro al DJ o lo
rompería**, contra el §5 de este plan. Solución final, validada en vivo: normvol
se aplica **per-media** en el reproductor global vía `media.add_option(":audio-filter=normvol")`
(+ `:norm-max-level`, `:norm-buff-size`). No recrea la instancia; al togglear se
recarga el media actual en su misma posición (micro-corte). El DJ crea sus propios
media y nunca recibe estas opciones.

## 1. Objetivo

Añadir, en `Configuración → Personalización`, una caja nueva con:

- **Ecualizador** estilo Spotify: preajustes (presets) + 10 barras. Si tras
  aplicar un preajuste el usuario mueve una barra, pasa a "Personalizado".
- **Opciones básicas** activables/desactivables que VLC soporta oficialmente
  (estabilizar volumen, etc.).

Y cambiar el subtítulo de la sección.

## 2. Cambio de subtítulo (trivial)

En [VistaConfiguracion.qml](../ui/qml/vistas/VistaConfiguracion.qml#L1726):

```
- "Ajusta tema, tipografía y escala. Esta sección se guarda al instante."
+ "Ajusta tema, tipografía, escala y opciones del reproductor. Esta sección se guarda al instante."
```

## 3. Qué soporta VLC realmente (verificado en este equipo)

libvlc **3.0.20 Vetinari** (binding `python-vlc`). Comprobado de forma empírica
(no son APIs inventadas):

### 3.1 Ecualizador — API de alto nivel, aplicable EN VIVO
- `vlc.AudioEqualizer()` / `libvlc_audio_equalizer_new()`.
- `libvlc_audio_equalizer_new_from_preset(idx)` para cargar un preajuste.
- **18 presets**: `Flat, Classical, Club, Dance, Full bass, Full bass and
  treble, Full treble, Headphones, Large Hall, Live, Party, Pop, Reggae, Rock,
  Ska, Soft, Soft rock, Techno`.
- **10 bandas** (Hz): `31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000`.
- `eq.set_amp_at_index(amp_dB, idx)` y `eq.set_preamp(amp_dB)` (rango típico
  ±20 dB), `eq.get_amp_at_index(idx)`.
- Se aplica al reproductor con `media_player.set_equalizer(eq)` **sin recrear la
  instancia** → ideal para edición en vivo. `set_equalizer(None)` lo desactiva.

### 3.2 Estabilizar volumen — dos mecanismos reales (args de instancia)
Ambos se pasan al **crear** `vlc.Instance(...)`; cambiarlos en caliente exige
**recrear la instancia** (ver §4.2):
- Normalizador de volumen en tiempo real: `--audio-filter=normvol`
  - `--norm-max-level <float>` (nivel máx., p.ej. 2.0)
  - `--norm-buff-size <int>` (nº de buffers para medir potencia, p.ej. 20)
- ReplayGain (usa tags ReplayGain del archivo):
  - `--audio-replay-gain-mode {none,track,album}`
  - `--audio-replay-gain-preamp <float>`, `--audio-replay-gain-default <float>`
  - `--audio-replay-gain-peak-protection`

### 3.3 Otros filtros disponibles (opcionales)
- Compresor de rango dinámico: `--audio-filter=compressor` (+ `--compressor-*`).
- Ganancia global: `--gain <float [0..8]>`.

### 3.4 "Omitir silencios entre canciones" — NO nativo en VLC
VLC **no** tiene un filtro de reproducción que recorte el silencio inicial/final
de cada pista. Lo más cercano es la reproducción **sin huecos** (gapless), que se
gestiona a nivel de cola, no con un filtro. Recomendación: **no prometer** esta
opción como "de VLC". Alternativas, si se desea:
- (a) Reproducción gapless real (encadenado de medios) — trabajo de cola, no de
  filtro.
- (b) Recorte de silencios por análisis de audio (fuera de VLC) — feature aparte.
Para esta caja: incluir solo lo que VLC sí permite (§3.1–3.3).

## 4. Diseño técnico

### 4.1 Ecualizador (vive en el `media_player`, en vivo)
- En `servicios/reproductor.py`:
  - Guardar un `vlc.AudioEqualizer` activo. Métodos nuevos:
    `aplicar_ecualizador(preset_idx|None, bandas: list[float], preamp: float)`,
    `desactivar_ecualizador()`.
  - Reaplicar el EQ tras cada cambio de pista (`_reproducir_pista`) porque
    `set_equalizer` se asocia al media actual; mantener el EQ "pegajoso".
  - Restaurar desde config al arrancar (en `_cargar_estado_persistido`).
- Persistencia (config_ui, sin cambio de esquema):
  - `eq_activo` ("0"/"1"), `eq_preset` (índice o "custom"),
    `eq_bandas` (JSON de 10 floats), `eq_preamp` (float).
- Regla "personalizado": al cargar un preset se rellenan las 10 bandas; si el
  usuario mueve una barra, `eq_preset="custom"` (la UI muestra "Personalizado").

### 4.2 Filtros de instancia (normvol / replaygain) — requieren recrear instancia

> ⚠️ **Superado para normvol** (ver §0): por la instancia compartida con el DJ,
> normvol se implementó **per-media**, no recreando la instancia. Esta sección se
> conserva como referencia de los hechos de VLC y para una eventual opción
> ReplayGain (que sí sería arg de instancia y exigiría otra estrategia).
- `--audio-filter` y `--audio-replay-gain-*` son argumentos de `libvlc_new`; no
  se cambian en caliente. Estrategia: cuando el usuario activa/desactiva
  "estabilizar volumen", **reconstruir** la instancia VLC y el media_player
  reusando el patrón ya probado de cierre/reanudación:
  - Capturar pista + posición actuales (igual que `preparar_cierre` /
    `_guardar_estado_reproduccion`).
  - Recrear instancia con los nuevos args, recrear media_player, reanudar en la
    misma pista/posición (mismo mecanismo de `_reanudar_seg_pendiente`).
  - Reaplicar el ecualizador activo.
- Construir los args en `_inicializar_vlc`
  ([anchor](../servicios/reproductor.py#L193)) leyendo config_ui:
  - `audio_normalizar` ("0"/"1") → añade `--audio-filter=normvol --norm-max-level=… --norm-buff-size=…`.
  - (Opcional) `audio_replaygain_mode` → `--audio-replay-gain-mode=…`.
- Por simplicidad de UX, ofrecer SOLO "Estabilizar volumen" (normvol) como
  toggle en la primera versión; ReplayGain/compresor quedan como ampliación.

### 4.3 Modelo QML
- En `ModeloReproductor`: slots `setEcualizadorPreset(idx)`,
  `setEcualizadorBanda(idx, dB)`, `setPreampEcualizador(dB)`,
  `setEcualizadorActivo(bool)`, `setNormalizarVolumen(bool)` + propiedades
  reactivas (`eqPreset`, `eqBandas`, `eqPreamp`, `eqActivo`, `normalizarVolumen`).
- Persisten al instante (coherente con "se guarda al instante").

### 4.4 UI (respetar la maquetación existente)
- Insertar un `GrupoConfig` nuevo **antes** del de "Tipografía"
  ([anchor](../ui/qml/vistas/VistaConfiguracion.qml#L1733)), justo tras la
  cabecera de la sección.
- Estructura del grupo:
  - Toggle "Ecualizador" (activar/desactivar) con `PillOption`/switch del estilo
    ya usado en la vista.
  - Selector de preajuste: fila de chips (`PillOption`) con los 18 presets +
    "Personalizado". Reusar el patrón de chips de la propia VistaConfiguracion.
  - 10 barras verticales (una por banda) usando
    [SliderLine.qml](../ui/qml/componentes/SliderLine.qml) o un slider vertical
    equivalente; etiqueta de frecuencia bajo cada barra. Mover una barra →
    preset "Personalizado".
  - Pre-amplificación: un slider extra.
  - Toggle "Estabilizar volumen" (normvol) con nota: "reinicia el audio un
    instante al cambiar" (por la recreación de instancia).
- Deshabilitar/atenuar las barras cuando el ecualizador está desactivado.

## 5. Por qué NO toca el DJ Privado
El DJ usa `servicios/dj_privado/reproductor_sesion.py` + `mix_engine.py`, con su
propia instancia/cadena de audio para mezclar y hacer transiciones. El EQ y los
filtros aquí descritos se aplican exclusivamente al `Reproductor` global. No se
debe compartir `AudioEqualizer` ni args de instancia con la sesión DJ.

## 6. Tareas de implementación (cuando se aborde)
1. Subtítulo (§2).
2. Backend EQ en `reproductor.py` (§4.1) + persistencia config_ui.
3. Reaplicar EQ en cada `_reproducir_pista` y restaurar al arrancar.
4. Toggle normvol con recreación de instancia reusando el patrón de reanudación (§4.2).
5. Slots/propiedades en `ModeloReproductor` (§4.3).
6. `GrupoConfig` nuevo en VistaConfiguracion (§4.4), estilo existente.
7. Tests: función pura de mapeo preset→bandas; persistencia round-trip de
   config_ui; que el DJ no se ve afectado; smoke QML de la vista.

## 7. Riesgos / notas
- Recrear la instancia VLC al togglear normvol implica un micro-corte de audio;
  documentarlo en la UI. Si molesta, dejar normvol como opción "al reiniciar".
- `set_equalizer` debe reaplicarse por-media; no es global a la instancia.
- No prometer "omitir silencios" como función de VLC (§3.4).
