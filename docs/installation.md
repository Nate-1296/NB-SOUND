# Instalación

NB SOUND tiene dos rutas de instalación independientes según tu caso de
uso. Elige la que aplique:

- [Instalar como aplicación (release)](#instalar-como-aplicación-release)
  — usuarios finales que quieren la app empaquetada lista para usar.
- [Instalar desde el código fuente (desarrollo)](#instalar-desde-el-código-fuente-desarrollo)
  — desarrolladores, contributors o quien quiera ejecutar la suite de
  tests.

---

## Instalar como aplicación (release)

Descarga el instalador para tu sistema desde
[Releases](https://github.com/Nate-1296/NB-SOUND/releases). Los bundles
ya traen `ffmpeg`, `ffprobe` y `fpcalc` empaquetados; solo necesitas
**VLC** instalado en el sistema (para reproducción de audio).

### Linux

**Debian / Ubuntu / Pop!_OS**

```bash
sudo apt install ./nb-sound_1.0.0_amd64.deb
```

**Fedora / RHEL**

```bash
sudo dnf install ./nb-sound-1.0.0-1.x86_64.rpm
```

**AppImage (cualquier distro)**

```bash
chmod +x NB_Sound-1.0.0-x86_64.AppImage
./NB_Sound-1.0.0-x86_64.AppImage
```

**Portable**

```bash
tar -xzf nb_sound-1.0.0-linux-x64.tar.gz
cd nb_sound-1.0.0-linux-x64
./nb_sound
```

VLC del sistema (necesario solo para reproducción):

```bash
sudo apt install vlc                 # Debian/Ubuntu
sudo dnf install vlc                 # Fedora
sudo pacman -S vlc                   # Arch
```

### Windows

- **Installer**: descarga `nb-sound-1.0.0-windows-x64-setup.exe` y
  ejecuta. Crea acceso en menú inicio.
- **Portable**: descomprime `nb_sound-1.0.0-windows-x64.zip` y ejecuta
  `nb_sound.exe`.

VLC del sistema:

```powershell
winget install --id VideoLAN.VLC
```

### macOS

- **DMG**: monta `NB_Sound-1.0.0-macos.dmg` y arrastra `NB Sound.app`
  a `/Applications`.
- **Portable**: descomprime `nb_sound-1.0.0-macos-arm64.zip`.

VLC del sistema:

```bash
brew install --cask vlc
```

### Dependencias opcionales (karaoke + análisis profundo)

`torch`, `demucs` y `essentia-tensorflow` **no vienen incluidas** en el
bundle (suman ~2 GB y la mayoría de usuarios no las necesitan). La
primera vez que entres a la vista **Estado del sistema** o intentes
usar Karaoke o Análisis profundo, la app detecta qué falta y te ofrece
instalarlo automáticamente (~300–500 MB descarga real). No requiere
abrir terminal ni reiniciar la app.

Los modelos Essentia (`.pb`) también se descargan desde la propia
vista al activar el análisis profundo.

### Resolución de problemas comunes

- **La app abre pero no reproduce**: confirma que VLC esté instalado
  con `vlc --version`. La UI muestra un aviso si no lo detecta.
- **"No se pudo decodificar X.mp3" en karaoke**: el bundle ya trae
  ffprobe; si persiste, revisa el log en
  `$XDG_DATA_HOME/nb_sound/logs/tagger_run.log` (Linux) o el
  equivalente del SO.
- **El instalador `.deb` falla por dependencia faltante**: el `.deb`
  declara solo `vlc` como dependencia; cualquier otra falla suele
  resolverse con `sudo apt --fix-broken install`.

→ Más en [docs/troubleshooting.md](troubleshooting.md)

---

## Instalar desde el código fuente (desarrollo)

### Requisitos previos

Antes de instalar NB SOUND, asegúrate de tener:

- Python 3.12 instalado
- FFmpeg en el `PATH`
- VLC instalado en el sistema (para la UI)
- Chromaprint/`fpcalc` en el `PATH` (para AcoustID)

→ Instrucciones detalladas en [docs/requirements.md](requirements.md)

---

## Paso a paso

### 1. Clonar el repositorio

```bash
git clone <URL_DEL_REPOSITORIO> nb_sound
cd nb_sound
```

### 2. Crear entorno virtual

**Linux / macOS:**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Actualizar pip e instalar dependencias

```bash
pip install -U pip setuptools wheel
pip install -r requirements.txt
```

Para desarrollo y tests:

```bash
pip install -r requirements-dev.txt
```

### 4. Configurar variables de entorno

**Opción A — Configuración automática.** Si no creas un `.env`, la UI lo
genera en el primer arranque con rutas estándar del sistema operativo
(XDG en Linux, `%APPDATA%` en Windows, `~/Library` en macOS) y crea los
directorios necesarios. No se sobreescribe ningún archivo existente.

**Opción B — Configuración manual.**

```bash
cp .env.example .env
```

Edita `.env` y define al menos las rutas principales. **Usa rutas absolutas adaptadas a tu sistema operativo**:

```env
# Linux / macOS
USER_INPUT_DIR=/home/usuario/Música/Entrada
USER_LIBRARY_DIR=/home/usuario/Música/Biblioteca
USER_QUARANTINE_DIR=/home/usuario/Música/Cuarentena
USER_REVIEW_DIR=/home/usuario/Música/Revision
USER_LOGS_DIR=/home/usuario/Música/Logs
USER_PROCESSED_DIR=/home/usuario/Música/Procesados
```

```env
# Windows (usa barras normales / o dobles \\, nunca una sola \)
USER_INPUT_DIR=C:/Users/usuario/Music/Entrada
USER_LIBRARY_DIR=C:/Users/usuario/Music/Biblioteca
USER_QUARANTINE_DIR=C:/Users/usuario/Music/Cuarentena
USER_REVIEW_DIR=C:/Users/usuario/Music/Revision
USER_LOGS_DIR=C:/Users/usuario/Music/Logs
USER_PROCESSED_DIR=C:/Users/usuario/Music/Procesados
```

→ Explicación completa de todas las variables en [docs/configuration.md](configuration.md)

### 5. Verificar la instalación

```bash
# Verificar CLI
python main.py --version
python main.py --help

# Verificar UI
python main_ui.py --version
```

### 6. Ejecutar tests (opcional)

```bash
pytest -q
```

Todos los tests deberían pasar. Si falla alguno relacionado con VLC o librerías nativas, verifica que estén instaladas correctamente.

---

## Verificaciones adicionales

### FFmpeg

```bash
ffmpeg -version
```

Si no aparece, instálalo y asegúrate de que esté en el `PATH`.

### Chromaprint

```bash
fpcalc -version
```

### VLC

```bash
# Linux
vlc --version

# macOS
/Applications/VLC.app/Contents/MacOS/VLC --version
```

```powershell
# Windows
"C:\Program Files\VideoLAN\VLC\vlc.exe" --version
```

La UI abrirá aunque VLC no esté disponible, pero mostrará un aviso crítico y la reproducción quedará deshabilitada.

---

## Audio Intelligence profunda (opcional)

Solo si necesitas análisis de moods, géneros Discogs400 y embeddings profundos:

```bash
pip install -r requirements-audio-intelligence.txt
```

Luego configura en `.env`:

```env
ENABLE_AUDIO_INTELLIGENCE_DEEP=True
AUDIO_INTELLIGENCE_BACKEND=essentia_tensorflow
AUDIO_INTELLIGENCE_MODEL_DIR=/ruta/a/modelos_essentia
```

Los modelos Essentia deben descargarse por separado. Consulta [docs/audio-features.md](audio-features.md) para la lista completa de archivos necesarios.

---

## Problemas comunes

**`ModuleNotFoundError`**: activa el entorno virtual y ejecuta `pip install -r requirements.txt`.

**La UI abre pero no reproduce**: verifica que VLC esté instalado en el sistema y que `python-vlc` esté instalado en el entorno.

**Todo queda en cuarentena**: revisa la conexión a internet, las claves de API y la calidad de los tags de tus archivos.

**QML muestra cambios viejos**: NB SOUND desactiva el caché QML automáticamente (`QML_DISABLE_DISK_CACHE=1`). Si persiste, reinicia la aplicación.

→ Más soluciones en [docs/troubleshooting.md](troubleshooting.md)

---

← [Volver al README](../README.md)
