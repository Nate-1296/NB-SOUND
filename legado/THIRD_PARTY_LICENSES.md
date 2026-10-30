# Componentes de terceros

NB SOUND se distribuye bajo **GPL-3.0-or-later** (ver [`LICENSE`](LICENSE)).
Las builds binarias oficiales embeben dos componentes externos compatibles
con esa licencia. Esta nota documenta cada uno con su licencia, su fuente y
el motivo por el que se incluye.

## FFmpeg

- **Componente**: binario estático `ffmpeg` para Linux, Windows y macOS.
- **Versión**: la última estable de la serie 6.x al momento del build.
- **Licencia**: GPL-2.0-or-later (build GPL de FFmpeg con `libx264`,
  `libmp3lame`, etc.). Compatible con GPL-3.0-or-later, que es la licencia
  bajo la que se distribuye NB SOUND.
- **Sitio oficial**: https://www.ffmpeg.org/
- **Builds usadas**:
  - Linux: https://johnvansickle.com/ffmpeg/ (static builds)
  - Windows: https://www.gyan.dev/ffmpeg/builds/
  - macOS: https://evermeet.cx/ffmpeg/
- **Para qué se usa**: transcodificación de formatos de audio no-MP3 al
  pipeline interno (FLAC, M4A, OGG, WAV → MP3) y conversión de stems
  generados por Demucs en la separación voz/instrumental del karaoke.
- **Fuente del código**: https://git.ffmpeg.org/ffmpeg.git — distribuible
  por separado conforme a la GPL.

## Chromaprint (`fpcalc`)

- **Componente**: binario `fpcalc` provisto por Chromaprint.
- **Versión**: 1.5.x.
- **Licencia**: LGPL-2.1-or-later. Compatible con GPL-3.0-or-later mediante
  la cláusula 3 de la GPL.
- **Sitio oficial**: https://acoustid.org/chromaprint
- **Build usada**: https://github.com/acoustid/chromaprint/releases
- **Para qué se usa**: generar fingerprints acústicos de pistas para el
  cliente AcoustID, que identifica grabaciones por audio contra la base
  abierta de MusicBrainz.
- **Fuente del código**: https://github.com/acoustid/chromaprint —
  distribuible por separado conforme a la LGPL.

## Dependencias Python (instaladas vía `pip`)

Las builds embeben el árbol Python con las dependencias declaradas en
[`requirements.txt`](requirements.txt). Cada paquete mantiene su propia
licencia; ninguna entra en conflicto con GPL-3.0-or-later. Las principales:

| Paquete | Licencia |
| --- | --- |
| PySide6 | LGPL-3.0 |
| python-vlc | LGPL-2.1-or-later |
| mutagen | GPL-2.0-or-later |
| musicbrainzngs | BSD-2-Clause |
| Pillow | MIT-CMU |
| python-dotenv | BSD-3-Clause |
| pyacoustid | MIT |
| librosa | ISC |
| demucs | MIT |
| torch | BSD-3-Clause |
| numpy | BSD-3-Clause |
| soundfile | BSD-3-Clause |
| shazamio | MIT |
| anthropic | MIT |
| openai | Apache-2.0 |

## Componentes NO embebidos pero usados en runtime

- **libVLC** (parte del paquete VLC del sistema): LGPL-2.1-or-later.
  El usuario debe instalar VLC por separado. NB SOUND solo carga libVLC
  via `python-vlc` sin redistribuirlo.
- **Modelos de Demucs** (`htdemucs` y derivados): se descargan en el primer
  uso desde el CDN oficial de Facebook AI Research. Licencia MIT.
- **Modelos de Essentia/TensorFlow** (opcionales para Audio Intelligence
  profunda): deben descargarse manualmente. Cada uno mantiene su licencia,
  publicada por Music Technology Group en https://essentia.upf.edu/.

## Cómo obtener el código fuente de los componentes GPL/LGPL

Si redistribuyes una build binaria de NB SOUND, debes ofrecer el código
fuente correspondiente de los componentes GPL/LGPL que embebe, o un enlace
a ellos. Los enlaces oficiales listados arriba son suficientes para cumplir
con esa obligación.
