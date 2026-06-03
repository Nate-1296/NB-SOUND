# Resolución de problemas

## Problemas del bundle (release instalada)

Aplica si instalaste NB SOUND desde
[Releases](https://github.com/Nate-1296/NB-SOUND/releases) (`.deb`,
`.rpm`, `.AppImage`, `.exe`, `.dmg`). Para problemas en modo desarrollo
(desde código fuente), salta a [Problemas de instalación](#problemas-de-instalación).

### "Karaoke: no se pudo decodificar X.mp3"

Los bundles oficiales ya traen `ffmpeg` y `ffprobe` empaquetados, y
`main_ui.py` antepone el directorio `bin/` del bundle al `PATH`. Si
aun así falla:

1. Revisa el log del último intento en `<USER_LOGS_DIR>/tagger_run.log`.
   El detalle técnico aparece en la línea `Job N fallo (audio_corrupto)
   ... | detalle=...`.
2. Confirma que el archivo se decodifica con tu ffmpeg del sistema:
   `ffmpeg -i /ruta/al/archivo.mp3 -f null -`.
3. Si la pista tiene metadata ID3 corrupta, puede fallar la lectura
   inicial; reabrirla y guardarla con un editor de tags como Kid3
   suele resolverlo.

### "Análisis profundo: todas las pistas fallidas"

El subprocess externo carga TensorFlow + modelos desde el Python del
sistema. Si todas fallan con el mismo error:

1. Revisa el log: `<USER_LOGS_DIR>/tagger_run.log` contiene
   `analyzer_init_failed: ...` con el mensaje real del fallo.
2. Comprueba que el Python del sistema sea ≥ 3.10:
   `python3 --version`.
3. Si dice `No module named 'essentia'`, la app no terminó de instalar
   las dependencias opcionales. Ve a **Configuración → Estado del
   sistema** y pulsa **Instalar** sobre Essentia/Demucs/PyTorch según
   lo que aparezca como faltante.

### Plug & play (Estado del sistema)

La vista detecta y permite instalar `torch`, `demucs` y
`essentia-tensorflow` + modelos `.pb` sin reiniciar la app. Casos
frecuentes:

1. **"Python del sistema no utilizable"** (Linux): falta `pip` o
   `venv`. La propia vista ofrece un botón **Reparar Python** que
   ejecuta `pkexec apt install python3-pip python3-venv` (te pide
   contraseña).
2. **"PyTorch instalado pero no detectado"**: cierra y vuelve a abrir
   la app una vez. La detección hace `import torch` en un subprocess
   externo aislado; el primer `import` puede tardar varios segundos.
3. **El instalador se queda colgado**: cancela y mira
   `<USER_LOGS_DIR>/tagger_run.log` → busca líneas
   `nb_sound.instalador`. El log muestra la salida real de `pip`.

### Mini reproductor: VLC sigue sonando tras cerrar la app

Resuelto en v1.0.0. Si lo ves, confirma que la versión instalada es
la última: `dpkg -l nb-sound | grep Version`. Si persiste, mata el
proceso huérfano con `pkill -f nb_sound` y reporta el caso con el log.

### La app no escribe logs

`infra/logger.py` usa line-buffering: cada `\n` se persiste al SO. Si
el archivo está vacío:

1. Confirma la ruta real desde la propia app (Configuración → Logs).
2. Si está vacía aún tras usar la app, revisa permisos de escritura
   en ese directorio.

---

## Problemas de instalación

### `ModuleNotFoundError`

El entorno virtual no está activado o faltan dependencias.

```bash
# Linux / macOS
source .venv/bin/activate
pip install -r requirements.txt
```

```powershell
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### `No module named PySide6`

```bash
pip install PySide6
```

### `No module named vlc`

```bash
pip install python-vlc
```

Asegúrate también de que VLC esté instalado en el sistema (no solo el paquete Python).

---

## Problemas de herramientas externas

### FFmpeg no encontrado

```bash
# Linux (Debian/Ubuntu)
sudo apt install ffmpeg

# Linux (Fedora)
sudo dnf install ffmpeg

# Linux (Arch)
sudo pacman -S ffmpeg

# macOS
brew install ffmpeg
```

```powershell
# Windows (winget)
winget install --id Gyan.FFmpeg

# Windows (Chocolatey)
choco install -y ffmpeg
```

```bash
# Verificar
ffmpeg -version
```

### `fpcalc` no encontrado

```bash
# Linux (Debian/Ubuntu)
sudo apt install libchromaprint-tools

# Linux (Fedora)
sudo dnf install chromaprint-tools

# Linux (Arch)
sudo pacman -S chromaprint

# macOS
brew install chromaprint
```

```powershell
# Windows (winget)
winget install --id AcoustID.Chromaprint.Fpcalc

# Windows (Chocolatey)
choco install -y chromaprint
```

```bash
# Verificar
fpcalc -version
```

### VLC no reproduce en la UI

1. Verifica que VLC esté instalado en el sistema: `vlc --version`
2. Verifica que `python-vlc` esté instalado en el entorno: `pip show python-vlc`
3. En algunos sistemas puede haber conflicto con versiones. Reinstala: `pip install --force-reinstall python-vlc`

---

## Problemas de catalogación

### Todo queda en cuarentena

Revisa en este orden:

1. Conexión a internet activa
2. AcoustID configurado (`ACOUSTID_API_KEY`) si está activado
3. Shazam habilitado (`ENABLE_SHAZAM=True`)
4. Que los archivos tengan duración válida y no estén corruptos
5. Que FFmpeg esté disponible para archivos no-MP3
6. Logs en `USER_LOGS_DIR` para ver el motivo exacto

### Todo queda en revisión

Puede ser comportamiento correcto. Ocurre con versiones live, remasters, compilaciones, covers, ediciones deluxe y títulos ambiguos. El sistema es conservador por diseño.

Si parece excesivo, revisa la calidad de los tags locales y si MusicBrainz devuelve candidatos razonables.

### `--dry-run` mueve archivos

No debería ocurrir. Si pasa, verifica que la variable `DRY_RUN` se lea correctamente desde `settings` en todos los módulos que escriben o mueven archivos.

---

## Problemas de la UI

### La UI abre pero muestra la biblioteca vacía

La UI y el CLI deben usar la misma base de datos. Si usas rutas por defecto, verifica que `USER_LIBRARY_DIR` esté configurado en `.env` y que exista el archivo `nb_sound.sqlite3` en esa carpeta.

También puedes iniciar la UI apuntando explícitamente a la DB:

```bash
python main_ui.py --db /ruta/a/nb_sound.sqlite3
```

### QML muestra cambios viejos

NB SOUND desactiva el caché QML automáticamente con `QML_DISABLE_DISK_CACHE=1`. Si el problema persiste, cierra la app y borra los cachés QML temporales del sistema.

### La UI no responde durante importación

La importación corre en un worker Qt. Si la UI se congela completamente (no solo el botón de importar), puede ser un conflicto con el loop de eventos. Revisa los logs en `USER_LOGS_DIR`.

---

## Problemas de Audio Intelligence

### Estado `backend_disabled`

```env
ENABLE_AUDIO_INTELLIGENCE_DEEP=True
AUDIO_INTELLIGENCE_BACKEND=essentia_tensorflow
```

### Estado `model_dir_missing`

```env
AUDIO_INTELLIGENCE_MODEL_DIR=/ruta/correcta/a/modelos_essentia
```

Verifica que la carpeta contenga los 22 archivos `.pb` y `.json` necesarios.

### Análisis profundo muy lento

- Mantén `AUDIO_INTELLIGENCE_MAX_WORKERS=1` en equipos medios
- Usa `AUDIO_INTELLIGENCE_SEGMENT_SECONDS=120` o menos
- Ejecuta el deep después de la importación, no durante
- Usa `--audio-intelligence-deep-pause` y reanuda cuando el equipo esté libre

---

## SQLite bloqueada

No lances dos procesos sobre la misma base de datos simultáneamente. La conexión usa un lock Python pero no tolera múltiples procesos externos.

---

## Problemas de rendimiento

### Importación muy lenta con Shazam activo

Shazam tiene límites de rate. Si procesas muchas canciones, considera desactivarlo temporalmente o aumentar el timeout:

```env
SHAZAM_TIMEOUT_SEG=20
```

### Mucha memoria durante importación

Reduce workers:

```env
AUDIO_FEATURES_MAX_WORKERS=1
AUDIO_INTELLIGENCE_MAX_WORKERS=1
```

---

← [Volver al README](../README.md)
