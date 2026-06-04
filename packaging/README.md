# Empaquetado de NB Sound

Recursos para producir binarios distribuibles de NB Sound en Linux, Windows
y macOS, incluyendo instaladores nativos (`.deb`, `.rpm`, `.AppImage`,
`.exe` NSIS, `.dmg`) además de bundles portables.

## Estructura

```text
packaging/
├── README.md                 ← esta guía
├── _common.py                ← analysis compartido entre los tres specs
├── linux/
│   ├── nb_sound.spec         ← PyInstaller para Linux
│   ├── build.sh              ← build local: tar.gz + opcional AppImage
│   ├── nb-sound.desktop      ← entry para escritorios freedesktop
│   └── com.nbsound.NBSound.metainfo.xml  ← AppStream para distros
├── windows/
│   ├── nb_sound.spec         ← PyInstaller para Windows
│   ├── build.ps1             ← build local: .zip portable
│   └── installer.nsi         ← script NSIS para instalador .exe
└── macos/
    ├── nb_sound.spec         ← PyInstaller para macOS (.app bundle)
    └── build.sh              ← build local: .zip + opcional .dmg
```

Los iconos (`.ico`, `.icns`, PNGs multi-resolución) viven en
[`ui/qml/assets/logo/`](../ui/qml/assets/logo/) y los specs los referencian.

## Binarios externos embebidos

Las builds oficiales generadas por la CI embeben dos binarios externos
dentro del bundle, en `bin/`:

| Binario | Origen | Licencia | Función |
| --- | --- | --- | --- |
| `ffmpeg` | [johnvansickle.com](https://johnvansickle.com/ffmpeg/) (Linux), [gyan.dev](https://www.gyan.dev/ffmpeg/) (Windows), [evermeet.cx](https://evermeet.cx/ffmpeg/) (macOS) | GPL-2.0+ | Transcodificación de audio no-MP3 y composición de stems de karaoke |
| `fpcalc` | [acoustid/chromaprint](https://github.com/acoustid/chromaprint/releases) | LGPL-2.1+ | Fingerprint acústico para AcoustID |

El helper `infra.binarios.resolver_bin` los localiza dentro del bundle
(via `sys._MEIPASS/bin/` o junto al ejecutable) y cae al PATH del sistema
sólo si el bundle no los trae.

Detalle de licencias en [`THIRD_PARTY_LICENSES.md`](../THIRD_PARTY_LICENSES.md).

## Pipeline oficial (CI)

El workflow [`.github/workflows/release.yml`](../.github/workflows/release.yml)
construye los siguientes artefactos en cada tag `v*` (o vía
`workflow_dispatch`):

| OS | Formatos | Notas |
| --- | --- | --- |
| Linux | `.tar.gz`, `.AppImage`, `.deb`, `.rpm` | El `.deb` y `.rpm` declaran `vlc` como dependencia |
| Windows | `.zip`, `.exe` (NSIS) | El instalador detecta VLC y muestra link si falta |
| macOS | `.zip` (vía `ditto`), `.dmg` (vía `create-dmg`) | Universal binary cuando los runners lo permitan |

Cada artefacto viene con su archivo `.sha256` adjunto. La Release de GitHub
queda en estado `draft` hasta que un mantenedor la revisa y publica.

## Build local

### Prerrequisitos

```bash
pip install -r requirements.txt
pip install pyinstaller
```

Además:

- Python 3.12.
- VLC instalado (libVLC se carga vía `python-vlc` en runtime).
- Para Windows: Visual C++ Redistributable 2015–2022.
- Para macOS: Xcode Command Line Tools.

> Los builds locales **no embeben `ffmpeg` ni `fpcalc`** por defecto. La
> app los toma del PATH del sistema. Si querés replicar el bundle de la
> CI, copiá los binarios estáticos manualmente a `external_bin/` antes
> de invocar PyInstaller.

### Linux

```bash
bash packaging/linux/build.sh             # tar.gz
bash packaging/linux/build.sh --appimage  # tar.gz + AppImage (requiere appimagetool)
```

Para integrar con el escritorio sin instalador (mismo layout que el `.deb`/`.rpm`
oficial: el bundle vive en `/opt/nb-sound/` y el launcher se registra en el
`PATH` como `nb-sound`):

```bash
sudo cp -r dist/nb_sound /opt/nb-sound
sudo install -Dm755 packaging/linux/nb-sound-launcher /usr/local/bin/nb-sound
sudo install -Dm644 packaging/linux/nb-sound.desktop /usr/share/applications/nb-sound.desktop
sudo install -Dm644 ui/qml/assets/logo/logo_512.png /usr/share/icons/hicolor/512x512/apps/nb-sound.png
```

Tras instalar, el comando `nb-sound` queda disponible en la terminal:

```bash
nb-sound            # abre la interfaz gráfica
nb-sound cli --help # CLI del catalogador (mismo binario; ver docs/cli.md)
```

### Windows

```powershell
.\packaging\windows\build.ps1   # .zip portable

# Para el instalador .exe (requiere NSIS instalado):
makensis /DVERSION=1.0.0 /DSRC_DIR="$(Resolve-Path dist\nb_sound)" `
  packaging\windows\installer.nsi
```

### macOS

```bash
bash packaging/macos/build.sh           # .zip (.app empaquetado)
bash packaging/macos/build.sh --dmg     # .zip + .dmg (requiere create-dmg)
```

Para distribución pública fuera de la App Store es obligatorio:

1. Firmar con un Developer ID (`codesign`).
2. Notarizar con `notarytool`.
3. Adjuntar el ticket con `xcrun stapler staple`.

## Dependencias en el sistema destino

| Componente | Obligatorio | Estado en builds oficiales |
| --- | --- | --- |
| VLC | Sí | **No embebido** (el usuario instala VLC) |
| FFmpeg | Recomendado | Embebido en el bundle |
| Chromaprint (`fpcalc`) | Opcional | Embebido en el bundle |
| Demucs (modelo `htdemucs`) | Opcional | Se descarga en el primer uso (~80 MB) |
| Essentia + TensorFlow (modelos) | Opcional | Externo, descarga manual |

Si VLC no está disponible, la aplicación arranca pero muestra un aviso
crítico y la reproducción queda deshabilitada. El instalador `.exe` de
Windows lo detecta automáticamente y ofrece comandos de instalación
(`winget`, `choco`) o el link oficial.

## Tamaño esperado de los bundles

| Plataforma | Sin Demucs | Con Demucs (karaoke) |
| --- | --- | --- |
| Linux | ~330 MB | ~2.2 GB |
| Windows | ~360 MB | ~2.4 GB |
| macOS | ~390 MB | ~2.5 GB |

Las cifras incluyen `ffmpeg` estático (~80 MB) y `fpcalc` (~5 MB)
embebidos.

## Checklist previo a generar binarios

1. `pytest -q` pasa en el entorno del builder.
2. `python main.py --version` y `python main_ui.py --version` reportan
   la versión correcta.
3. Iconos actualizados en `ui/qml/assets/logo/`.
4. URLs del workflow (`FFMPEG_*_URL`, `CHROMAPRINT_VERSION`) siguen vivas.
5. Probar el binario generado en una VM o entorno limpio (sin venv de
   desarrollo) antes de publicar.
6. Si se distribuye en macOS: firmar y notarizar.
7. Si se distribuye en Windows: firmar con certificado válido para
   evitar advertencias de SmartScreen.
