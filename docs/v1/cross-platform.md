# Compatibilidad cross-platform

Análisis sistemático de las asunciones de plataforma del proyecto (Linux,
Windows, macOS) y su estado de manejo. El patrón de referencia a detectar y
prevenir es el caso `essentia-tensorflow` en Windows (sin wheel funcional),
resuelto ocultando la UI deep condicionalmente
(ver [qml-architecture.md](qml-architecture.md#deepanalyticsdisponible--gating-de-ui-por-plataforma)).

> Alcance: este documento cubre la **app de escritorio**. El análisis de
> compatibilidad de la app móvil (Android/iOS/tablets) vive en el proyecto
> [NB Sound Mobile](https://github.com/Nate-1296/NB-SOUND-MOBILE).

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
| **ffmpeg / fpcalc** (`infra/binarios.py`) | bundle→PATH | bundle→PATH, sufijo `.exe` | bundle→PATH | Resolución correcta en los tres; falla blanda si falta (degradación) | El CI empaqueta el binario por SO en `external_bin/` |
| **libVLC / python-vlc** | `libvlc.so` | `libvlc.dll` | `libvlc.dylib` | `find_lib()` de python-vlc depende del SO; en Windows requiere VLC instalado o DLL en PATH | Documentar dependencia de VLC por SO en el instalador (ya en `dependencias.py` con URLs por SO) |
| **essentia-tensorflow** | wheel OK | **sin wheel funcional** | wheel parcial | Resuelto: UI deep oculta en Windows vía `deepAnalyticsDisponible` | Ninguna |
| **torch / demucs (Karaoke)** | CPU/CUDA | CPU/CUDA | CPU/MPS | Verificación en subprocess para evitar SIGSEGV; índice `whl/cpu` por defecto al instalar | Ninguna |
| **Subprocess deep** (`infra/deep_runner.py`) | OK | `CREATE_NO_WINDOW` aplicado | OK | Manejado: flag anti-ventana en Windows | Ninguna |
| **PATH en lanzadores sin shell** (`main_ui.py`) | COSMIC/Wayland/SDDM | — | — | Se antepone `_MEIPASS/bin` + `/usr/bin` para subprocess (ffprobe) | Ninguna (Linux-específico, ya resuelto) |
| **SQLite WAL** (`db/conexion.py`) | OK | OK | OK | `journal_mode=WAL` con fallback a `DELETE` si el FS no lo soporta (NFS) | Ninguna |
| **Separadores de PATH / rutas** | `/` `:` | `\` `;` | `/` `:` | Uso de `pathlib` y `os.pathsep` (verificado en `main_ui.py`) | Resuelto: auditoría completada (sin separadores literales en construcción de rutas) |
| **TORCH_HOME / cache Demucs** | XDG cache | `%LOCALAPPDATA%` | `~/Library/Caches` | Promoción de pesos entre caches (`_promover_pesos_demucs_si_corresponde`) | Ninguna |
| **Iconos / bundle de app** | `.png`/`.desktop` | `.ico`/NSIS | `.icns`/`.dmg` | Specs por SO en `packaging/{linux,windows,macos}` | Ninguna |
| **pkexec (reparación Python)** | sí | no aplica | no aplica | `repararPython` solo en Linux; Win/macOS muestran instrucciones | Ninguna |
| **Servidor local (ecosistema móvil)** | `aiohttp`+`zeroconf`+`qrcode`+`cryptography` | igual | igual | **Resuelto**: servidor HTTPS/WSS en hilo propio (`servicios/servidor_sync.py`), mDNS y QR. **TLS** autofirmado con huella TOFU; bind a la IP de la subred LAN; puerto libre (8731–8799); arranque bajo demanda; selección negociable y manifest paginable | Ninguna (deps en los 3 specs y en `requirements*.txt`; verificado por `tests/test_packaging_artifacts.py`) |

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
- **Servidor de sincronización**: `aiohttp`, `zeroconf` y `qrcode` se incluyen
  vía `_DYNAMIC_SUBMODULES` (sus submódulos dinámicos) y los módulos
  `servicios.servidor_sync` / `servicios.sync_repositorio` / `servicios.backup`
  vía `_HIDDEN_IMPORTS_BASE` en `packaging/_common.py` — compartido por los tres
  specs. También están en `requirements.txt` y `requirements-release.txt`.
- **Runtime hooks**: `pyi_rth_linux_vlc.py` (Linux) y
  `pyi_rth_windows_stdio.py` (Windows) — hooks específicos ya presentes.

### Recomendación

La **validación de bundle por SO** está cubierta por
`tests/test_packaging_artifacts.py`: verifica que (1) los módulos de sync están
en `hiddenimports`, (2) `aiohttp`/`zeroconf`/`qrcode` están en
`_DYNAMIC_SUBMODULES` y en `requirements*.txt`, (3) `collect_external_tools`
mapea `external_bin/{ffmpeg,fpcalc}` a `bin/`. El workflow de release ya
descarga ffmpeg/fpcalc por SO y falla si no aparecen en el bundle.

### Nota de seguridad — TLS (TOFU)

El servidor de sincronización opera con **TLS (HTTPS + WSS)** mediante un
certificado **autofirmado** generado y persistido por el PC
(`infra/tls_local.py`, requiere `cryptography`). La confianza es **TOFU**: el
QR lleva la huella SHA-256 del certificado y el cliente la fija; en cada
conexión valida el cert por huella (no por CA ni hostname), logrando
confidencialidad y mitigación de MitM en la LAN sin depender de una autoridad
certificadora. Defensa en capas: además del TLS, se exige **token por
petición** (`device_token` tras emparejar por QR con token efímero de un solo
uso) y bind a la IP de la subred del WiFi (nunca `0.0.0.0` público). La huella
es estable entre reinicios (cert persistido) para no romper el emparejamiento.
Degradación: si faltara `cryptography`, el servidor cae a HTTP plano (LAN +
token) y lo registra; el release oficial incluye `cryptography`.

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
