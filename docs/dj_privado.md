# DJ Privado — Arquitectura, decisiones y contratos

> Sistema musical conversacional con director automático, scheduler
> perceptual y motor de mezcla real. NO es chatbot ni búsqueda en lenguaje
> natural: traduce intención del usuario a estructura musical controlable
> y la convierte en una sesión continua, mezclada como lo haría un DJ.

---

## 1. Visión

El DJ Privado convierte expresiones perceptuales —"algo cinematográfico
con voces femeninas", "subida progresiva para entrenar", "elegante para
conducir de noche"— en sesiones musicales coherentes y **mezcladas en
vivo** sobre la biblioteca local.

No es un reproductor con crossfade. Es un director automático que:

1. Interpreta la intención del usuario.
2. Selecciona pistas que la cumplen.
3. Decide CÓMO se mezclan unas con otras (qué técnica DJ aplicar a cada
   transición, cuánto solapamiento, qué hacer con bajos/agudos).
4. Reproduce respetando puntos óptimos de entrada y salida de cada pista
   (no las toca completas: toma segmentos).

Es determinístico, interpretable, rápido, sin descargas, sin LLMs.

---

## 2. Filosofía arquitectónica

| Principio                  | Implementación                                              |
|----------------------------|-------------------------------------------------------------|
| Determinismo               | Parser de intent reglas-basadas + scheduler con semilla     |
| Interpretabilidad          | Cada decisión anota razones (`+vocal_focus(+0.63)`, `peak con BPM cercano -> hard_cut`) |
| Fallback graceful          | Embeddings opcionales, librosa opcional, Demucs opcional    |
| Hardware-aware             | Perfil HIGH/MID/LOW detectado por benchmark; cada perfil habilita técnicas distintas |
| Inicio rápido              | Análisis pesado es asíncrono; audio empieza en < 3 s        |
| No invade UI global        | Audio exclusivo: si DJ está activo, el reproductor normal está en pausa real |
| Reutilización              | Stems del subsistema karaoke se aprovechan para mezcla vocal |

---

## 3. Mapa de componentes

```text
servicios/dj_privado/
├── ontologia.py        # Conceptos, ejes, aliases, contradicciones
├── intencion.py        # IntentMusical estructurado (parser + JSON)
├── embeddings.py       # Provider determinista + ONNX opcional
├── persistencia.py     # CRUD sesiones, eventos, candidatos
├── scheduler.py        # Scoring multi-eje, curva de energía, diversidad
├── narrativa.py        # Perfil de fases warmup/groove/peak/release/cooldown
├── transiciones.py     # Camelot, BPM, key compat; refinamiento de orden
├── constructor.py      # Construcción progresiva por bloques
├── servicio.py         # DjPrivadoService (orquestador)
├── ownership.py        # Quien tiene el audio (global vs DJ)
├── reproductor_sesion.py    # Reproductor propio aislado (dos decks VLC)
├── hardware_profile.py      # Benchmark + clasificación HIGH/MID/LOW
├── mix_engine.py            # Selección de técnica, mix points, EjecutorMezcla
├── stems_karaoke.py         # Adaptador a karaoke como fuente de stems sin voz
├── stems_prefetch.py        # Pre-fetch agresivo encolando jobs karaoke
└── errores.py
```

### 3.1 Flujo de datos

```text
prompt usuario
   │
   ▼
ontologia.buscar_conceptos       (frontera de palabra, longitud descendente)
   │
   ▼
intencion.parsear_intent         (negaciones, contradicciones, focos)
   │
   ▼
IntentMusical (axes, focos, exclusiones, curva, estilo)
   │
   ▼
narrativa.construir_perfil       (fases warmup/groove/peak/release/cooldown)
   │
   ▼
persistencia.cargar_candidatos
   │
   ▼
scheduler.planificar_sesion      (scoring multi-eje + bonus focos + curva)
   │
   ▼
transiciones.refinar_orden       (swaps locales que mejoran vecinas)
   │
   ▼
constructor.bloque_a_rows  →  persistencia.insertar_pistas_sesion
   │
   ▼
ReproductorSesionDj.cargar_sesion
   │   • puebla mix_in_seg / mix_out_seg por BPM
   │   • lanza pre-fetch de stems en background
   ▼
play()
   │
   ▼
Bucle de polling cada 50 ms:
   • si quedan ≤ overlap segundos antes de mix_out_seg → arrancar transición
   • mix_engine.preparar_transicion() decide técnica concreta + ruta de B
   • EjecutorMezcla mantiene los dos vlc.AudioEqualizer durante el overlap
   • al completar, swap de decks y avanzar
```

---

## 4. Ontología musical (resumen)

`ontologia.py` define **55+ conceptos** por `role` (`context`, `priority`,
`modifier`, `exclusion`) y **24 ejes perceptuales** ortogonales en [0, 1].

Cada concepto declara `aliases`, `axes`, `perceptual_weight`,
`contradicts`. `buscar_conceptos(texto)` aplica greedy por longitud
descendente con frontera de palabra y sin solapamientos.

Las contradicciones se resuelven por `perceptual_weight` y, en empate,
por orden de aparición (el último mencionado gana). El intent reporta las
contradicciones detectadas.

---

## 5. IntentMusical

`intencion.parsear_intent(prompt, duracion_minutos)` retorna una
`IntentMusical` (dataclass) con `axes`, `focos`, `exclusiones`,
`generos_excluidos`, `curva_energia`, `estilo_transicion`,
`contradicciones`, `notas` y `resumen`.

Las negaciones se detectan por proximidad: lista de negadores (`sin`,
`evita`, `no quiero`...) con ventana de 4 palabras y ruptores (`pero`,
`con`, `aunque`) que cortan el alcance.

El intent se serializa a JSON y se persiste en `dj_sesiones.intent_json`.

---

## 6. Narrativa y fases

`narrativa.construir_perfil(intent)` produce una lista de
`SessionPhase` con `start_t`, `end_t` (tiempo normalizado [0, 1]) y
objetivos por eje. Cinco fases canónicas:

- `warmup` — apertura, energía media-baja
- `groove` — ritmo establecido
- `peak` — clímax
- `release` — descenso del pico
- `cooldown` — cierre

Las proporciones varían según `curva_energia` (`progressive`, `peak`,
`descending`, `wave`, `stable`). El mix engine consulta la fase actual
para decidir técnicas: en `peak` con BPM similares se prefiere `HARD_CUT`,
en `release`/`cooldown` se prefiere `ENERGY_BLEND` (fundido largo), etc.

---

## 7. Scheduler (resumen)

`scheduler.planificar_sesion` extrae ejes de cada pista desde
`track_audio_features` + `track_deep_audio_features` + `track_vibe_tags`
(fallback NEUTRAL=0.5 cuando hay datos parciales), calcula score por
alineación con el intent + bonus por focos + adherencia a curva de
energía, aplica diversidad por artista y devuelve un ordenamiento. La
semilla controla los desempates.

`transiciones.refinar_orden_para_transiciones` aplica swaps locales que
mejoran la suma de scores entre vecinas (greedy, converge en ≤8 iter).

---

## 8. Mix Engine

`mix_engine.py` es el motor de mezcla real. Tres capas:

### 8.1 Cálculo de mix points

Cada pista tiene dos puntos críticos:

- `mix_in_seg`: dónde "entrar" al reproducir (el deck inactivo hace seek
  a este offset antes de play). Salta intros.
- `mix_out_seg`: cuándo arrancar el fade hacia la siguiente. La sesión
  no toca la pista entera: arranca la transición saliente aquí.

Tres estrategias en orden de preferencia:

1. **Por BPM** (rápido y determinista, `O(N)` sin I/O):
   - Intro = 16 beats
   - Outro = 32 beats
   - Garantiza ≥60% de la pista entre ambos puntos
2. **Por RMS** (librosa, opt-in): detecta valles de energía al inicio y
   final para definir mix-in/out reales.
3. **Default**: 8 s / 12 s para pistas largas; sin recorte para cortas
   (< 60 s).

Los mix points se cachean en memoria por pista.

### 8.2 Selección de técnica

`seleccionar_tecnica(plan_transicion, perfil, fase_narrativa, bpm_a,
bpm_b, stems_listos)` devuelve una `TecnicaMezcla` y razones. Reglas en
orden de prioridad:

1. **`peak` con BPM iguales (±2)** → `HARD_CUT` (corte seco en el beat).
2. **`release` o `cooldown`** → `ENERGY_BLEND` (fundido largo, equal-power).
3. **Perfil hardware HIGH/MID + stems listos + armonía buena (key+BPM)** →
   `HARMONIC_MIX` (superposición con versión sin voz en una de las dos
   pistas).
4. **BPM cercano (factor ≥0.75)** → `EQ_KILL_BASS` (baja graves de A,
   sube graves de B durante el overlap).
5. **Default** → `FILTER_SWEEP` (high-pass gradiente en A, low-pass en B).

### 8.3 Curvas de volumen y EQ

Funciones puras `curva_volumen(tecnica, progreso)` y
`curva_eq(tecnica, progreso)` devuelven, respectivamente, `(vol_a, vol_b)`
en [0, 1] y `(amps_a, amps_b)` con 10 ganancias en dB para el ecualizador
ISO de libVLC (bandas 31 Hz - 16 kHz).

`EjecutorMezcla` mantiene dos instancias `vlc.AudioEqualizer` activas
durante el overlap, las asigna a cada deck y las actualiza cada tick
(~50 ms). Al terminar la transición, las libera.

### 8.4 Etiquetas humanas

Cada `TecnicaMezcla` tiene una etiqueta para UI (`etiqueta_humana`):

| Técnica         | Etiqueta UI                |
|-----------------|----------------------------|
| `HARD_CUT`      | Corte en el beat           |
| `ENERGY_BLEND`  | Fundido largo              |
| `EQ_KILL_BASS`  | Mezclando con ecualización |
| `FILTER_SWEEP`  | Barrido de filtros         |
| `HARMONIC_MIX`  | Fundiendo capas            |

El identificador técnico nunca se muestra al usuario.

---

## 9. Hardware profile

`hardware_profile.py` clasifica el equipo en tres perfiles:

- **HIGH**: Demucs procesa 10 s en < 15 s (factor < 1.5×). Habilita
  todas las técnicas.
- **MID**: factor entre 1.5× y 5×. Habilita HARMONIC_MIX solo cuando los
  stems ya están en disco.
- **LOW**: factor > 5× o Demucs no disponible. Solo técnicas vía libVLC.
  No es un modo degradado: las técnicas de EQ y filtros son DJ-grade
  válidas por sí mismas; sólo prescinde de la separación vocal.

En HIGH y MID el motor exige que el stem ya esté en disco para activar
HARMONIC_MIX; nunca espera al pre-fetch en runtime, así no arriesga la
transición. Si falta, degrada a otra técnica sin avisar al usuario.

El benchmark:

- Se ejecuta una sola vez en un hilo daemon al primer uso del DJ.
- No bloquea el inicio: mientras corre, el motor opera en LOW.
- Sintetiza 10 s de audio con espectro variado y mide la inferencia de
  Demucs (sin contar el load del modelo).
- Persiste el resultado en `config_ui` (clave `dj_privado_perfil_hardware`).

Cuando termina, el mix engine recibe el perfil nuevo vía callback y la
siguiente transición ya usa las técnicas correctas.

---

## 10. Pre-fetch de stems

`stems_prefetch.py` encola en background la generación de instrumentales
para las primeras pistas de la sesión. Aprovecha la cola persistente del
subsistema karaoke (`karaoke_jobs`, worker `WorkerKaraokeCola`).

- En LOW no encola nada (HARMONIC_MIX no se va a usar).
- En MID/HIGH encola las primeras 5 pistas.
- Es idempotente: si la pista ya tiene su instrumental o ya hay job
  activo, se ignora.
- El `StemsKaraokeProvider` lee `pistas.karaoke_ruta_instrumental` y
  valida el archivo en disco antes de declarar "stems listos".

Si el procesamiento aún no terminó cuando llega el momento de la
transición, el mix engine degrada a otra técnica sin avisar al usuario.

---

## 11. Reproductor de sesión

`reproductor_sesion.py` (`ReproductorSesionDj`) es un reproductor propio
basado en **dos decks VLC** (A y B). Aislado del reproductor global.

### 11.1 State machine

```text
detenido → preparando → reproduciendo
              ↓               ↓
           pausado ←  transicionando  → finalizado/error
```

### 11.2 Carga de sesión

`cargar_sesion(sesion_id)`:

1. Lee pistas + BPM desde BD.
2. Extrae el perfil narrativo del `resumen_json` de la sesión.
3. Pobla `mix_in_seg` / `mix_out_seg` de cada pista usando BPM
   (mix engine, sin I/O, sin librosa).
4. Construye un prefijo de duraciones acumuladas para que el polling
   calcule la posición global de la sesión en O(1) por tick.
5. Lanza `pre_fetch_inicial_async` para stems en background.

### 11.3 Bucle de transición

El hilo de polling `dj_sesion_loop` se inicia al primer `play()` y vive
hasta que el estado pasa a un terminal (`detenido`, `finalizado`,
`error`) o `close()`. Garantías:

- Sólo existe un hilo de polling a la vez (`_iniciar_hilo_polling_locked`
  es no-op si ya hay uno vivo).
- Espera ticks con `_stop_event.wait(0.05)`, no con `sleep`: responde al
  cierre en menos de un tick.
- Cada ciclo toma el lock una sola vez, decide acciones, y emite el
  progreso a la UI FUERA del lock para evitar deadlocks con slots Qt
  reentrantes.

Cuando quedan ≤ `overlap_seg` segundos antes del `fin_efectivo`:

```python
fin_efectivo = min(
    duracion_natural,
    mix_out_seg,    # punto óptimo de salida del mix engine,
                    # sólo si hay siguiente pista
)
```

Para la última pista del set se ignora `mix_out_seg`: toca hasta su
final natural y luego pasa a estado `finalizado`. El reproductor global
queda en pausa: nunca reanuda automáticamente al terminar el DJ.

El motor consulta `mix_engine.preparar_transicion(...)` con la fase
narrativa actual y obtiene un `PlanMezcla`:

```python
@dataclass(frozen=True)
class PlanMezcla:
    tecnica:                 TecnicaMezcla
    overlap_seg:             float
    mix_out_a_seg:           float
    mix_in_b_seg:            float
    ruta_audio_b_override:   Optional[str]  # stem sin voz si HARMONIC_MIX
    usa_eq:                  bool
    razones:                 tuple[str, ...]
    etiqueta_ui:             str
```

Si la técnica es HARMONIC_MIX con stems listos, el deck inactivo carga
el MP3 instrumental en vez de la mezcla original. Hace seek a
`mix_in_b_seg` (saltar intro) y empieza a sonar a volumen 0.

Durante el overlap el `EjecutorMezcla` modula volumen y EQ cada tick.

### 11.4 Lifecycle de transición

El ejecutor (`EjecutorMezcla`) **se libera siempre** al terminar o
cancelar una transición, en todos los puntos de salida:

- `_tick_transicion_locked` al completar (progreso ≥ 1.0).
- `_saltar_a_locked` (next/prev/saltar_a).
- `buscar_posicion_global` (seek absoluto).
- `_detener_interno`, `_finalizar_locked`.

Esto garantiza que los `vlc.AudioEqualizer` se desconectan
(`set_equalizer(None)`) y los volúmenes se devuelven al objetivo.

---

## 12. Ownership del audio

El sistema garantiza que **solo un motor toca audio a la vez**: el
reproductor global (música normal, búsqueda, playlists, karaoke) o el
reproductor DJ. `dj_privado/ownership.py::SessionOwnershipManager`
encapsula la transición.

```text
GLOBAL  ─── adquirir_para_sesion(N) ───►  SESION_DJ(N)
SESION_DJ(N)  ─── liberar() ──────────►  GLOBAL
SESION_DJ(N)  ─── transferir(M) ──────►  SESION_DJ(M)   (sin pasar por GLOBAL)
```

Es idempotente y la única vía para llamar `Reproductor.set_modo_dj()`.

### 12.1 Comportamiento ante acciones del usuario

| Acción del usuario | Qué pasa |
|---|---|
| Iniciar reproducción DJ | Adquirir ownership → global pausa real, snapshot de posición guardado |
| Sesión finaliza naturalmente | Liberar ownership → posición global restaurada, **pero queda en pausa**: no hay auto-play |
| "Cerrar sesión" (botón) | Detener motor DJ + liberar ownership + limpiar el estado visible para mostrar el empty state |
| Cargar otra sesión del historial mientras hay DJ activo | Detener DJ + liberar; cargar la nueva |
| Construir nueva sesión vía chat mientras hay DJ activo | NO se reemplaza la sesión sonando; la nueva queda visible en el historial |
| Eliminar la sesión que está sonando | Detener DJ + liberar; eliminar de BD |
| Reproducir pista global, agregar a cola, etc. | Liberar DJ primero (callback pausa el motor DJ conservando posición) |
| Volver al DJ y darle play tras reproducir algo global | Readquirir ownership y reanudar desde la posición exacta donde quedó |

Estos comportamientos se conectan en `main_ui.construir_modelos`:
`ModeloReproductor.set_ownership_dj(...)` recibe el manager y todos los
slots de reproducción (`reproducir`, `pausar_reanudar`,
`reproducir_cola_desde_pistas`, `reproducir_indice_cola`) lo llaman
antes de tocar audio.

Cuando una sesión DJ pierde ownership (porque algo más reproduce), el
motor se **pausa** en lugar de detenerse: los decks VLC conservan su
media y posición. `dj_play_pause` reconoce el caso "pausado sin
ownership" y readquiere el ownership antes del toggle, permitiendo
reanudar desde el segundo exacto.

---

## 13. Persistencia (esquema BD)

Tablas (todas `CREATE IF NOT EXISTS`, migración ligera vía
`_aplicar_migraciones_ligeras` con ALTER TABLE condicional):

```sql
dj_sesiones (
    id, prompt_original, intent_json, objetivo_minutos, estado,
    motor_version, semilla, notas, resumen_json, playlist_id,
    creado_en, actualizado_en, finalizado_en
)
dj_pistas_sesion (
    sesion_id, posicion (PK compuesta), pista_id,
    score_total, score_intent, score_transicion, score_curva,
    razones_json, transicion_json, estado, bloqueada
)
dj_eventos (id, sesion_id, pista_id, tipo, payload_json, creado_en)
dj_concepto_emb / dj_track_emb / dj_preferencias
```

**Decisión consciente**: `mix_in_seg`, `mix_out_seg`, técnica de mezcla
y ruta de stems **NO se persisten** en BD. Se calculan en runtime cada
vez que se carga una sesión (mix points por BPM son `O(N)` sin I/O; la
técnica concreta depende del perfil hardware actual y de los stems
disponibles ahora, que son volátiles). Esto evita invalidaciones de
caché y simplifica el flujo.

La duración objetivo es una **sugerencia** para el scheduler (cuántas
pistas elegir), no un trim duro: el reproductor toca cada pista hasta
su `mix_out_seg` (si hay siguiente) o su final natural, sin truncar.

---

## 14. UI (vista DJ Privado)

`ui/qml/vistas/VistaDJPrivado.qml` orquesta tres tabs:

- **Construir**: prompt, chips detectados en vivo, slider de duración y
  CTA. Overlay "Preparando tu mezcla…" no bloqueante (con botón
  "Continuar sin esperar" que esconde el overlay sin abortar la
  construcción) mientras el constructor trabaja.
- **En sesión** (`DjSesionActiva.qml`):
  - Reproductor con play/pause/next/prev y "Cerrar sesión".
  - Chip persistente con la **etiqueta humana** de la técnica activa
    durante una transición (parpadea suavemente).
  - Timeline horizontal con bandas de fase (warmup/groove/peak/...) y
    una **franja translúcida que muestra la zona de overlap** durante
    una mezcla activa.
  - Header contextual con prompt y duración real.
  - Lista de pistas con razones, energía visual, estado (escuchada,
    omitida, intocable) y acciones por pista.
- **Historial** (`DjHistorial.qml`): tabla de sesiones con filtros, buscador y
  acciones (Reproducir, Abrir, Generar variante, Eliminar). Confirmación
  de borrado con texto contextual ("Sí, borrar esta sesión" /
  "No, conservarla").

### 14.1 Patrón de modales

Los popups del DJ siguen el patrón canónico de `VistaConfiguracion`:
`Popup` modal con background propio, padding 18, título 16/DemiBold,
descripción 12 textoSec, botones locales (no `standardButtons`). Esto
los hace visualmente coherentes con el resto de la app.

### 14.2 Textos orientados a acción humana

- Estado del reproductor: "Sonando tu sesión · tu música normal está en
  pausa mientras tanto".
- Fase activa: "Ya entraste en calor, ahora viene lo bueno" (no
  "groove").
- Confirmación de borrado: "Sí, borrar esta sesión" (no "Confirmar").
- Header de pistas: "Tu sesión de 45 min · 12 pistas · '…'" (no "Lo
  que vas a escuchar").

Ningún identificador interno (`mix_armonico`, `score`, columnas BD) es
visible al usuario.

---

## 15. Cleanup al cerrar la aplicación

`main_ui.py` conecta `app.aboutToQuit` con un cleanup que llama a
`ModeloKaraoke.cerrar()` y `ModeloDjPrivado.cerrar()`. Cada uno:

- **Karaoke**: pide `requestInterruption()` al `WorkerKaraokeCola` y
  espera hasta 5 s. La cancelación es cooperativa (entre chunks de
  Demucs).
- **DJ Privado**: llama `ReproductorSesionDj.close()` (cierra los dos
  decks VLC y para el hilo de polling) y pide quit + wait al worker de
  construcción de sesión.

Sin este cleanup Qt aborta al salir con `QThread: Destroyed while thread
is still running`.

---

## 16. Tests

Cobertura del subsistema DJ Privado:

| Archivo | Cubre |
|---|---|
| `test_dj_privado_ontologia.py` | Búsqueda, frontera de palabra, contradicciones, aliases extendidos |
| `test_dj_privado_scheduler.py` | Scoring, curvas, diversidad, semilla |
| `test_dj_privado_integracion.py` | E2E con BD real + biblioteca sintética |
| `test_dj_refactor_profundo.py` | Duración efectiva, ownership manager, contratos |
| `test_dj_reproductor_sesion.py` | State machine, mix points poblados, pre-fetch encolado |
| `test_dj_mix_engine.py` | Mix points (BPM/RMS/default), selección, curvas, EQ, plan, ejecutor, degradación |
| `test_dj_hardware_profile.py` | Clasificación, persistencia, idempotencia, no-reentrancia |
| `test_dj_stems_prefetch.py` | Perfiles, filtrado, async, fail-soft |

La calidad subjetiva del audio (cómo "se siente" una transición real)
no se cubre con tests automatizados — requiere validación humana.

---

## 17. Cómo extender

### 17.1 Añadir un concepto

En `ontologia.py`, dentro de `CONCEPTOS`:

```python
Concepto(
    "lo_fi", aliases=("lo-fi", "lofi", "lo fi"),
    axes={"calmness": 0.5, "brightness": -0.2,
          "electronic_weight": 0.3, "rhythmic_density": -0.2},
    perceptual_weight=1.1,
    role="priority",
    genres=("lo-fi",),
),
```

Disponible inmediatamente para detección, intent y embeddings.

### 17.2 Añadir una técnica de mezcla

1. En `mix_engine.TecnicaMezcla` añadir el valor.
2. En `ETIQUETAS_HUMANAS` mapear texto humano.
3. Implementar la rama correspondiente en `curva_volumen` y, si toca EQ,
   en `curva_eq`.
4. Ajustar `seleccionar_tecnica` y `overlap_recomendado` para decidir
   cuándo activarla.
5. Si requiere stems, considerar pre-fetch en `stems_prefetch.py`.

### 17.3 Añadir un perfil hardware

Editar `UMBRAL_HIGH_FACTOR` / `UMBRAL_MID_FACTOR` o, para una categoría
nueva, extender `PerfilHardware` y `tecnicas_habilitadas`. La
clasificación es lineal en `factor_tiempo_real`.

### 17.4 Cambiar el peso de las reglas de selección

`seleccionar_tecnica` es código procedural de reglas en orden. Cambiar
prioridades es reordenar los `if`. Cada decisión devuelve razones
("`peak con BPM iguales -> hard_cut`") visibles en `_transicion_activa`
y serializables, lo que facilita auditar resultados subjetivos.

---

## 18. Decisiones técnicas explicadas

### 18.1 Por qué libVLC equalizer y no filtros de cutoff dinámicos

`python-vlc` expone un ecualizador ISO de **10 bandas fijas** (31 Hz a
16 kHz). Cubre `EQ_KILL_BASS` de forma directa (bajar bandas 0-2) y
permite aproximar `FILTER_SWEEP` con gradiente de ganancias. No hay
cutoff dinámico real, pero la diferencia auditiva en un overlap de 5-8 s
es marginal y el coste es: cero (la API ya está en el binario VLC del
sistema).

Antes de usarlo se verificó en runtime que `audio_equalizer_new`,
`audio_equalizer_set_amp_at_index` y `media_player.set_equalizer`
funcionan en este entorno (regla "no inventar APIs").

### 18.2 Por qué stems pre-renderizados y no separación en vivo

Demucs tarda 30-90 s por pista en CPU típica. Hacer la separación
durante la transición es inviable (la transición sería muda). El
subsistema karaoke ya genera y persiste el instrumental sin voz; el DJ
lo reutiliza vía `StemsKaraokeProvider` y, si falta para una pista,
encola un job al cargar la sesión para que esté listo cuando llegue.

### 18.3 Por qué mix points en runtime y no persistidos

El mix-in/mix-out depende de la pista (BPM) y el cálculo por BPM es
O(N) sin I/O. Persistirlos en BD obligaría a invalidar si cambia el
audio o el análisis. La selección de técnica además depende del perfil
hardware actual, la fase narrativa real (que depende de la duración
final con los recortes), y los stems disponibles ahora — todos
volátiles. Recalcular es más barato que mantener una caché consistente.

### 18.4 Por qué un reproductor de sesión separado del global

El reproductor global está optimizado para una sola pista a la vez con
una cola lineal. Hacer crossfade real requiere dos pipelines de audio
simultáneos y sincronizados, lo que es invasivo. Tener un reproductor
DJ aislado con sus propios decks A/B y bucle de polling permite
implementar mezcla sin tocar el reproductor existente. El ownership
manager (sección 12) garantiza coexistencia limpia.

### 18.5 Por qué no LLM

Determinismo, interpretabilidad, latencia, privacidad y coste cero.
La arquitectura permite añadir un re-ranker basado en LLM como capa
adicional sin tocar el motor determinista existente.

---

## 19. Límites actuales

1. **Mix points por BPM solo**: para pistas sin BPM en
   `track_audio_features`, se usa el default. El cálculo por RMS
   (librosa) existe en código pero es opt-in: no se llama
   automáticamente al cargar para evitar un pre-fetch agresivo.
2. **`FILTER_SWEEP` no es cutoff real**: es gradiente de ganancias en
   10 bandas ISO. Suficiente para "sensación DJ" pero no para sweeps
   acústicamente continuos.
3. **HARMONIC_MIX depende de karaoke pre-procesado**: si el usuario nunca
   procesó karaoke y el pre-fetch no terminó a tiempo, la técnica se
   degrada a otra sin avisar. Es honesto pero no garantiza vocal removal
   en una sesión recién creada.
4. **Una sesión activa por instancia**: el modelo guarda solo la última
   sesión cargada/sonando. Las anteriores viven en `dj_sesiones`.
5. **No hay aprendizaje de preferencias**: likes/dislikes se registran
   pero no influyen en futuras sesiones todavía.
6. **Calidad subjetiva no testeable automáticamente**: si una transición
   suena rara, hay que escucharla y ajustar curvas o reglas.

---

## 20. Resumen ejecutivo

DJ Privado es un **director musical automático con motor de mezcla real**.
Combina un parser determinístico de intención perceptual, un scheduler
multi-eje interpretable y un motor de transiciones que aplica técnicas
DJ-grade (corte en el beat, fundido equal-power, EQ kill de bajos,
barrido de filtros, mezcla con stems sin voz) según el hardware
disponible y la fase narrativa de la sesión.

Funciona sin LLMs, sin descargas obligatorias, sin red. El motor opera
plenamente en hardware modesto (perfil LOW) usando libVLC; en hardware
con Demucs aprovecha los instrumentales del subsistema karaoke para
mezcla con vocal removal. La UI usa textos orientados a la acción
humana y nunca expone identificadores internos al usuario.
