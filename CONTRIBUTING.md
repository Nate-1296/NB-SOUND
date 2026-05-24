# Guía de contribución — NB SOUND

¡Gracias por tu interés en el proyecto!

---

## Antes de contribuir

NB SOUND es software libre bajo **GPL-3.0-or-later**. Al contribuir aceptas que tu código se distribuirá bajo esa misma licencia.

Si tienes una idea grande, abre un issue primero para discutirla antes de ponerte a programar. Para bugs o mejoras pequeñas, un PR directo está bien.

---

## Configurar el entorno de desarrollo

```bash
# Linux / macOS
git clone https://github.com/Nate-1296/NB-SOUND.git nb_sound && cd nb_sound
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# Editar .env con rutas locales (opcional: la UI las genera al primer arranque)
```

```powershell
# Windows (PowerShell)
git clone https://github.com/Nate-1296/NB-SOUND.git nb_sound
cd nb_sound
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Verifica que todo funcione:

```bash
pytest -q
python main_ui.py --version
```

> El primer arranque sin `.env` es seguro: `infra.bootstrap` crea las rutas
> estandar del SO (XDG en Linux, `%APPDATA%` en Windows, `~/Library/...`
> en macOS) y genera un `.env` minimo.

---

## Flujo de trabajo

```bash
# Crear rama desde main
git checkout -b fix/descripcion-corta
# o
git checkout -b feat/descripcion-corta

# Hacer cambios, luego:
pytest -q
git add <archivos específicos>
git commit -m "fix: descripción clara del cambio"
git push origin fix/descripcion-corta
# Abrir PR contra main
```

**Convención de commits** (`conventional commits`):

| Prefijo | Cuándo usarlo |
| --- | --- |
| `feat:` | Nueva funcionalidad |
| `fix:` | Corrección de bug |
| `docs:` | Solo documentación |
| `refactor:` | Refactor sin cambio funcional |
| `test:` | Tests nuevos o ajustados |
| `chore:` | Tareas de mantenimiento |

---

## Estándares de código

- Python 3.12, type hints en funciones nuevas
- Sin comentarios obvios; solo cuando el *por qué* no es evidente
- No introducir lógica de negocio en QML ni en los modelos QML — eso va en servicios Python
- Los modelos QML solo exponen propiedades, señales y slots; delegan en `servicios/`
- Tests para toda funcionalidad nueva que toque la capa de servicio o de datos

### Tests

```bash
pytest -q              # Suite completa
pytest tests/test_X.py # Un archivo específico
```

Los tests no deben requerir internet, VLC instalado ni modelos de Essentia. Usa mocks para todo lo externo.

### Smoke test de QML

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. timeout 10 \
  .venv/bin/python -c "
import tempfile
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine
from db.conexion import inicializar_db
app = QApplication([])
inicializar_db(Path(tempfile.gettempdir()) / 'smoke_test.sqlite')
engine = QQmlApplicationEngine()
engine.addImportPath('ui/qml')
engine.load('ui/qml/Principal.qml')
print('OK' if engine.rootObjects() else 'ERROR')
"
```

> `tempfile.gettempdir()` resuelve el temp directory correcto para cada SO:
> `/tmp` en Linux/macOS, `%TEMP%` (usuario actual) en Windows. NO hardcodear
> `/tmp`.

## Empaquetado

Los specs PyInstaller estan en `packaging/{linux,windows,macos}/nb_sound.spec`.
Para construir localmente:

```bash
# Linux
bash packaging/linux/build.sh             # tar.gz
bash packaging/linux/build.sh --appimage  # tar.gz + AppImage si appimagetool esta presente

# macOS
bash packaging/macos/build.sh             # .zip via ditto
bash packaging/macos/build.sh --dmg       # .zip + .dmg si create-dmg esta instalado
```

```powershell
# Windows
.\packaging\windows\build.ps1
```

La CI de GitHub Actions construye los 3 targets automaticamente al crear
una tag `v*` (ver `.github/workflows/release.yml`).

---

## Qué tipos de contribución son bienvenidas

- **Bugs**: abre un issue con pasos para reproducir y la versión de Python/SO
- **Mejoras de UI**: ten en cuenta los tokens de diseño (`UiTokens.qml`) y los patrones existentes
- **Nuevos servicios Python**: sigue el patrón de `servicios/biblioteca.py`
- **Tests**: siempre bienvenidos, especialmente para casos límite
- **Documentación**: correcciones, ejemplos, traducciones

---

## Qué evitar

- No introducir dependencias propietarias ni incompatibles con GPL-3.0
- No escribir lógica de negocio directamente en QML
- No acceder a SQLite desde QML ni desde los modelos directamente — usa servicios
- No añadir `ToolTip` en archivos QML (convención del proyecto: no se usan tooltips)
- No omitir tests para código nuevo que toque servicios o la capa de datos

---

## Licencia de tu contribución

Al enviar un PR confirmas que:

1. Tu código cumple con GPL-3.0-or-later
2. Tienes derecho a contribuirlo
3. Aceptas que se distribuirá bajo GPL-3.0-or-later
4. No incluye código de terceros con licencia incompatible

---

## ¿Dudas?

Abre un issue. Nos interesa que el proceso sea claro y que contribuir no dé miedo.
