# Explorador Ciego (¡A ciegas!)

Juego de redescubrimiento musical sobre tu propia biblioteca local. No es un reproductor con quiz pegado encima: es un loop de adivinanza con cuatro modos, sistema de pistas progresivas y validación tolerante por escritura.

Toda la lógica corre con metadatos, portadas y audio locales. Sin internet, sin telemetría, sin APIs externas.

---

## 1. Visión

El usuario inicia una ronda en uno de cuatro modos y juega contra su propia biblioteca:

- **Adivina por portada** — la portada se muestra con blur progresivo; revelar artista/álbum baja el blur, revelar título lo elimina.
- **Adivina por audio** — un fragmento de ~12 s sin ningún dato visual.
- **Redescubrimiento** — canciones que el usuario amó (favoritas o con historial) y dejó de poner hace tiempo.
- **Lo que nunca eliges** — pistas con cero (o casi cero) reproducciones.

La ronda dura 3, 5, 8 o 12 canciones. Por cada una el usuario puede reproducir el fragmento, pedir pistas progresivas, escribir el título, reproducir completa, añadir a la cola, marcar favorita, revelar o rendirse.

El juego nunca compite con el reproductor: lo reutiliza con un mecanismo de censura controlado por flag (ver [playback-architecture.md](playback-architecture.md#modo-ciego-explorador-ciego)).

---

## 2. Estructura del módulo

```text
servicios/explorador_ciego/
├── __init__.py        # API pública del paquete
├── modelos.py         # ModoExplorador, EstadoReto, NivelRevelacion, Reto, ResumenRonda
├── selectores.py      # SQL aislado por modo: pools de pistas candidatas
├── hints.py           # Normalización, validación tolerante, generadores de pistas
└── servicio.py        # ExploradorCiegoService — estado de ronda + transiciones
```

Capas externas:

- `ui/modelos_qml.py::ModeloExploradorCiego` — puente QML, coordina servicio + reproductor + timer del fragmento.
- `ui/qml/vistas/VistaExploradorCiego.qml` — UI con tres pantallas (inicio, jugando, fin).
- `ModeloReproductor.set_modo_ciego(id)` / `limpiar_modo_ciego()` — censura visual en la barra inferior y la cola.

El servicio Python es puro: no toca Qt, no toca VLC, no toca SQLite (lee de `db.conexion` igual que el resto del catálogo pero no persiste estado del juego). Toda la ronda vive en memoria del proceso; al cerrar la app, desaparece.

---

## 3. Modos y selectores

`servicios/explorador_ciego/selectores.py` aísla la consulta SQL de cada modo. Todos filtran por `estado='biblioteca'` y `ruta_archivo` no vacío, devuelven hasta 400 candidatos aleatorizados y normalizan portadas via `biblioteca._normalizar_pista_fila`.

| Modo | Pool de pistas |
| --- | --- |
| `portada` | Pistas con portada resoluble (archivo en disco o `mb_release_id` del álbum) |
| `audio` | Cualquier pista con `duracion_seg > 30` |
| `redescubrimiento` | Favoritas o con historial, ordenadas por último acceso ascendente |
| `nunca_eliges` | `historial.reproducciones = 0` y `pistas.veces_reproducida = 0`; fallback relajado a `<= 2` cuando la biblioteca no tiene cola larga |

`contar_disponibles(modo)` cuenta sin cargar payloads completos: la UI lo usa para mostrar "N pistas listas" en las tarjetas de modo.

---

## 4. Máquina de estados del reto

```text
NivelRevelacion: OCULTO → ARTISTA → ALBUM → TOTAL
EstadoReto:      EN_CURSO → ACERTADO | REVELADO | PASADO
```

El nivel controla qué metadatos son visibles; el estado registra cómo terminó cada reto para el resumen final.

### Transiciones de nivel

- `revelar_artista()` — `OCULTO → ARTISTA`
- `revelar_album()` — `OCULTO|ARTISTA → ALBUM`
- `revelar_total()` — cualquier nivel → `TOTAL`; si el estado era `EN_CURSO`, pasa a `REVELADO`

### Transiciones de estado

- `intentar_adivinar(texto)` — valida contra el título real; si acierta, marca `ACERTADO` y eleva nivel a `TOTAL`; si no, incrementa `intentos_fallidos`
- `marcar_acertada()` — salida alternativa cuando el alfabeto no permite escritura: marca `ACERTADO` con confianza, sin validar
- `marcar_pasado()` — el usuario salta sin resolver; solo aplica si el estado era `EN_CURSO`
- `avanzar()` — si el reto sigue `EN_CURSO`, lo marca como `PASADO` automáticamente; devuelve el siguiente reto o `None` si la ronda termina

Para el botón "Me rindo" la UI invoca `marcar_pasado()` *antes* que `revelar_titulo()`: si se invierte el orden, `revelar_total` cambia `EN_CURSO → REVELADO` y la rendición ya no aplica.

---

## 5. Validación tolerante

`hints.normalizar_para_comparar(texto)` aplica un pipeline pensado para perdonar todo lo que un usuario "olvidaría" al teclear un título:

1. **Pre-normalización** — comillas (`‘ ’ ‚ “ ” „ « »`), apóstrofes (`ʼ` `` ` ``), guiones (`– — − ‐`) y `…` colapsan a su forma ASCII.
2. **NFD + strip de diacríticos** — `Canción` y `Cancion` quedan idénticos.
3. **Lowercase**.
4. **Strip de puntuación** — paréntesis, comas, signos pasan a espacio.
5. **Colapso de espacios**.

`validar_intento(real, intento)` devuelve `{"acierto", "cerca", "ratio"}`:

- `acierto` si `ratio >= 0.84` (incluye igualdad tras normalizar)
- `cerca` si `0.62 <= ratio < 0.84` — feedback "muy cerca"
- resto → fallido

El ratio se calcula con `difflib.SequenceMatcher` sobre los textos normalizados (truncados a 200 chars). Ejemplos que aciertan:

| Título real | Intento | Resultado |
| --- | --- | --- |
| `Canción del Mar` | `cancion del mar` | acierto |
| `Don't Stop Believin'` | `dont stop believin` | acierto |
| `Don’t Stop` (apóstrofe curvo) | `Don't Stop` (ASCII) | acierto |
| `Bohemian Rhapsody` | `Bohemia Rapsody` | acierto (ratio ≈ 0.94) |
| `Stairway to Heaven` | `Stairway Heaven` | cerca |
| `We Are Never Ever Getting Back Together` | `we are never ever getting back together` | acierto |

---

## 6. Pistas (hints)

`hints.generar_hints(titulo)` produce el catálogo completo:

| Clave | Contenido |
| --- | --- |
| `empieza_con` | Primera letra/dígito alfanumérico, en mayúscula |
| `termina_con` | Última letra/dígito alfanumérico, en mayúscula |
| `cantidad_palabras` | Palabras separadas por espacios |
| `cantidad_letras` | Caracteres alfanuméricos (sin contar espacios ni puntuación) |
| `alfabeto` | `latino`, `cirilico`, `griego`, `arabe`, `chino`, `japones`, `coreano`, `devanagari`, `hebreo`, `otro` |

`revelar_hint(clave)` solo acepta las cinco claves del catálogo; cualquier otra cadena se ignora silenciosamente (la UI no puede forzar la revelación de campos privados).

Las hints son acumulativas y *no* penalizan en el resumen. Lo único que cuenta es si la canción se acertó, se reveló o se saltó.

---

## 7. Alfabeto y modo de entrada

`hints.requiere_escritura(titulo)` decide si la UI ofrece input de texto o solo el botón "¡La sé!":

- Es `True` solo si **todos** los caracteres alfabéticos del título son latinos (rango U+0000–U+024F).
- Un único carácter no latino (p. ej. `花` en `Song 花 Title`) hace que sea `False`: pedir teclear ese símbolo en un teclado típico es irreal y rompe el flow del juego.
- Números, puntuación y espacios no cuentan: `99 Luftballons`, `Don't Stop!` y `(I Can't Get No) Satisfaction` siguen requiriendo escritura.

`detectar_alfabeto(titulo)` devuelve el alfabeto dominante (el que más codepoints alfabéticos aporta) — la UI lo usa solo para el chip informativo "Alfabeto: cirílico".

---

## 8. Censura visual del reproductor

Mientras hay un fragmento del juego en curso, el `ModeloReproductor` aplica un flag `blind_pista_id` que afecta a:

- `titulo_activo`, `artista_activo`, `album_activo` → `"???"`
- `pista_activa`, `pista_visual` → snapshot con campos sensibles censurados (incluye portadas)
- `cola.obtener(i)` → mismo tratamiento para cualquier item cuya id coincida
- Slots de control humano (`pausar_reanudar`, `siguiente`, `anterior`, `buscar_posicion`, `reproducir_indice_cola`, `detener`, `reproducir(datos)` para pistas distintas) → no-op silencioso

El juego usa métodos internos sin `@Slot` para hacer bypass: `pausar_reanudar_forzado(bool)` y `detener_forzado()`. Esos no son accesibles desde QML.

Al avanzar de canción (`siguiente_reto`), el modelo del juego:

1. Llama `detener_forzado()` — vacía pista activa y limpia la cola.
2. Llama `limpiar_modo_ciego()` — libera la censura.
3. Resetea su propio `_fragmento_pista_id`.

Así la barra inferior queda en blanco y el panel de cola no muestra residual de la canción anterior cuando se libera el ciego.

Si el reto ya estaba acertado/revelado/pasado y el usuario pulsa "play" de nuevo, el modelo del juego **no** reactiva el modo ciego: la barra muestra los metadatos reales porque el usuario ya conoce la respuesta.

---

## 9. Acciones secundarias durante un reto

| Acción | Efecto |
| --- | --- |
| **Reproducir completa** | Reanuda la pista hasta el final sin revelar metadatos. Usa bypass para escapar al bloqueo de juego. |
| **Añadir a la cola** | Encola la pista en el reproductor global (queda censurada mientras el modo ciego siga activo) |
| **Añadir/quitar favorita** | Llama `svc_bib.toggle_favorita`; el flag se actualiza en el reto visible y persiste fuera del juego |
| **Ir a artista / Ir a álbum** | Solo visible cuando ya se reveló; navega a `biblioteca` vía `shell.navegar_a_vista` |
| **Revelar título** | Eleva nivel a `TOTAL` con estado `REVELADO` — no se cuenta como saltada |
| **¡Me rindo!** | Marca como `PASADO` y luego revela título — sí se cuenta como saltada |

---

## 10. Cierre de ronda

Cuando el usuario llega al último reto y pulsa "Terminar ronda" (o explícitamente "Terminar ronda" en cualquier momento), el modelo:

1. Cierra el servicio: `ExploradorCiegoService.cerrar_ronda()` → devuelve un `ResumenRonda(modo, total, acertados, revelados, pasados)`.
2. Emite `rondaTerminada(payload)` con el dict.
3. La vista cambia a la pantalla final con el resumen y dos CTAs: "Elegir otro modo" o "Otra ronda igual".

El resumen es desechable: no se persiste en disco. El historial de escucha del reproductor sí se actualiza para las pistas que sonaron (igual que cualquier otra reproducción).

---

## 11. Filosofía local-first

El juego respeta tres principios del producto:

- **Sin internet** — todo sale de la biblioteca, historial, portadas y metadatos ya catalogados por el CLI.
- **Sin telemetría** — no se envía nada hacia ningún servidor; el resumen se descarta al cerrar la ronda.
- **Reutilización** — usa el reproductor global, las consultas de biblioteca y el sistema de temas existentes; no introduce paralelismos.

Si la biblioteca está vacía o el modo elegido no tiene candidatos, la UI muestra estados vacíos coherentes con el resto de la app (`EmptyState`).

---

← [Volver al README](../README.md)
