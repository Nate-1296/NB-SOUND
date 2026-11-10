# Revisión de producto (2026-11-05)

> **Qué es este documento:** una revisión de NB Sound punto por punto, en la 2.0.9 instalada, comparada con los
> reproductores con los que se va a medir: Spotify y Apple Music (la experiencia que la gente tiene en la cabeza),
> Plexamp (lo mejor de "tu música" con mezcla y radio), MusicBee y foobar2000 (los de biblioteca local en
> escritorio) y Symfonium (el de móvil con servidor propio). Dice lo que ya está a la altura, lo que falta y en qué
> orden lo haría. **Lo que propone no entra en el plan sin la decisión de Nathan** (CLAUDE.md, sección 10): cada
> propuesta aceptada pasa a una iteración con su criterio.

## Dónde está

* **Versión:** 2.0.9, publicada y con la CI en verde en Linux, Windows y macOS. Los 16 artefactos se empaquetan; el
  `.tar.gz` está firmado y es el que está instalado en el equipo de Nathan.
* **Verificación:** `pnpm verify`, `clippy` sin avisos y 620 pruebas de Rust; además, una batería sobre la aplicación
  instalada (no la de desarrollo) con la copia de los datos: las diez vistas, la reproducción, la cola de 2.243
  canciones, importar, Por revisar, borrar, el karaoke y volver a abrir donde se cerró.
* **Lo que se aprendió probando la instalada:** dos defectos que en desarrollo no se veían (el entorno de ONNX y la
  ruta inicial) y uno de rendimiento (el karaoke a prioridad normal). Por eso la regla de la
  [puerta de empaquetado](../plan/README.md) tiene razón: **lo que se publica se prueba instalado**.

## Lo que ya está a la altura, o por encima

| Área                         | Por qué                                                                                                                                                                                         |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Biblioteca propia             | Importa, identifica (Shazam, AcoustID, MusicBrainz), etiqueta, organiza y aparta duplicados sola. Ni Spotify ni Apple Music lo hacen con tus archivos; MusicBee y foobar2000 lo dejan al usuario |
| DJ Privado                    | Una sesión mezclada de verdad, con transiciones, a partir de una frase. Spotify tiene un DJ que habla y elige; no mezcla. Plexamp mezcla por "sweet fades", no construye la sesión             |
| Karaoke de cualquier canción | Separación de voz en el propio equipo y sin red. Apple Music Sing lo hace solo con su catálogo y en la nube                                                                                    |
| A ciegas                      | No tiene equivalente en ningún reproductor                                                                                                                                                      |
| Tu música                    | Identidad, tops, radar de ánimos, calendario y resumen exportable, todo local. Spotify lo da una vez al año (Wrapped)                                                                          |
| Privacidad                    | Sin cuenta, sin anuncios, cada servicio en línea con su interruptor y explicando qué recibe                                                                                                    |
| Teléfono                     | Sincroniza biblioteca, playlists, letras e instrumentales sin internet y sirve de mando; Modo fiesta para invitados desde el navegador                                                           |
| Sonido                        | Sin huecos entre canciones, sonoridad EBU R128, ecualizador de diez bandas con preselecciones                                                                                                    |
| Robustez                      | Nunca hay que reiniciar, se acuerda de todo y se repara sola tras un fallo (2.0.7–2.0.9)                                                                                                        |

## Lo que le falta

Ordenado por lo que aporta a quien la usa a diario. Cada fila dice qué app lo tiene y qué haría falta.

### Prioridad alta

| #  | Qué                                                                                                                                                                                                                                                                               | Quién lo tiene                                                        | Qué implica                                                                                                                                                                                                                                                                           |
| -- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A1 | **Seguir sonando al acabar la cola** (radio de una canción, de un artista o de lo que sonaba)                                                                                                                                                                               | Spotify (Autoplay), Apple Music, Plexamp (radio de artista, de álbum) | Las piezas existen: el análisis, los rasgos y el planificador del DJ ya saben qué se parece a qué. Es una regla en la cola y un ajuste para apagarlo                                                                                                                                |
| A2 | **Fundido entre canciones** en la reproducción normal (0–12 s), además de sin huecos                                                                                                                                                                                      | Spotify, Apple Music, Plexamp, MusicBee                                | El motor del DJ ya hace fundidos con dos platos; falta usarlo fuera del DJ, respetando los álbumes continuos (como Plexamp: sin fundido dentro de un mismo álbum)                                                                                                                    |
| A3 | **Elegir la salida de audio** (auriculares, altavoces, la tarjeta USB) sin ir al sistema                                                                                                                                                                                     | Spotify, MusicBee, foobar2000, Plexamp                                 | `cpal` enumera los dispositivos; un selector en el menú ··· (Dónde suena) y recordar la elección                                                                                                                                                                               |
| A4 | **Selección múltiple** en las listas (Mayús y Ctrl): añadir a una playlist, a la cola, favoritas o quitar varias a la vez                                                                                                                                                | Todos                                                                  | Hoy todo se hace canción por canción. Es la carencia que más se nota al ordenar una biblioteca grande                                                                                                                                                                               |
| A5 | **Temporizador de apagado** (al acabar esta canción, en 15, 30, 60 min)                                                                                                                                                                                                     | Spotify (móvil), Apple Music, Plexamp                                 | Pequeño: una orden al reproductor y una entrada en el menú ···                                                                                                                                                                                                                    |
| A6 | **Firma de código** en Windows y macOS                                                                                                                                                                                                                                      | Cualquier aplicación distribuida                                      | Descartada el 2026-11-09: Nathan no pagará los certificados (P15) |
| A7 | **Las pruebas finales**, solo las que hace una IA (sin máquina limpia desde el 2026-11-08)                                                                                                                                                                                  | —                                                                     | Hecha el 2026-11-09: todas por guion; quedan explicadas en [pruebas finales](../plan/pruebas-finales.md) |
| A8 | **La memoria del karaoke** (P8: llegó a 9 GB)                                                                                                                                                                                                                               | —                                                                     | Hecha el 2026-11-09: 1,4 GB de pico sin optimizar el grafo de ONNX Runtime (P8)                                                                                                                                                                                                        |
| A9 | **Completar en segundo plano lo que le falta a la biblioteca** (letras, portadas, fotos de artista, etiquetas), como el karaoke: una importación puede fallar a medias sin que falte el dato en el servicio, y una biblioteca que llega de otra instalación entra sin nada | Plexamp, MusicBee (con complementos)                                   | Hecha el 2026-11-09 (`catalogo/completar_fondo.rs`, V11): cinco minutos después de abrir, con prioridad baja y la conexión general encendida, cada pista sin portada, sin letra o con su artista sin imagen pasa por "Completar datos"; lo que no se encuentra se reintenta al mes |

### Prioridad media

| #  | Qué                                                                           | Quién lo tiene                          | Qué implica                                                                                                                                               |
| -- | ------------------------------------------------------------------------------ | ---------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| M1 | **Explorar por géneros y décadas** (una pestaña o tarjetas en Inicio) | Apple Music, MusicBee, Plexamp           | El género ya está en los datos; las inteligentes lo usan, pero no hay dónde verlo                                                                       |
| M2 | **Registrar escuchas en ListenBrainz o Last.fm** (opcional)              | MusicBee, foobar2000, Plexamp, Symfonium | Una salida de red más, con su interruptor y consentimiento (regla 5) y su clave en el llavero                                                             |
| M3 | **Importar y exportar playlists en M3U**                                 | MusicBee, foobar2000                     | Hoy solo la copia a USB escribe M3U. Importar es lo que pide quien viene de otro reproductor                                                               |
| M4 | **Inglés**                                                              | Todos                                    | Toda la interfaz sale de un diccionario (`check-i18n`), así que es traducir `es.ts` y elegir por el idioma del sistema. Necesario para publicar fuera |
| M5 | **Bajar la prioridad del trabajo de fondo en Windows**                   | —                                       | Hecha el 2026-11-09 con `windows-sys` (P16) |
| M6 | **Accesibilidad** revisada con lector de pantalla y solo teclado         | Apple Music, Spotify                     | Las bases están (roles, foco visible, temas de alto contraste); falta una pasada con Orca y NVDA                                                          |
| M7 | **Instrumentales más pequeños** (P14: 40 MB por canción en WAV)       | —                                       | FLAC los deja en la mitad o menos; depende de P7 en el teléfono                                                                                           |

### Prioridad baja

| #  | Qué                                                                                   | Quién lo tiene                     |
| -- | -------------------------------------------------------------------------------------- | ----------------------------------- |
| B1 | Mostrar lo que suena en Discord                                                        | MusicBee, Plexamp (con complemento) |
| B2 | Velocidad de reproducción (para audiolibros y clases)                                 | Apple Music, foobar2000             |
| B3 | Editar o sincronizar a mano una letra                                                  | MusicBee                            |
| B4 | Un visualizador en la reproducción ampliada                                           | MusicBee, foobar2000                |
| B5 | Atajos globales configurables (además de las teclas multimedia, que ya van por MPRIS) | foobar2000, MusicBee                |

### Lo que no conviene

* **Catálogo en streaming, perfiles sociales o sincronizar con la nube.** Contradicen lo que hace distinta a NB Sound
  (tu música, en tu equipo, sin cuenta) y la regla 5.
* **Un modo "avanzado"** con columnas técnicas, colas internas o diagnósticos: lo prohíbe la regla 2. Lo que
  foobar2000 enseña en pantalla, aquí va al registro.

## Lo que queda por decidir o por cerrar

* **Pruebas finales:** hechas el 2026-11-09, todas por guion sobre una copia de los datos
  ([pruebas finales](../plan/pruebas-finales.md)).
* **Preguntas abiertas:** P3 (la licencia, pendiente de aclarar con Nathan), P7 (FLAC y M4A en el teléfono) y P14,
  que depende de P7.
* **Un defecto sin reproducir:** en la primera apertura de la 2.0.7 instalada, cerrar y abrir volvió a una sesión
  anterior. No se repitió en ningún ciclo posterior, tampoco en las pruebas finales.

## Lo que haría a continuación

1. **A1, A2, A3 y A5** juntas: son la experiencia de escuchar, se apoyan en piezas que ya existen y es donde Spotify
   y Plexamp hoy se notan por delante.
2. **A4**, la selección múltiple, antes de que la biblioteca crezca más.
3. Después, **M1–M4** en ese orden.
