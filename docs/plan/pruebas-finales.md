# Pruebas finales en el entorno real

> **Estado:** Vigente desde el 2026-10-30. Decisión de Nathan: las puertas de empaquetado y todo lo que solo se
> comprueba a mano se acumulan aquí y se ejecutan juntas al terminar la Fase 8 ([plan](./README.md), sección 5.1).
> Cada iteración que deja algo sin comprobar a mano lo apunta aquí en el mismo commit.

## Cómo se hará

1. Se compilan los instaladores (Linux en el contenedor de Ubuntu 22.04; Windows y macOS desde el CI).
2. Se prueba primero en máquina limpia (contenedor o máquina virtual): instala, arranca, no pide nada de fuera.
3. En la máquina de Nathan:
   * se desinstala NB Sound V1;
   * se parte de la copia de seguridad de la V1 que está en `~/Música/copia_seguridad/`
     (`nb_sound_20261029_112230.nbsound-backup`, 4,2 GB: la base hecha con `VACUUM INTO`, las portadas, las
     imágenes de artista y los manifiestos; **no** trae el audio, que sigue en `~/Música/biblioteca/`, ni los
     instrumentales, ni la identidad del servidor móvil, ni las claves);
   * se instala la V2, se importa y se recorre la lista de abajo.
4. Lo que falle se corrige con su prueba de regresión antes de publicar.

Durante esta prueba, y solo durante ella, la V2 escribe en el entorno real de Nathan con su permiso: el llavero, las
carpetas de datos de la V2 y lo que Nathan haga con la aplicación. Las rutas de la V1 siguen siendo de solo lectura.

## Fase 0

- [ ] El `.deb` y la AppImage arrancan en Ubuntu 22.04, Ubuntu 24.04 y Debian 12 limpios (ya comprobado el
      2026-10-30 con la Fase 0; se repite con la aplicación completa).
- [ ] Los instaladores de Windows y macOS instalan y arrancan en una máquina real.
- [ ] `fpcalc` instalado en `/usr/bin` por el `.deb` no choca con el paquete `chromaprint` (F7.2.1).

## Fase 1

- [ ] La V2 instalada encuentra la V1 (o su copia de seguridad, ver P12) y la importa en segundo plano sin retrasar
      la ventana.
- [ ] Las cifras del informe cuadran con las de `docs/engineering/migracion-v1.md` (pistas, álbumes, playlists con su
      orden, historial, teléfonos).
- [ ] La clave de servicio que tenía la V1 aparece en el llavero del sistema bajo "NB Sound" y en ningún archivo de
      la V2.
- [ ] El teléfono emparejado con la V1 se conecta a la V2 sin volver a emparejarse (la huella y los tokens se
      conservan; necesita la Fase 3).
- [ ] Una segunda apertura no vuelve a importar.

## Fase 2

- [ ] Suena por la salida por defecto en Linux (PipeWire y PulseAudio), Windows y macOS, y sigue sonando al
      cambiar de dispositivo (auriculares que se conectan) con la tasa nueva.
- [ ] Un álbum en MP3 y otro en FLAC se oyen sin hueco entre pistas.
- [ ] Mover la barra de posición cae donde se suelta; pausar y reanudar no hace clic.
- [ ] Las 18 preselecciones del ecualizador se oyen como en la V1 y ninguna distorsiona al volumen máximo.
- [ ] Con la normalización activa, pasar de una pista muy alta a una muy baja no obliga a tocar el volumen.
- [ ] Al abrir, la cola, la pista y el segundo en que se quedó la última sesión están ahí, sin sonar hasta pulsar
      reproducir.
- [ ] Cerrar la ventana mientras suena no deja audio sonando ni procesos vivos.
- [ ] La primera vez, con la V1 importándose en segundo plano, el reproductor recoge la cola de la V1 al terminar.
- [ ] Tras la importación, la medición de sonoridad recorre la biblioteca real sin que el equipo se note (CPU por debajo de un núcleo, sin cortes en lo que suena); con la normalización activa, una pista alta y una baja de la V1 suenan parecidas.
- [ ] La carcasa, la barra lateral y la barra de reproducción se comparan con las capturas de la V1 (`legado/assets/screens/`) y con la V1 abierta al lado.
- [ ] La biblioteca real (2.397 canciones, 1.421 álbumes) se desplaza sin tirones en WebKitGTK, con las portadas apareciendo al frenar; buscar, filtrar, ordenar y abrir álbum y artista funcionan como en la V1.
- [ ] Las playlists de la V1 aparecen con sus categorías, mosaicos y orden; crear, renombrar, ordenar, quitar, borrar y añadir desde cualquier canción funcionan, y el móvil recibe los cambios y «Me gusta» al marcar favoritas.
- [ ] La vista de reproducción toma el color de la portada; las letras sincronizadas siguen a la canción y llevan al segundo pulsado; el panel de la cola reordena con el ratón y con Alt+flechas; el minirreproductor flota encima y cerrar la ventana principal cierra todo.
- [ ] La V2 abre con el tema de la V1 (`sangre_dragon`) y Fira Sans sin parpadear con el de fábrica; los 63 temas se ven como en la V1.
- [ ] En Ajustes, cambiar de tema, tipografía y tamaño se ve al momento; el ecualizador suena con cada preselección y con las bandas movidas a mano; la normalización se nota desde la canción siguiente.
- [ ] Inicio muestra las cifras, Retomar, el álbum destacado y las secciones de la V1 con la biblioteca real, y saluda por el nombre.
- [ ] KDE Plasma y GNOME muestran título, artista, portada, duración y posición; sus botones y las teclas multimedia controlan la aplicación; aleatorio y repetición se reflejan en los dos sentidos. En Windows (SMTC) y macOS, lo mismo salvo aleatorio y repetición desde el sistema.
- [ ] Los atajos de la V1 funcionan en la ventana (espacio, flechas, S, R, L, F, K, +/-, Ctrl+Q, Ctrl+M) y no interfieren al escribir; la bandeja muestra el icono con su menú.
- [ ] Tu música muestra la foto y el nombre de la V1, las cifras del historial real, la hora pico en la hora local, el mood del día, los días activos del mes y los tops.

## Fase 3

- [ ] **Antes de desinstalar la V1, se conserva `~/.config/nb_sound/sync/`** (el certificado y la clave del servidor
      móvil). La copia de seguridad no la trae; sin ella la V2 crea una identidad nueva y los teléfonos tienen que
      emparejarse otra vez.
- [ ] Con `servidor_movil_al_arrancar` importado, la V2 enciende el servidor al abrir y el teléfono ya emparejado
      con la V1 se conecta sin escanear el QR (F3.1.1).
- [ ] El teléfono encuentra el equipo por mDNS tras reiniciar el equipo con otra IP.
- [ ] Con la base real migrada, el teléfono recibe el manifiesto sin volver a descargar la biblioteca (las versiones
      siguen donde las dejó la V1) y las playlists traen su mosaico (F3.1.4).
- [ ] Desde el teléfono: reproducir, pausar, saltar, buscar, volumen, aleatorio, repetición y karaoke; la cola
      espejada se mantiene al cambiar de destino en los dos sentidos (F3.2.1).
- [ ] Ajustes > Dispositivos: conectar un teléfono nuevo con el QR y con el código corto; quitar uno lo desconecta al
      momento (F3.3.1). El cortafuegos del sistema deja pasar el puerto 8731-8799 (en Windows, el aviso del
      sistema la primera vez).
- [ ] El selector de la barra dice qué teléfono controla el equipo mientras lo hace (F3.3.2).
- [ ] Una descarga completa de la biblioteca desde el teléfono no se nota en el equipo (audio sin cortes, ventana
      fluida).

## Fase 4

- [ ] Shazam reconoce de verdad pistas del corpus con la firma de la V2 (API no oficial: se comprueba contra el
      servicio real, con el consentimiento dado en Ajustes).
- [ ] AcoustID y MusicBrainz responden con la clave de AcoustID que el importador llevó de la V1 al llavero.
- [ ] Arrastrar una carpeta con canciones sobre cualquier parte de la ventana las importa, con la tarjeta de progreso
      y el resumen; "Añadir música" abre el selector del sistema.
- [ ] Cerrar la aplicación a mitad de una importación y volver a abrirla: sigue por donde iba sin duplicar nada.
- [ ] Por revisar: cada motivo con su texto, elegir un candidato, importar tal como está, buscar de nuevo y descartar a
      la papelera del sistema (comprobar que el archivo está en la papelera).
- [ ] Con la red desactivada en Ajustes, importar canciones con etiquetas: entran sin verificar.
- [ ] Copiar un álbum en la carpeta de música con la aplicación abierta lo importa solo, cuando termina de copiarse
      (F4.2.2); copiarlo con la aplicación cerrada lo importa al abrirla.
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
- [ ] Rasgos: comparar con la V1 los rasgos de F4.1.12 que el prototipo no midió (ancho de banda, caída espectral,
      ataques, pulsos y aproximaciones) sobre el corpus, con correlación ≥ 0,95, y escuchar la tonalidad de 30
      pistas.
- [ ] Paridad global de la Fase 4: 300 archivos sin etiquetar (copias del corpus fuera de la carpeta real) importados
      con la V1 y con la V2, con las decisiones coincidiendo en ≥ 98 % y cada diferencia explicada en el informe.

## Fase 5

- [ ] Con la Release de agregados publicada (P13): instalar cada agregado desde Ajustes, cortar la red a mitad y
      reanudar; el archivo instalado es el del catálogo (F5.1.2).
- [ ] Separar con el modelo real (`NS_MODELO_KARAOKE`, `NS_AUDIO_KARAOKE` y `NS_ONNXRUNTIME` en
      `karaoke::tests::con_el_modelo_real_separa_una_pista`) y en la aplicación: con todos los núcleos ocupados, ningún
      vacío de buffer en la reproducción, y el pico de memoria del proceso por debajo de 3 GB (F5.2.1, P8).
- [ ] Con el agregado de karaoke: pulsar el micrófono en una canción sin instrumental, ver el avance en el botón,
      seguir escuchando el original y, al terminar, cantar sin que la canción se corte (F5.2.2); sin el agregado,
      el micrófono lo ofrece con su tamaño (F5.1.4).
- [ ] Tras importar la V1, las 115 pistas con instrumental aparecen en "Listas para cantar" sin volver a separarse, y
      las que esperaban en cola están pendientes (F5.2.4).
- [ ] Con el agregado de análisis instalado: las 407 pistas que analizó la V1 dan las mismas salidas que F0.4.3 (peor
      diferencia por debajo de 0,01, con valencia y activación en la escala de DEAM llevada a 0–1), y analizar en
      segundo plano no produce vacíos de buffer (F5.3.1, F5.3.2).

## Fase 6

- [ ] Con el agregado de texto instalado, el tokenizador propio da los mismos ids que el `tokenizer.json` de MiniLM con
      `tokenizers` de HuggingFace en 50 frases del DJ, y los embeddings coinciden con los de la V1 (F6.1.1).
- [ ] Sobre la base migrada de la instalación real, diez pedidos con semilla construyen en la V2 la misma sesión que la
      V1 (mismas pistas en el mismo orden). Las pistas con etiquetas `genre_discogs400` en la V1 pueden diferir: la
      importación conserva solo las de MusiCNN (F6.1.2).
