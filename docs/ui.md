# Interfaz gráfica (UI)

La UI de NB SOUND es una aplicación PySide6/QML que te permite usar el cerebro del proyecto sin abrir una terminal. Comparte la misma base de datos que el CLI.

```bash
python main_ui.py

# Con base de datos específica
python main_ui.py --db /ruta/a/nb_sound.sqlite3
```

---

## Vistas principales

### Inicio

Dashboard musical con acceso a todo lo que ya escuchaste y lo que aún no:

- Resumen de biblioteca (pistas, artistas, álbumes, duración)
- "Vuelve a tu música" — grid con pistas, álbumes y artistas recientes con historial
- Playlists destacadas — listas relevantes priorizadas automáticamente
- Últimos añadidos — lo que entró más recientemente
- Top 10 canciones, artistas y álbumes más escuchados
- Álbumes que vuelven a aparecer

### Buscar

Dos modos en la misma pantalla:

**Búsqueda clásica** — desde 1 carácter, tolerante a acentos y typos leves. Resultados separados por artistas, álbumes y pistas. Las favoritas aparecen destacadas arriba. Clic en álbum navega a su detalle; clic en artista navega a su vista; clic en pista la reproduce.

**Háblale a tu biblioteca** — lenguaje natural. Escribe "algo triste pero con energía" o "música para concentrarme" y la app interpreta la intención usando los features de audio disponibles. Si no hay features suficientes, informa el estado y orienta al usuario.

### Biblioteca

Exploración completa de tu colección catalogada:

- **Álbumes** — grid con portadas, navegación a detalle de álbum
- **Artistas** — grid con imágenes, discografía, pistas destacadas y estadísticas
- **Pistas** — listado completo con filtros, orden y acciones rápidas

Desde cualquier sección puedes reproducir, encolar, ir al álbum o ir al artista.

### Playlists

Sistema local completo de listas de reproducción:

- **Me gusta** — se sincroniza automáticamente desde los favoritos marcados en cualquier vista
- **Manuales** — crea, renombra, edita, añade canciones, reordena y borra
- **Automáticas** — generadas desde tu historial y biblioteca: favoritas, recientes, tops, "This is...", mixes por artista/álbum y moods si hay features de audio
- **Portadas** — collage automático con Pillow a partir de las portadas de las canciones

La vista combina un explorador categorizado con filtros, preview lateral y detalle tipo álbum.

### Importar

Usa el cerebro CLI desde la interfaz, sin abrir terminal:

- **Modo simple** — selecciona carpeta y pulsa iniciar. Muestra progreso y resumen final.
- **Modo pro** — dry-run previo, progreso detallado por etapa, ETA, historial de ejecuciones y panel de revisión/cuarentena integrado. Audio Intelligence background con controles de pausa/reanudar/cancelar.

La importación corre en background y nunca bloquea la interfaz.

### Configuración

- **Básica** — rutas del sistema, toggles de Shazam y AcoustID, clave de AcoustID, modo de aceptación
- **Avanzada** (solo modo Pro) — todas las variables de `.env` agrupadas por bloque
- **Personalización** — tema visual, tipografía y escala de UI

### Perfil

Dashboard de identidad musical personal basado exclusivamente en tu historial local:

- Cabecera con foto de perfil (o iniciales), nombre editable y tags de identidad (año favorito, hora pico, días activos)
- Resumen de escucha: pistas, artistas y álbumes distintos escuchados, tiempo total
- Mood del día: género o artista dominante en las escuchas de hoy
- Actividad mensual: cuadrícula de 31 días con intensidad de escucha
- Top canciones, álbumes y artistas (con navegación inteligente: clic en álbum abre biblioteca)
- Tus extremos: lo más repetido vs lo que nunca ha sonado
- Lo que podrías probar: sugerencias de tu propia biblioteca, paginables

### Karaoke

Vista dedicada a preparar pistas para cantar encima. Gestiona la cola de separación voz/instrumental con Demucs y muestra el estado de cada pista (sin preparar, en cola, procesando, lista, fallida, no aplica). Cuando una pista está lista, el reproductor expone el botón de karaoke para conmutar entre la mezcla original y el instrumental sin perder posición ni lyrics.

→ Ver [docs/karaoke.md](karaoke.md) para los detalles del subsistema.

### DJ Privado

Director musical automático: describes el ambiente que quieres ("algo cinematográfico con voces femeninas") y la app construye una sesión continua de tu biblioteca, mezclada en vivo con cortes en el beat, fundidos, EQ kill y capas con stems. El audio del DJ es exclusivo: mientras suena, el reproductor estándar queda en pausa.

Tres pestañas: **Construir** (prompt + sugerencias + chips de vocabulario), **Sesión** (reproductor propio con timeline y lista de pistas) e **Historial** (sesiones previas, retomables o guardables como playlist).

→ Ver [docs/dj_privado.md](dj_privado.md) para la arquitectura completa.

### Explorador Ciego (¡A ciegas!)

Juego de redescubrimiento sobre tu propia biblioteca. Cuatro modos:

- **Adivina por portada** — la portada aparece borrosa; revelar va bajando el blur.
- **Adivina por audio** — un fragmento de ~12 segundos sin ningún dato visual.
- **Redescubrimiento** — canciones que amabas y dejaste de poner hace tiempo.
- **Lo que nunca eliges** — pistas con cero (o casi cero) reproducciones.

La ronda configura 3, 5, 8 o 12 canciones. Para cada una puedes:

- Reproducir el fragmento (la barra inferior queda con título, artista, álbum y portada censurados como `???`).
- Pedir pistas progresivas (con qué letra empieza/termina, cuántas palabras, cuántas letras, qué alfabeto).
- Escribir el título y pulsar Enter para validar; la comparación tolera tildes, mayúsculas, apóstrofes curvos, comillas y guiones distintos.
- Para títulos con caracteres no latinos (cirílico, CJK, etc.) el input se reemplaza por un botón **¡La sé!** porque tipear esos alfabetos no es realista en la mayoría de teclados.
- Reproducir completa, añadir a la cola, marcar como favorita, ir al artista o álbum (cuando ya están revelados).
- Revelar el título (sin penalización) o rendirse (marca la canción como saltada).

Mientras juegas, los controles del reproductor de la barra inferior (play/pausa, anterior, siguiente, seek) se bloquean sobre la pista del reto para que no puedas spoilearte. Al avanzar de canción, la cola y la barra se vacían: la pista anterior queda abandonada sin posibilidad de retroceder.

→ Ver [docs/explorador-ciego.md](explorador-ciego.md) para la arquitectura del juego.

---

## Reproductor

Controles completos en la barra inferior:

- Play/pause, anterior y siguiente
- Seek con barra de progreso
- Control de volumen
- Modo aleatorio y repetición (ninguna / pista / cola)
- **Sorpréndeme bien** — elige una pista inteligente de tu biblioteca sin repetir
- Cola visual reordenable con drag & drop
- Botón de karaoke (visible solo cuando la pista tiene versión instrumental preparada)

**Modos de visualización:**

- **Lyrics** — letra de la pista en overlay, con autohide de barra
- **Fullscreen** — portada grande y datos de la pista (modo contemplativo)
- **Fullscreen con lyrics** — letra a pantalla completa
- **Mini player** — ventana pequeña flotante con controles mínimos

---

## Modo simple / Pro

El modo se cambia desde la barra lateral o desde Configuración.

**Simple** — flujo cotidiano sin saturar. Importación en un clic, menos opciones visibles.

**Pro** — control granular. Importación con dry-run, resultados detallados, historial, panel de revisión, configuración avanzada y más.

Las vistas de Perfil, Karaoke, DJ Privado y Explorador Ciego están disponibles en ambos modos.

---

## Temas y personalización

61 paletas predefinidas (oscuras, claras, neutras y editoriales) más un tema personalizado donde defines tus propios colores. Todas tienen contraste WCAG calculado dinámicamente: el color del texto sobre cada acento se ajusta solo según la luminancia para que nunca quede ilegible.

También puedes cambiar la tipografía y la escala de la UI (100 % a 200 %). Los cambios se aplican al instante y persisten entre sesiones.

---

## Atajos de teclado

Los atajos de reproducción son configurables desde Configuración > Avanzada. Por defecto no hay atajos globales asignados para no interferir con otros programas.

---

← [Volver al README](../README.md)
