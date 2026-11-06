# Pruebas finales en el entorno real

> **Estado:** Vigente desde el 2026-10-30. Decisión de Nathan: las puertas de empaquetado y todo lo que solo se
> comprueba a mano se acumulan aquí y se ejecutan juntas al terminar la Fase 8 ([plan](./README.md), sección 5.1).
> Cada iteración que deja algo sin comprobar a mano lo apunta aquí en el mismo commit.

## Cómo se hará

1. Se compilan los instaladores (Linux en el contenedor de Ubuntu 22.04; Windows y macOS desde el CI).
2. Se prueba primero en máquina limpia (contenedor o máquina virtual): instala, arranca, no pide nada de fuera.
3. En la máquina de Nathan, se instala NB Sound y se recorre la lista de abajo.
4. Lo que falle se corrige con su prueba de regresión antes de publicar.

Durante esta prueba, y solo durante ella, NB Sound escribe en el entorno real de Nathan con su permiso: el llavero, las
carpetas de datos de NB Sound y lo que Nathan haga con la aplicación. Las rutas siguen siendo de solo lectura.

## Fase 0

- [ ] El `.deb` y la AppImage arrancan en Ubuntu 22.04, Ubuntu 24.04 y Debian 12 limpios (ya comprobado el
      2026-10-30 con la Fase 0; se repite con la aplicación completa).
- [ ] Los instaladores de Windows y macOS instalan y arrancan en una máquina real.
- [ ] `fpcalc` instalado en `/usr/bin` por el `.deb` no choca con el paquete `chromaprint` (F7.2.1).

## Fase 2

- [ ] Suena por la salida por defecto en Linux (PipeWire y PulseAudio), Windows y macOS, y sigue sonando al
      cambiar de dispositivo (auriculares que se conectan) con la tasa nueva.
- [ ] Un álbum en MP3 y otro en FLAC se oyen sin hueco entre pistas.
- [ ] Mover la barra de posición cae donde se suelta; pausar y reanudar no hace clic.
- [ ] Las 18 preselecciones del ecualizador se oyen y ninguna distorsiona al volumen máximo.
- [ ] Con la normalización activa, pasar de una pista muy alta a una muy baja no obliga a tocar el volumen.
- [x] Al abrir, la cola, la pista y el segundo en que se quedó la última sesión están ahí, sin sonar hasta pulsar
      reproducir. *(Comprobado por guion el 2026-11-05 sobre la 2.0.9 instalada y la copia de los datos.)*
- [x] Cerrar la ventana mientras suena no deja audio sonando ni procesos vivos. *(Comprobado por guion el 2026-11-05 sobre la 2.0.9 instalada y la copia de los datos.)*
- [ ] Tras la importación, la medición de sonoridad recorre la biblioteca real sin que el equipo se note (CPU por debajo de un núcleo, sin cortes en lo que suena); con la normalización activa, una pista alta y una baja suenan parecidas.
- [ ] La biblioteca real (2.397 canciones, 1.421 álbumes) se desplaza sin tirones en WebKitGTK, con las portadas apareciendo al frenar; buscar, filtrar, ordenar y abrir álbum y artista funcionan.
- [ ] Las playlists aparecen con sus categorías, mosaicos y orden; crear, renombrar, ordenar, quitar, borrar y añadir desde cualquier canción funcionan, y el móvil recibe los cambios y «Me gusta» al marcar favoritas.
- [ ] La vista de reproducción toma el color de la portada; las letras sincronizadas siguen a la canción y llevan al segundo pulsado; el panel de la cola reordena con el ratón y con Alt+flechas; el minirreproductor flota encima y cerrar la ventana principal cierra todo.
- [ ] NB Sound abre con el tema (`sangre_dragon`) y Fira Sans sin parpadear con el de fábrica; los 63 temas se ven.
- [ ] En Ajustes, cambiar de tema, tipografía y tamaño se ve al momento; el ecualizador suena con cada preselección y con las bandas movidas a mano; la normalización se nota desde la canción siguiente.
- [ ] Inicio muestra Retomar (sin las cifras, por decisión de QA-R2), el álbum destacado y las secciones con la biblioteca real, y saluda por el nombre.
- [ ] KDE Plasma y GNOME muestran título, artista, portada, duración y posición; sus botones y las teclas multimedia controlan la aplicación; aleatorio y repetición se reflejan en los dos sentidos. En Windows (SMTC) y macOS, lo mismo salvo aleatorio y repetición desde el sistema.
- [ ] Los atajos funcionan en la ventana (espacio, flechas, S, R, L, F, K, +/-, Ctrl+Q, Ctrl+M) y no interfieren al escribir; la bandeja muestra el icono con su menú.
- [ ] Tu música muestra la foto y el nombre, las cifras del historial real, la hora pico en la hora local, el mood del día, los días activos del mes y los tops.

## Fase 3

- [ ] El teléfono encuentra el equipo por mDNS tras reiniciar el equipo con otra IP.
- [ ] Con la biblioteca real, el teléfono recibe el manifiesto sin volver a descargar la biblioteca y las playlists traen su mosaico (F3.1.4).
- [ ] Desde el teléfono: reproducir, pausar, saltar, buscar, volumen, aleatorio, repetición y karaoke; la cola
      espejada se mantiene al cambiar de destino en los dos sentidos (F3.2.1).
- [ ] Ajustes > Dispositivos: conectar un teléfono nuevo con el QR y con el código corto; quitar uno lo desconecta al
      momento (F3.3.1). El cortafuegos del sistema deja pasar el puerto 8731-8799 (en Windows, el aviso del
      sistema la primera vez).
- [ ] "Dónde suena", en el menú ··· de la barra, dice qué teléfono controla el equipo mientras lo hace (F3.3.2).
- [ ] Una descarga completa de la biblioteca desde el teléfono no se nota en el equipo (audio sin cortes, ventana
      fluida).

## Fase 4

- [ ] Shazam reconoce de verdad pistas del corpus con la firma de NB Sound (API no oficial: se comprueba contra el
      servicio real, con el consentimiento dado en Ajustes).
- [ ] AcoustID y MusicBrainz responden con la clave de AcoustID que el importador llevó al llavero.
- [ ] Arrastrar una carpeta con canciones sobre cualquier parte de la ventana las importa, con la tarjeta de progreso
      y el resumen; "Añadir música" abre el selector del sistema.
- [ ] Cerrar la aplicación a mitad de una importación y volver a abrirla: sigue por donde iba sin duplicar nada.
- [ ] Por revisar: cada motivo con su texto, elegir un candidato, importar tal como está, buscar de nuevo y descartar a
      la papelera del sistema (comprobar que el archivo está en la papelera).
- [ ] Con la red desactivada en Ajustes, importar canciones con etiquetas: entran sin verificar.
- [x] Copiar un álbum en la carpeta de música con la aplicación abierta lo importa solo, cuando termina de copiarse
      (F4.2.2); copiarlo con la aplicación cerrada lo importa al abrirla. *(Comprobado por guion el 2026-11-05 en la 2.0.7 instalada con un archivo sintético; a mano, con un álbum real.)*
- [ ] Ajustes > Privacidad: apagar un servicio corta su siguiente petición sin reiniciar; con la conexión general
      apagada no sale nada (F4.2.7).
- [ ] Ajustes > Inteligencia artificial con una clave real de Anthropic: se guarda en el llavero del sistema (visible
      en su gestor de contraseñas como "NB Sound") y un empate entre candidatos se resuelve; con OpenAI, igual
      (F4.1.7).
- [ ] "Completar datos" sobre una pista sin verificar le pone portada y letra y, si la identifica, la verifica; el
      teléfono la sigue reconociendo y la vuelve a descargar con los datos nuevos (F4.2.8, arnés de respuestas
      doradas en verde).
- [ ] Editar los datos de una canción y de un álbum: el teléfono recibe el cambio y el archivo lleva las etiquetas
      nuevas; renombrar un álbum conserva su portada; borrar la pista e importar el mismo archivo otra vez respeta
      lo editado (F4.2.5).
- [ ] Crear una copia de seguridad, cambiar la biblioteca, restaurarla y reiniciar: vuelve a estar como en la copia;
      la copia automática semanal aparece en su carpeta (F4.2.6).

## Fase 5

- [ ] Con la Release de agregados publicada (P13): instalar cada agregado desde Ajustes, cortar la red a mitad y
      reanudar; el archivo instalado es el del catálogo (F5.1.2).
- [ ] Separar con el modelo real (`NS_MODELO_KARAOKE`, `NS_AUDIO_KARAOKE` y `NS_ONNXRUNTIME` en
      `karaoke::tests::con_el_modelo_real_separa_una_pista`) y en la aplicación: con todos los núcleos ocupados, ningún
      vacío de buffer en la reproducción, y el pico de memoria del proceso por debajo de 3 GB (F5.2.1, P8).
- [ ] Con el agregado de karaoke: pulsar el micrófono en una canción sin instrumental, ver el avance en el botón,
      seguir escuchando el original y, al terminar, cantar sin que la canción se corte (F5.2.2); sin el agregado,
      el micrófono lo ofrece con su tamaño (F5.1.4).

## Fase 6

- [ ] Con el agregado de texto instalado, el tokenizador propio da los mismos ids que el `tokenizer.json` de MiniLM con
      `tokenizers` de HuggingFace en 50 frases del DJ, y los embeddings coinciden con los (F6.1.1).
- [ ] A oído, en la instalación real, una sesión de una hora con las cinco técnicas: ninguna transición hace clic,
      se hunde ni sube de golpe, y en las capas la voz de la entrante vuelve al final del solapamiento (F6.1.3).
- [ ] Con los dos platos, la reproducción normal sigue por debajo del 2 % de un núcleo (criterio de ADR-003), y una
      mezcla en curso, por debajo del 4 % (F6.1.3).
- [ ] Con el agregado de karaoke instalado, la medida del equipo de desarrollo termina en menos de dos minutos y da
      un perfil coherente con lo que tarda en preparar una pista para cantar (F6.1.4).
- [ ] En la instalación real: pedir una sesión empieza a sonar en menos de 3 s, la vista muestra cómo se entendió el
      pedido, la sesión crece mientras suena hasta la duración pedida, la barra la controla (pausa, saltar, anterior,
      buscar), "Otra parecida" y "Descartar" devuelven la cola tal como estaba, y al cerrar y abrir vuelve en pausa
      (F6.1.6).
- [ ] En la instalación real, una ronda de cada modo de A ciegas: el fragmento suena desde el 30 % durante los
      segundos elegidos, la barra y el móvil no dicen la canción, escribir el título con un error de una letra acierta
      y al terminar la cola vuelve donde estaba (F6.2.2).

## Fase 8

- [ ] En la instalación real, diez pistas del corpus: la forma de onda en la barra se corresponde a la vista con lo que
      suena, en una sesión del DJ marca el punto de entrada y el de salida de la pista actual, y volver a medir la
      biblioteca entera en segundo plano para poblar los picos no se nota en el equipo (F8.1).
- [ ] En la instalación real: crear una lista inteligente por BPM, ánimo y favoritas, comprobar que el teléfono la
      recibe y que al marcar otra canción como favorita entra sola; pulsar "Crear para mí" sobre la biblioteca real
       y comprobar las listas automáticas generadas (F8.2).
- [ ] En la instalación real, en Tu música: recorrer el resumen local de escucha por año y por mes sobre el historial
      real, comprobar el radar de ánimos y el mapa de calor 7×24 y exportar una tarjeta SVG (F8.3).
- [ ] En la instalación real, en Ajustes > Dispositivos: copiar una playlist y las favoritas a una memoria USB o
      microSD con portada incrustada y comprobar la estructura de carpetas, la portada en los archivos, el archivo
      `.m3u8` y la conversión opcional a WAV (F8.4).
- [ ] En la instalación real, en Ajustes > Dispositivos: encender el Modo fiesta, escanear el código QR desde un
      teléfono en la misma red Wi-Fi, buscar canciones desde el navegador del teléfono, enviar sugerencias, aprobarlas,
      descartarlas, probar el modo automático y rotar el QR comprobando que el enlace anterior deja de funcionar (F8.5).

## Revisión QA-R1

- [ ] En la instalación de Arch con el `.tar.gz`: con una publicación nueva hecha por la CI (que ya firma el `.tar.gz`),
      "Instalar y reiniciar" pide la contraseña con `pkexec`, instala sobre `/usr` y arranca la versión nueva. La
      publicación 2.0.6 y anteriores no tienen `.tar.gz.sig`: desde ellas el aviso será que no se pudo instalar.
- [ ] Quitar una canción "y mover el archivo a la papelera": el archivo aparece en la papelera de KDE y se puede
      restaurar; la canción sale de sus playlists, de la cola y del teléfono en la siguiente sincronización.
- [ ] "Mostrar en su carpeta" abre Dolphin con el archivo seleccionado, también con comas y tildes en la ruta.
- [ ] Cancelar una importación grande a la mitad: lo importado se queda, el resto no vuelve al reabrir.
- [ ] "Buscar duplicados" sobre la biblioteca real no aparta nada que no sea una copia real.
- [ ] Cambiar la foto de perfil por un PNG y por un JPG grandes: se ve al momento en Tu música.

## Revisión QA-R2 (interfaz)

Lo que la pasada con la aplicación en marcha no pudo comprobar: el puntero del entorno de pruebas no se mueve, y los
estados de pasar por encima solo se vieron en el código.

- [ ] En una lista de canciones, al pasar por encima el número se cambia por reproducir, aparecen la favorita, "+" y
      ···; con el teclado, Tab llega a los mismos botones y el número también se cambia.
- [ ] El menú ··· de una fila, de un álbum y de una playlist se abre junto al botón, se recorre con las flechas y se
      cierra con Escape; cerca del borde inferior se abre hacia arriba.
- [ ] La cabecera de un álbum, de un artista y de una playlist toma el color de su portada, y con "Color por portada"
      apagado se queda con el del tema.
- [ ] En la consola de karaoke, "Cantar ahora" activa el karaoke de lo que suena y el botón pasa a "Volver a la
      original"; "Verlas en la biblioteca" abre Pistas con "Listas para cantar" aplicado, también estando ya en
      Biblioteca.
- [ ] Ajustes > Biblioteca > "Cambiar" la carpeta de tu música: con una copia ya hecha en otro disco, dice que están
      todas y solo apunta; con una carpeta vacía en otro disco, "Llevar mi música" muestra el avance, la música
      suena desde la nueva y la vieja queda sin las canciones (y sin carpetas vacías). Lo nuevo que se copie en la
      carpeta nueva se importa solo.
- [ ] En Tu música, tocar el nombre lo deja editar; Enter guarda, Escape cancela, y Ajustes e Inicio lo ven.
- [ ] Las playlists ancladas llevan su distintivo en la esquina de la portada, en las cuatro densidades de Playlists.
- [ ] En pantalla completa con la letra o la portada, al dejar quieto el ratón 3,5 s los controles se esconden
      aunque la letra siga avanzando, y no queda ninguna franja vacía abajo; al moverlo vuelven.
- [ ] El minirreproductor se arrastra desde la portada o el fondo; cerrarlo y volverlo a abrir (Ctrl+M) es
      instantáneo; el botón de volver trae delante la ventana grande.
- [ ] En la cola, con muchas canciones, la barra de desplazamiento no tapa la duración ni el botón de quitar.
- [ ] La consola de karaoke con varias canciones pedidas: la primera lleva su barra y su porcentaje, las demás "En
      espera"; al cerrar NB Sound a la mitad y abrirla, sigue con la misma.
- [ ] Con un cajón (Karaoke, Dispositivos, Añadir música), la cola o el menú ··· abiertos, la barra de
      desplazamiento de la vista de debajo no se ve encima.
- [x] Karaoke, Dispositivos y Añadir música entran deslizándose desde la derecha, sin aparecer antes en mitad de la
      ventana (solo se veía con la GPU). *(Comprobado el 2026-11-06 en la 2.0.10 instalada, en el escritorio de Nathan
      con la GPU, la animación ralentizada a 3 s y capturas a mitad.)*
- [x] Reproducir la biblioteca entera y abrir la cola: abre al momento, se desplaza fluida y Vaciar responde. *(Comprobado por guion el 2026-11-05 sobre la 2.0.9 instalada y la copia de los datos.)*
- [ ] "Cooler Than Me" (48 kHz) se prepara para karaoke y aparece su micrófono en la barra.
- [ ] Desplazarse rápido por Biblioteca (pistas, álbumes, artistas) y por Playlists va fluido, y al volver a una
      vista ya visitada se ve al momento lo de antes.
- [ ] Al pasar por encima: las tarjetas de Inicio, los carruseles con sus flechas, el botón grande de reproducir (crece
      un poco) y las filas de la sesión del DJ.
- [ ] Una instalación nueva abre en la bienvenida; "Elegir la carpeta" importa lo que hay en ella y lo sigue vigilando.


## Revisión QA-R3

Lo que la pasada de la 2.0.12 no pudo comprobar en el entorno de pruebas: el selector nativo de carpetas no se
maneja desde el inspector y el puntero no se mueve.

- [ ] Por revisar con el ratón: el ··· de cada fila se abre junto al botón; "Otras 3 versiones" despliega y repliega;
      las filas se apagan mientras se importan y vuelven si algo falla.
- [ ] "¿Dónde está tu música?" → "Buscar mi música" → elegir la carpeta buena: dice que están todas y, al usarla, la
      biblioteca suena sin reiniciar. Con una carpeta vacía dice que no hay ninguna y ofrece elegir otra.
- [ ] La barra de reproducción a 720 px con el ratón: la fila de controles del menú ··· responde y el menú se cierra
      al elegir letras o pantalla completa.
