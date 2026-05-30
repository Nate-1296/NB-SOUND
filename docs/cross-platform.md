# Compatibilidad cross-platform

Análisis sistemático de las asunciones de plataforma del proyecto (Linux,
Windows, macOS) y su estado de manejo. El patrón de referencia a detectar y
prevenir es el caso `essentia-tensorflow` en Windows (sin wheel funcional),
resuelto en la v1.0.1 ocultando la UI deep condicionalmente
(ver [qml-architecture.md](qml-architecture.md#deepanalyticsdisponible--gating-de-ui-por-plataforma)).

> Alcance: este documento cubre la **app de escritorio**. El análisis de
> compatibilidad de la app móvil (Android/iOS/tablets) vive en el proyecto
> `nb_sound_mobile/`.

---

## Resumen ejecutivo

La app ya maneja correctamente la mayor parte de las diferencias de
plataforma mediante tres mecanismos verificados en el código:

- **Resolución de rutas por SO** en `infra/bootstrap.py` (XDG / `%APPDATA%` /
  `~/Library`).
- **Resolución de binarios empaquetados** en `infra/binarios.py` con orden
  `_MEIPASS/bin` → adyacente al ejecutable → `PATH`, y sufijo `.exe`
  automático en Windows.
- **Detección de dependencias nativas** en `infra/dependencias.py`, con
  verificación aislada en subprocess para las que pueden hacer `SIGSEGV`
  (torch, demucs, essentia).

Los gaps abiertos son los listados en la tabla como **Acción requerida**.

---

## Tabla de compatibilidad por componente

| Componente | Linux | Windows | macOS | Problemas detectados | Acción requerida |
| --- | --- | --- | --- | --- | --- |
| **Rutas de datos/config** (`infra/bootstrap.py`) | XDG | `%LOCALAPPDATA%`/`%APPDATA%` | `~/Library` | Manejado: resolución por SO + creación idempotente | Ninguna |
| **ffmpeg / fpcalc** (`infra/binarios.py`) | bundle→PATH | bundle→PATH, sufijo `.exe` | bundle→PATH | Resolución correcta en los tres; falla blanda si falta (degradación) | Verificar que el CI empaqueta el binario por SO en `external_bin/` (Fase 5 del plan) |
| **libVLC / python-vlc** | `libvlc.so` | `libvlc.dll` | `libvlc.dylib` | `find_lib()` de python-vlc depende del SO; en Windows requiere VLC instalado o DLL en PATH | Documentar dependencia de VLC por SO en el instalador (ya en `dependencias.py` con URLs por SO) |
| **essentia-tensorflow** | wheel OK | **sin wheel funcional** | wheel parcial | Resuelto v1.0.1: UI deep oculta en Windows vía `deepAnalyticsDisponible` | Ninguna (revisar si aparece wheel Windows en el futuro) |
| **torch / demucs (Karaoke)** | CPU/CUDA | CPU/CUDA | CPU/MPS | Verificación en subprocess para evitar SIGSEGV; índice `whl/cpu` por defecto al instalar | Ninguna |
| **Subprocess deep** (`infra/deep_runner.py`) | OK | `CREATE_NO_WINDOW` aplicado | OK | Manejado: flag anti-ventana en Windows | Ninguna |
| **PATH en lanzadores sin shell** (`main_ui.py`) | COSMIC/Wayland/SDDM | — | — | Se antepone `_MEIPASS/bin` + `/usr/bin` para subprocess (ffprobe) | Ninguna (Linux-específico, ya resuelto) |
| **SQLite WAL** (`db/conexion.py`) | OK | OK | OK | `journal_mode=WAL` con fallback a `DELETE` si el FS no lo soporta (NFS) | Ninguna |
| **Separadores de PATH / rutas** | `/` `:` | `\` `;` | `/` `:` | Uso de `pathlib` y `os.pathsep` (verificado en `main_ui.py`) | Auditar usos de `/` literal en construcción de rutas (bajo riesgo) |
| **TORCH_HOME / cache Demucs** | XDG cache | `%LOCALAPPDATA%` | `~/Library/Caches` | Promoción de pesos entre caches (`_promover_pesos_demucs_si_corresponde`) | Ninguna |
| **Iconos / bundle de app** | `.png`/`.desktop` | `.ico`/NSIS | `.icns`/`.dmg` | Specs por SO en `packaging/{linux,windows,macos}` | Ninguna |
| **pkexec (reparación Python)** | sí | no aplica | no aplica | `repararPython` solo en Linux; Win/macOS muestran instrucciones | Ninguna |
| **Servidor local (ecosistema móvil)** | — | — | — | **No existe aún**: sin lib de servidor HTTP/WS, mDNS ni QR | Ver [mobile-ecosystem.md](mobile-ecosystem.md) y plan |

---

## Gaps de packaging (PyInstaller) por SO

Verificado en `packaging/`:

- **Hidden imports / datas comunes** en `packaging/_common.py`
  (`collect_extra_datas`, `collect_external_tools`, `base_datas`). Los specs
  por SO (`packaging/{linux,windows,macos}/nb_sound.spec`) los reutilizan.
- **Binarios externos**: `collect_external_tools` espera `ffmpeg` y `fpcalc`
  en `<root>/external_bin/` que el CI descarga **por SO**. Acción: confirmar
  en el workflow de release que los tres binarios se descargan para cada
  runner (gap a validar, no defecto confirmado).
- **essentia/tensorflow** no se empaquetan en ningún spec (coherente: deep es
  instalación on-demand vía plug & play, no parte del bundle base).
- **Runtime hooks**: `pyi_rth_linux_vlc.py` (Linux) y
  `pyi_rth_windows_stdio.py` (Windows) — hooks específicos ya presentes.

### Recomendación

Antes de publicar binarios del ecosistema móvil, añadir al plan una tarea de
**validación de bundle por SO** que verifique: (1) ffmpeg/fpcalc presentes y
ejecutables, (2) libVLC resoluble, (3) la nueva dependencia de servidor
(HTTP/WS) incluida en `hiddenimports` de los tres specs.

---

## Principios para evitar nuevos gaps

1. **Nunca hardcodear plataforma en la capa de presentación.** Evaluar una
   vez en Python (`sys.platform`) y exponer como propiedad/flag, como se hizo
   con `deep_analytics_disponible()`.
2. **Aislar dependencias nativas frágiles** en subprocess (patrón ya usado
   para torch/demucs/essentia).
3. **Degradación controlada**: si un binario/lib no está, la app debe seguir
   en modo reducido y registrarlo, no abortar.
4. **Toda ruta vía `pathlib`/`os.pathsep`**, nunca separadores literales.
5. **Cada dependencia nueva** (p. ej. el servidor del ecosistema móvil) debe
   añadirse al catálogo de `infra/dependencias.py` y a los tres specs.

---

← [Volver a architecture.md](architecture.md)
