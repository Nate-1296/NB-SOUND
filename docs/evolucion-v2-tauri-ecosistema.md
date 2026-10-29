# Plan de Evolución V2: Arquitectura Tauri, Reproductor Embebido y Ecosistema

> **Documento de Visión y Arquitectura Estratégica.**  
> Recoge las decisiones de reestructuración para la próxima iteración mayor de NB SOUND: migración del frontend a Tauri v2 + Svelte 5, sustitución de LibVLC por un motor de audio embebido en Rust, simplificación de la experiencia de usuario (UX) mediante revelación progresiva, y alineación estética con el sistema de diseño Material You (Material 3).

---

## 1. Justificación y Diagnóstico del Estado Actual

NB SOUND cuenta con un núcleo de catalogación e inteligencia musical extremadamente avanzado (~41.000 líneas de Python), pero arrastra una deuda técnica significativa en su capa de presentación y reproducción:

1. **La sobrecarga de PySide6 / QML:**
   * La UI actual suma **~27.150 líneas de QML** y **~11.844 líneas en `ui/modelos_qml.py`**.
   * `modelos_qml.py` actúa como un voluminoso adaptador de pegamento (`@Property`, `@Signal`, `@Slot`, wrapping dinámico en `QVariant` y workers manuales para evitar congelar el bucle de eventos de Qt).
   * El dialecto JavaScript de QML carece de tipado estricto, provocando errores en tiempo de ejecución (`ReferenceError`, bindings rotos durante el desmontaje) y dificultando el testing determinista.

2. **El conflicto de runtimes nativos y el GIL de Python:**
   * Cargar en un único proceso Python **PyTorch (Demucs) + Essentia/TensorFlow + LibVLC + PySide6 (Qt6)** genera colisiones entre librerías C++ y runtimes de threading (OpenMP/TBB), derivando en fallos de segmentación impredecibles.
   * Esto obligó históricamente a soluciones de contención como aislar cada test con `pytest-forked` y delegar el análisis musical profundo a un subproceso (`deep_runner.py`).

3. **Las limitaciones críticas de LibVLC (`python-vlc`):**
   * **Dependencia de sistema:** No es un componente autocontenido; depende de que el sistema operativo tenga VLC instalado o de compilar y distribuir un árbol complejo de librerías y plugins nativos.
   * **Hilos zombi y ciclo de vida:** LibVLC gestiona sus propios hilos en C; un cierre forzado o un teardown asíncrono incompleto puede dejar el audio sonando tras cerrar la aplicación.
   * **Desincronización en Karaoke y DJ:** Para el modo Karaoke se mantienen dos instancias de `MediaPlayer` de VLC en paralelo. Sincronizar dos reproductores externos por polling desde Python vía ctypes provoca saltos acústicos (*audio pops*), tirones y derivas temporales (*clock drift*).
   * **Vulnerabilidad al GIL:** Si el proceso de Python se satura calculando embeddings o separando stems al 100% de CPU, la entrega de buffers a VLC sufre micro-cortes.

---

## 2. La Nueva Arquitectura: División de Responsabilidades

Para resolver estos problemas sin perder el poder de los modelos de aprendizaje automático ya construidos en Python, se establece una **arquitectura desacoplada en tres capas**:

```text
┌────────────────────────────────────────────────────────────────────────┐
│               CAPA 1: FRONTEND (Tauri WebView)                         │
│  - Svelte 5 con Runes ($state, $derived, $effect)                      │
│  - TypeScript estricto de extremo a extremo                            │
│  - Sistema de diseño Material You (tokens CSS de paletas dinámicas)    │
│  - Virtualización de listas masivas (@tanstack/svelte-virtual)         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ IPC tipado (Tauri Commands / Events)
┌───────────────────────────────────▼────────────────────────────────────┐
│               CAPA 2: NÚCLEO DE SISTEMA & AUDIO (Rust / src-tauri)     │
│  - Reproductor de audio embebido (Symphonia + Kira / Rodio)            │
│  - Control D-Bus MPRIS (crate mpris-server para Linux)                 │
│  - Ciclo de vida de la ventana, bandeja del sistema y atajos globales   │
│  - Servidor de assets ultrarrápido (protocolo asset:// para portadas)  │
│  - Orquestador del proceso daemon de Python                            │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ IPC Local (WebSocket / JSON-RPC / Unix Socket)
┌───────────────────────────────────▼────────────────────────────────────┐
│               CAPA 3: MOTOR INTELIGENTE (Python Headless Daemon)       │
│  - Base de datos SQLite (db/) con consultas optimizadas                │
│  - Pipeline de catalogación, normalización, AcoustID y scraping        │
│  - Separación de stems con Demucs v4 (PyTorch)                         │
│  - Análisis acústico y embeddings con Essentia (MusiCNN)               │
│  - Algoritmo y narrativa musical del DJ Privado                        │
│  - Servidor de sincronización móvil (aiohttp / QR / WebSockets)        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Sustitución de VLC por un Motor de Audio Embebido en Rust

La reproducción de sonido abandona definitivamente Python y LibVLC, pasando a ser gestionada de forma nativa por el proceso de Rust en `src-tauri`:

### Bibliotecas seleccionadas:
* **[Symphonia](https://github.com/pdeljanov/Symphonia):** Decodificación de audio 100% en Rust puro para MP3, FLAC, WAV, AAC, OGG y ALAC. Sin dependencias externas de C/C++, sin librerías dinámicas de sistema.
* **[Kira](https://github.com/tesselode/kira) o [Rodio](https://github.com/RustAudio/rodio):** Motor de mezcla y reproducción. `Kira` está diseñado específicamente para audio interactivo y multipista:
  * Permite sincronización de stems a nivel de sample exacto.
  * Facilita crossfades paramétricos y curvas de volumen matemáticamente perfectas.
  * Soporta control de pitch/velocidad y transiciones automáticas.

### Beneficios inmediatos:
1. **Inmunidad al GIL de Python:** El motor de audio se ejecuta en un hilo nativo de alta prioridad en Rust. Aunque Python esté consumiendo el 100% de CPU/GPU en una tarea pesada de Demucs o Essentia, el audio **jamás tendrá tirones ni micro-cortes**.
2. **Karaoke perfecto:** Las pistas vocal e instrumental se cargan en el mismo motor de mezcla de Rust. Subir o bajar el volumen de la voz en tiempo real es una operación de ganancia de pista con latencia cero.
3. **Cierre limpio garantizado:** El ciclo de vida del audio está vinculado directamente al binario de Tauri. Al cerrar la ventana, el motor de sonido finaliza inmediatamente.
4. **Portabilidad absoluta:** El binario final incluye sus propios decodificadores; funciona en cualquier distribución Linux limpia, Windows o macOS sin requerir VLC preinstalado.

---

## 4. Reestructuración de la Experiencia de Usuario (UX)

Las pantallas actuales de `nb_sound` sufren de sobrecarga informativa técnica. La nueva interfaz implementará el principio de **revelación progresiva** (*progressive disclosure*): simplicidad por defecto, profundidad técnica accesible solo bajo demanda.

### A. Vista de Importación
* **Estado actual:** Muestra causas internas de rechazo ("puntaje_intermedio", "candidatos_ambiguos"), colas de deep analysis y tablas densas.
* **Rediseño V2:**
  * **Flujo primario:** Una zona limpia de arrastrar y soltar (*Drag & Drop*) con una barra de estado comprensible: *"Catalogando 150 canciones..."*.
  * **Resumen claro:** *"142 canciones agregadas a tu biblioteca. 8 canciones requieren tu atención."*
  * **Flujo secundario:** Un botón *"Revisar discrepancias"* abre un diálogo modal enfocado únicamente en resolver esas 8 pistas (comparador lado a lado de metadatos), ocultando el resto de la fontanería interna.

### B. Modo Karaoke
* **Estado actual:** Vista administrativa con selección masiva de checkboxes, tablas de stems y botones para asociar instrumentales manuales.
* **Rediseño V2:**
  * **El Karaoke pasa a ser una función del reproductor**, no una tarea de administración de archivos.
  * En la barra de reproducción y en la vista de letras sincronizadas se añade un botón con icono de micrófono 🎤 (*"Modo Karaoke"*).
  * Si la canción ya fue separada: conmuta instantáneamente entre la versión original y la instrumental.
  * Si aún no tiene stems: muestra un estado sutil: *"Preparando modo karaoke por primera vez (~25 seg)..."* mientras el audio original sigue sonando.
  * La vista dedicada a Karaoke en la barra lateral se transforma en una colección limpia: **"Listas para cantar"**, con una opción directa: *"Preparar mis favoritas para karaoke en segundo plano"*.

### C. Ajustes y Configuración
* **Estado actual:** Solicita configurar manualmente 6 directorios del sistema (`dir_entrada`, `dir_biblioteca`, `dir_cuarentena`, `dir_revision`, `dir_logs`, `dir_procesados`).
* **Rediseño V2:**
  * Una única opción principal: **"Carpeta de tu música"**.
  * Todas las carpetas auxiliares (`cache`, `modelos`, `cuarentena`, `logs`, `procesados`) se alojan de forma automática en los directorios estándar del sistema operativo (`~/.local/share/nb_sound` en Linux, `%APPDATA%/NBSound` en Windows).
  * Una sección plegable al final: **"Ajustes Avanzados"**, donde los usuarios avanzados pueden personalizar rutas si lo desean explícitamente.

---

## 5. Sistema de Diseño: Material You y Ecosistema Unificado

Siguiendo el estándar establecido en `NB_Books`, `NB_Sound V2` adoptará plenamente **Material 3 (Material You)**:

1. **Reutilización de Tokens:**
   * Integración del mismo esquema de variables CSS (`--m3c-surface`, `--m3c-primary`, `--m3c-surface-container-high`, etc.) generado por scripts automatizados de paletas.
   * Modos claro, oscuro y soporte para alto contraste accesible.

2. **Paletas Dinámicas reactivas al Álbum:**
   * En Svelte, mediante la librería oficial de Material Color Utilities, el frontend extraerá en tiempo real los colores primarios y secundarios de la carátula del álbum en reproducción.
   * La interfaz teñirá sutilmente el fondo, los controles del reproductor y los contenedores con la tonalidad de la canción activa, proporcionando una experiencia visual viva y cohesiva.

3. **Fluidez e interpolación de Seekbar a 60 fps:**
   * La barra de progreso no saturará el canal IPC con 30-60 eventos por segundo desde el backend.
   * El backend emitirá únicamente cambios de estado (`play`, `pause`, `seek`, `duracion`). El frontend de Svelte interpolará la posición actual usando `requestAnimationFrame` en el hilo de renderizado, garantizando un desplazamiento completamente fluido.

---

## 6. Nuevas Capacidades y Oportunidades de Producto

Aprovechando los datos acústicos ya almacenados en SQLite y la nueva arquitectura ágil, se incorporarán las siguientes características:

1. **Waveform Interactivo y Beat Grid:**
   * Generación y visualización de la forma de onda (*waveform*) sobre la barra de reproducción a partir de los datos de Essentia/Librosa.
   * En el **DJ Privado**, la onda mostrará los puntos de entrada/salida (*mix in/out markers*) y los cambios de energía antes de que ocurra la transición.

2. **Normalización de Sonoridad Profesional (EBU R128 / LUFS):**
   * Integración del cálculo de sonoridad integrada en LUFS durante el análisis de audio.
   * Aplicación transparente de ganancia ReplayGain 2.0 al decodificar en Rust para eliminar los saltos bruscos de volumen entre pistas antiguas y grabaciones modernas.

3. **Smart Playlists (Listas Inteligentes Vivas):**
   * Creación de listas dinámicas evaluadas en SQLite basadas en descriptores acústicos:
     * *Modo Concentración:* Instrumental = true, BPM entre 75 y 105, Energía < 0.4.
     * *Energía Pura:* BPM > 125, Bailabilidad > 0.7.
     * *Joyas Olvidadas:* Canciones con calificación alta no reproducidas en más de 6 meses.

4. **Estadísticas Profundas Locales ("Wrapped" Privado):**
   * Generación de resúmenes de escucha periódicos (mensuales/anuales) 100% locales y sin telemetría:
     * Gráfico radar de estados de ánimo dominantes.
     * Mapa de calor de horas de escucha por día de la semana.
     * Generación de tarjetas visuales exportables para compartir.

5. **Sincronización a Dispositivos Físicos (DAPs y USBs Hi-Fi):**
   * Herramienta para transferir playlists seleccionadas a tarjetas microSD, memorias para automóviles o reproductores portátiles dedicados (FiiO, Walkman, Shanling), organizando automáticamente las carpetas e incrustando las portadas en los metadatos.

6. **Modo Jukebox / Fiesta Local:**
   * Extensión del servidor local de sincronización móvil: visualización de un código QR en pantalla para que los invitados en la misma red Wi-Fi puedan sugerir y encolar canciones desde su navegador sin instalar aplicaciones.

---

## 7. Estrategia de Migración y Estabilidad

La transición se ejecutará de forma modular para no congelar el avance del proyecto:

1. **Fase 1 — Desacoplamiento del Backend:**  
   Convertir las interfaces de `servicios/` en un servidor de comandos local (JSON-RPC o WebSocket en `localhost`). Las llamadas a la base de datos y tareas en segundo plano se aíslan de cualquier API de Qt.
2. **Fase 2 — Shell Tauri y Reproductor Rust:**  
   Implementar la base de Tauri v2 con el motor de audio embebido en Rust (`Symphonia` + `Kira`). Verificar reproducción pura, cola y ecualizador básico con tests de integración.
3. **Fase 3 — Frontend Svelte 5 con Material You:**  
   Construcción de los componentes principales (Shell maestro, Reproductor, Biblioteca virtualizada, Buscador).
4. **Fase 4 — Migración de Vistas Complejas:**  
   Reescribir Importación, DJ Privado, Karaoke y Explorador Ciego aplicando las directrices de revelación progresiva.
5. **Fase 5 — Depuración y Retiro de Qt:**  
   Eliminación de `ui/modelos_qml.py`, `ui/qml/`, `workers/workers_qt.py` y las dependencias de `PySide6` de `pyproject.toml`.
