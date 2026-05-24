# Requisitos del sistema

## Software

### Obligatorio

| Dependencia | Versión mínima | Uso |
|---|---|---|
| Python | 3.12 | Lenguaje base del proyecto |
| FFmpeg | Cualquiera reciente | Conversión de audio no-MP3 a MP3 |
| VLC | Cualquiera reciente | Reproducción de audio en la UI |
| Chromaprint (`fpcalc`) | Cualquiera reciente | Fingerprint acústico para AcoustID |
| SQLite | Incluido con Python | Base de datos local |

### Instalación de dependencias del sistema

**Linux (Ubuntu / Debian / Pop!\_OS)**

```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3-pip \
                 ffmpeg libchromaprint-tools vlc
```

**Linux (Fedora)**

```bash
sudo dnf install python3 python3-pip ffmpeg chromaprint-tools vlc
```

**Linux (Arch)**

```bash
sudo pacman -S python python-pip ffmpeg chromaprint vlc
```

**macOS**

```bash
brew install python@3.12 ffmpeg chromaprint vlc
```

**Windows (PowerShell con winget)**

```powershell
winget install --id Python.Python.3.12
winget install --id Gyan.FFmpeg
winget install --id AcoustID.Chromaprint.Fpcalc
winget install --id VideoLAN.VLC
```

**Windows (Chocolatey)**

```powershell
choco install -y python --version=3.12.*
choco install -y ffmpeg chromaprint vlc
```

**Windows (instalación manual)**

1. Instalar [Python 3.12](https://www.python.org/downloads/) y marcar "Add Python to PATH"
2. Instalar [FFmpeg](https://ffmpeg.org/) y agregar la carpeta `bin/` al `PATH`
3. Instalar [Chromaprint](https://acoustid.org/chromaprint) y agregar `fpcalc.exe` al `PATH`
4. Instalar [VLC 64 bits](https://www.videolan.org/vlc/) — debe coincidir con la arquitectura del Python instalado

### Dependencias Python

```bash
# Base (obligatorio)
pip install -r requirements.txt

# Desarrollo y tests
pip install -r requirements-dev.txt

# Audio Intelligence profunda (opcional, pesado)
pip install -r requirements-audio-intelligence.txt
```

Paquetes principales incluidos en `requirements.txt`:

| Paquete | Versión | Uso |
|---|---|---|
| `PySide6` | ≥ 6.6.0 | Interfaz gráfica |
| `mutagen` | ≥ 1.47.0 | Lectura/escritura de tags de audio |
| `python-dotenv` | ≥ 1.0.0 | Carga de configuración desde `.env` |
| `Pillow` | ≥ 10.0.0 | Generación de portadas collage |
| `python-vlc` | ≥ 3.0.20123 | Backend de reproducción |
| `librosa` | ≥ 0.11.0 | Análisis de audio local (features) |
| `musicbrainzngs` | 0.7.1 | API MusicBrainz |
| `pyacoustid` | ≥ 1.3.0 | Fingerprint acústico |
| `shazamio` | ≥ 0.4.0 | Reconocimiento Shazam |
| `anthropic` / `openai` | ≥ reciente | IA para desempate (opcional) |

### Audio Intelligence profunda (opcional)

Requiere `essentia-tensorflow`, que depende de modelos externos. Solo instalar si se planea usar análisis de moods, géneros Discogs400 o embeddings profundos. La instalación puede ser delicada dependiendo del sistema:

```bash
pip install -r requirements-audio-intelligence.txt
```

Verificar disponibilidad de la wheel para tu Python/OS en [PyPI](https://pypi.org/project/essentia-tensorflow/).

---

## Hardware

El rendimiento varía según el tamaño de la biblioteca, velocidad del disco, conectividad y si se usa Audio Intelligence profunda.

| Perfil | CPU | RAM | Disco | Uso recomendado |
|---|---|---|---|---|
| Mínimo | 2 núcleos | 8 GB | HDD o SSD | Pruebas, bibliotecas pequeñas, sin deep |
| Recomendado | 4–6 núcleos | 16 GB | SSD | Importación normal, UI, features básicos |
| Cómodo | 6–8 núcleos | 16–32 GB | NVMe | Bibliotecas grandes, deep por CPU |
| Alto | 8–12 núcleos | 32 GB | NVMe rápido | Deep frecuente, multitarea, lotes grandes |

> La GPU solo ayuda si el backend TensorFlow/Essentia realmente la detecta y aprovecha. En la mayoría de equipos sin NVIDIA compatible, el análisis profundo corre en CPU.

---

## Tiempos estimados

Referencia medida en Ryzen 5 3550H / 24 GB RAM / SSD / sin GPU:

| Modo | Canciones | Tiempo total | Por canción |
|---|---:|---:|---:|
| Importación normal | 2 335 | ≈ 3 h 15 min | ≈ 5 s |
| Audio Intelligence profunda (CPU) | 2 000 | ≈ 15 h | ≈ 27 s |

Estimaciones rápidas:

```text
100 canciones normal  →  ~8 min
1 000 canciones normal →  ~1 h 20 min
2 000 canciones normal →  ~2 h 45 min

100 canciones deep CPU  →  ~45 min
500 canciones deep CPU  →  ~3 h 45 min
```

El flujo recomendado en equipos medios es **importar primero, analizar deep después** en background.

---

← [Volver al README](../README.md)
