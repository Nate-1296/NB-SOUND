# NB SOUND

Un catalogador inteligente de música local. Identifica, etiqueta, organiza y enriquece tu colección de audio, y te da una interfaz completa para escucharla, explorarla y entenderla.

Sin nube. Sin suscripción. Sin que nadie sepa lo que escuchas.

---

## ¿Qué hace?

**El cerebro (CLI)** convierte una carpeta desordenada de archivos de audio en una biblioteca catalogada: reescribe tags ID3, descarga portadas, busca letras, detecta duplicados y deja todo trazable. Acepta automáticamente solo cuando la confianza es alta; si hay duda, manda a revisión; si hay problema técnico, a cuarentena.

**La interfaz (UI)** te deja reproducir tu colección, importar música nueva, revisar pendientes, buscar por texto o por lenguaje natural ("algo triste pero con energía"), gestionar playlists locales y ver estadísticas de tu propio historial de escucha. Incluye también karaoke con separación voz/instrumental, sesiones continuas mezcladas por un DJ automático y un juego de redescubrimiento sobre tu biblioteca.

---

## Inicio rápido

### Para usuarios — instalar una release

Descarga el instalador para tu sistema desde
[Releases](https://github.com/Nate-1296/NB-SOUND/releases):

- **Linux (Debian/Ubuntu/Pop!_OS)**: `nb-sound_1.0.0_amd64.deb` —
  `sudo apt install ./nb-sound_1.0.0_amd64.deb`
- **Linux (Fedora/RHEL)**: `nb-sound-1.0.0-1.x86_64.rpm` —
  `sudo dnf install ./nb-sound-1.0.0-1.x86_64.rpm`
- **Linux (cualquiera)**: `NB_Sound-1.0.0-x86_64.AppImage` —
  `chmod +x` y ejecutar
- **Linux (portable)**: `nb_sound-1.0.0-linux-x64.tar.gz` —
  descomprimir y ejecutar `nb_sound`
- **Windows**: `nb-sound-1.0.0-windows-x64-setup.exe` — instalador
  guiado; o `nb_sound-1.0.0-windows-x64.zip` para portable
- **macOS**: `NB_Sound-1.0.0-macos.dmg` — arrastrar a Applications;
  o `nb_sound-1.0.0-macos-arm64.zip` para versión portable

> Los bundles ya traen **FFmpeg + ffprobe + fpcalc** empaquetados; solo
> necesitas **VLC** instalado en el sistema (para reproducción de audio).
> Las dependencias opcionales pesadas (PyTorch, Demucs para karaoke,
> Essentia para análisis profundo) se instalan automáticamente desde
> la propia app la primera vez que las uses. Detalle en
> [docs/requirements.md](docs/requirements.md).

### Para desarrolladores — desde el código fuente

```bash
# Linux / macOS
git clone https://github.com/Nate-1296/NB-SOUND.git nb_sound && cd nb_sound
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py      # CLI
python main_ui.py   # UI
```

```powershell
# Windows (PowerShell)
git clone https://github.com/Nate-1296/NB-SOUND.git nb_sound
cd nb_sound
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
python main_ui.py
```

El primer arranque sin `.env` crea automáticamente las carpetas estándar
del SO (XDG en Linux, `%APPDATA%` en Windows, `~/Library/...` en macOS).

→ Guía completa en [docs/installation.md](docs/installation.md)

---

## Características

### Cerebro CLI

- Identificación por fingerprint acústico (AcoustID), Shazam y MusicBrainz
- Reescritura segura de tags ID3 (nunca toca el original directamente)
- Detección de duplicados exactos (hash SHA256) y semánticos (ISRC +
  `mb_recording_id`) con pre-carga desde la biblioteca: reimportar no
  crea duplicados
- Descarga de portadas, imágenes de artistas y letras sincronizadas
- Análisis de audio local: BPM, energía, danceability, vibe tags
- Análisis profundo opcional con modelos Essentia/TensorFlow (moods,
  géneros Discogs400, embeddings), aislado en subprocess Python externo
  para no bloquear la UI ni acoplar versiones nativas al bundle
- Dry-run, recuperación post-importación y procesamiento reanudable
  con manifiestos

### Interfaz gráfica (PySide6/QML)

- Reproductor completo con cola, lyrics, fullscreen y mini player
- Importación con progreso en tiempo real, ETA y cancelación
- Biblioteca por álbumes, artistas y pistas con filtros y orden
- Playlists locales: manuales, automáticas, "This is...", tops y mixes
- Búsqueda clásica y búsqueda natural ("Háblale a tu biblioteca")
- Dashboard de inicio con recientes, tops y sugerencias
- Vista de perfil con estadísticas personales y actividad mensual
- Karaoke: separación voz/instrumental con Demucs y conmutación en vivo
- DJ Privado: sesiones continuas a partir de un prompt, con mezcla real
  (corte en el beat, fundido, EQ kill, barrido de filtros, fundido con
  capas usando los stems del karaoke)
- Explorador Ciego (¡A ciegas!): juego de redescubrimiento sobre tu
  biblioteca con cuatro modos, sistema de pistas progresivas y validación
  por escritura
- 61 paletas de tema más tema personalizado, con contraste WCAG
  calculado dinámicamente sobre cada color de acento
- Refresco en vivo tras importación: estadísticas, biblioteca, playlists,
  karaoke, deep y cache de letras se actualizan sin reiniciar la app
- Plug & play opcional: detecta y permite instalar torch/demucs/
  essentia-tensorflow + modelos `.pb` desde la propia vista de
  configuración cuando se quiere usar karaoke o análisis profundo

---

## Documentación

| Documento | Descripción |
| --- | --- |
| [Requisitos del sistema](docs/requirements.md) | Software, hardware y tiempos estimados |
| [Instalación](docs/installation.md) | Paso a paso para Linux, macOS y Windows |
| [Configuración](docs/configuration.md) | Variables `.env` explicadas |
| [CLI](docs/cli.md) | Todos los comandos del cerebro |
| [Interfaz gráfica](docs/ui.md) | Guía de la UI y sus vistas |
| [Audio Features e Intelligence](docs/audio-features.md) | Análisis local y modelos profundos |
| [Karaoke](docs/karaoke.md) | Separación voz/instrumental, cola, errores y cancelación |
| [DJ Privado](docs/dj_privado.md) | Director musical automático y motor de mezcla real |
| [Explorador Ciego](docs/explorador-ciego.md) | Juego de redescubrimiento: modos, hints y validación |
| [Arquitectura](docs/architecture.md) | Estructura técnica del proyecto |
| [Ciclo de vida de importación](docs/import-lifecycle.md) | Pipeline completo: etapas, decisiones, sidecars y recovery |
| [Pipeline de audio](docs/audio-pipeline.md) | Análisis básico (librosa), análisis profundo (Essentia), feature store |
| [Procesamiento en background](docs/background-processing.md) | Workers Qt, cola karaoke, sidecars del CLI |
| [Arquitectura de reproducción](docs/playback-architecture.md) | VLC, karaoke, DJ Privado y mezcla real |
| [Arquitectura QML](docs/qml-architecture.md) | Puente Python↔QML, modelos reactivos, componentes |
| [Observabilidad](docs/observability.md) | Logging estructurado, ControlEjecucion, reports |
| [Recovery y resiliencia](docs/recovery-and-resilience.md) | Mecanismos de recuperación ante fallos e interrupciones |
| [Resolución de problemas](docs/troubleshooting.md) | Errores frecuentes y cómo resolverlos |

---

## Requisitos mínimos

| | Linux | Windows | macOS |
| --- | --- | --- | --- |
| Python | 3.12 | 3.12 | 3.12 |
| FFmpeg | `apt/dnf/pacman install ffmpeg` | `winget install Gyan.FFmpeg` | `brew install ffmpeg` |
| VLC | `apt/dnf/pacman install vlc` | `winget install VideoLAN.VLC` | `brew install --cask vlc` |
| fpcalc (opcional) | `apt install libchromaprint-tools` | `winget install AcoustID.Chromaprint.Fpcalc` | `brew install chromaprint` |

→ Detalle completo en [docs/requirements.md](docs/requirements.md)

## Plataformas soportadas

NB Sound se prueba y empaqueta para:

- **Linux x86_64**: Ubuntu 22.04+, Debian 12+, Fedora 39+, Arch
- **Windows 10/11 x86_64**
- **macOS 10.15+** (Intel y Apple Silicon)

La CI (`.github/workflows/ci.yml`) ejecuta la suite de portabilidad en
los tres SO con cada commit a `main`.

---

## Licencia

GNU GPL v3.0 or later — ver [LICENSE](LICENSE).

Puedes usar, modificar y redistribuir libremente. Si distribuyes versiones modificadas, deben mantener la misma licencia.

```text
Copyright (C) 2026 Nathan
```
