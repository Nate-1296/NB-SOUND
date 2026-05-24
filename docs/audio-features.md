# Audio Features e Intelligence

NB SOUND tiene dos niveles de análisis de audio: uno ligero que corre en cualquier equipo, y uno profundo que requiere modelos externos.

---

## Audio Features básico

Análisis local con `librosa`. No requiere internet ni modelos externos.

**Qué genera:**

- BPM (tempo)
- Energía RMS
- Brillo espectral
- Contraste espectral
- Zero crossing rate
- Danceability proxy
- Vibe tags derivados de reglas básicas (energético, tranquilo, bailable, etc.)

**Configuración:**

```env
ENABLE_AUDIO_FEATURES=True
AUDIO_FEATURES_MODE=light          # light (recomendado) o standard
AUDIO_FEATURES_ANALYZE_ON_IMPORT=True
AUDIO_FEATURES_BACKGROUND=True
AUDIO_FEATURES_MAX_WORKERS=1
AUDIO_FEATURES_SAMPLE_STRATEGY=smart_segments
AUDIO_FEATURES_SEGMENT_SECONDS=90
```

**Comandos CLI:**

```bash
python main.py --audio-features-status        # Ver estado actual
python main.py --audio-features-analyze       # Analizar pendientes
python main.py --audio-features-analyze --all # Forzar todas las pistas
python main.py --audio-features-reanalyze     # Reanálisis completo
```

Los features básicos se guardan en SQLite (`track_audio_features` y `track_vibe_tags`) y se usan para la búsqueda natural "Háblale a tu biblioteca".

---

## Audio Intelligence profunda (opcional)

Modelos Essentia/TensorFlow para análisis más ricos. Lento, pesado, apagado por defecto.

> En los bundles oficiales (release) el análisis profundo corre en un
> **subprocess Python externo** aislado del proceso de la UI. El
> adaptador `core.audio_intelligence_deep_subprocess.DeepAnalyzerSubprocess`
> mantiene un daemon persistente que reutiliza el modelo entre tracks
> (la carga de TensorFlow + modelos tarda ~10–15 s y solo se paga una
> vez) y se comunica vía protocolo JSON por línea. La UI nunca acapara
> el GIL ni se ve afectada por crashes nativos del backend. En modo
> desarrollo (`python main_ui.py`) el analyzer corre in-process; el
> subprocess se activa automáticamente cuando `sys.frozen` o cuando se
> exporta `NB_SOUND_DEEP_SUBPROCESS=1`.

**Qué genera:**

- Embeddings MusicNN y VGGish
- Tags MSD50 (50 etiquetas musicales generales)
- Moods: happy, sad, relaxed, aggressive, party
- Arousal y valence (DEAM)
- Danceability
- Géneros Discogs400

**Activación:**

```env
ENABLE_AUDIO_INTELLIGENCE_DEEP=True
AUDIO_INTELLIGENCE_BACKEND=essentia_tensorflow
AUDIO_INTELLIGENCE_MODEL_DIR=/ruta/a/modelos_essentia
ENABLE_AUDIO_MOOD_MODELS=True
ENABLE_AUDIO_EMBEDDINGS=True
ENABLE_AUDIO_TAGGING_MODELS=True
```

**Modelos requeridos:**

Los 22 archivos (`.pb` + `.json`) deben estar en `AUDIO_INTELLIGENCE_MODEL_DIR`:

```text
audioset-vggish-3.json / .pb
danceability-msd-musicnn-1.json / .pb
deam-msd-musicnn-2.json / .pb
discogs-effnet-bs64-1.json / .pb
genre_discogs400-discogs-effnet-1.json / .pb
mood_aggressive-msd-musicnn-1.json / .pb
mood_happy-msd-musicnn-1.json / .pb
mood_party-msd-musicnn-1.json / .pb
mood_relaxed-msd-musicnn-1.json / .pb
mood_sad-msd-musicnn-1.json / .pb
msd-musicnn-1.json / .pb
```

Los modelos se descargan por separado desde el sitio oficial de Essentia.

**Instalación:**

```bash
pip install -r requirements-audio-intelligence.txt
```

La instalación de `essentia-tensorflow` puede ser delicada. Verifica compatibilidad de wheel con tu versión de Python y sistema operativo.

---

## Background reanudable

El análisis profundo se registra en SQLite como jobs/runs. Si el proceso se interrumpe, se puede retomar exactamente desde donde se quedó.

```bash
python main.py --audio-intelligence-deep-status      # Estado actual
python main.py --audio-intelligence-deep-resume      # Reanudar pendientes
python main.py --audio-intelligence-deep-pause       # Pausar
python main.py --audio-intelligence-deep-cancel-keep     # Cancelar, conservar resultados listos
python main.py --audio-intelligence-deep-cancel-discard  # Cancelar, descartar resultados
python main.py --audio-intelligence-deep-retry-failed    # Reintentar fallidos
```

La UI también expone estos controles desde la vista Importar en modo Pro.

---

## Music Discovery

Búsqueda natural sobre tu biblioteca usando los features disponibles.

```bash
python main.py --music-discovery "algo triste"
python main.py --music-discovery "música para entrenar" --limit 15
```

En la UI: "Háblale a tu biblioteca" dentro de la vista Buscar.

La calidad de los resultados mejora con más features disponibles:

| Nivel | Qué usa | Calidad |
|---|---|---|
| Sin features | Solo metadata textual | Básica |
| Features básicos | BPM, energía, vibe tags | Buena |
| Features básicos + deep | Todo lo anterior + moods, géneros, embeddings | Excelente |

---

## Rendimiento estimado

Análisis básico (`librosa`, modo `light`, 90 segundos por pista):

- ~0.5–2 s por pista en equipos medios
- No bloquea la importación (corre en background)

Análisis profundo (Essentia, CPU):

- ~27 s por pista en Ryzen 5 3550H
- 1 000 pistas ≈ 7–8 horas
- **Recomendación:** importar primero, analizar deep después

---

← [Volver al README](../README.md)
