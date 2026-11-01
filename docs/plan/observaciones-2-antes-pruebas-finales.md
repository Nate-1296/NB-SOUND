# Informe de Auditoría y Control de Calidad (QA Senior) - Segunda Ronda
<!-- check-docs: allow-absolute-path -->

**Producto:** NB Sound (Desktop App - WebKitGTK / Tauri 2 / Svelte 5)  
**Versión evaluada:** 2.0.2 (Entorno real de ejecución en Linux Wayland / KDE Plasma 6 / CachyOS)  
**Documento:** `docs/plan/observaciones-2-antes-pruebas-finales.md`  
**Referencia previa:** `docs/plan/observaciones-antes-pruebas-finales.md`  
**Rol:** QA Tester Senior & Analista de Pruebas Senior  
**Fecha:** Noviembre 2026 (Pruebas Dinámicas en Vivo: Navegación, Ergonomía, Responsividad e Interacción)  

---

## 1. Resumen Ejecutivo y Diagnóstico General

Como QA Tester Senior y Analista de Pruebas Senior, he procedido a levantar e interactuar exhaustivamente sobre la instancia viva de **NB Sound** instalada directamente en el portátil bajo el entorno de producción (`/usr/bin/nb-sound` en Wayland, resolución física 1920x1080 con escalado fraccional 1.25x en KDE Plasma 6.8). 

Se contrastó el comportamiento en tiempo real contra los contratos arquitectónicos del repositorio (`CLAUDE.md`, ADR-007, ADR-008, `contrato-reproductor.md`, `pruebas-finales.md`) y contra los estándares consolidados de usabilidad multimedia (Spotify Desktop, Apple Music, Tidal y el referente interno `NB_Books`).

### Diagnóstico de la Sesión de Pruebas en Vivo

Si bien las correcciones previas de la primera ronda mitigaron los bloqueos de scroll y la paridad técnica de temas, la prueba dinámica en vivo revela **nuevas fricciones severas de usabilidad, incongruencias lógicas del estado inicial, roturas en modo responsivo y una evidente falta de dinamismo estético**:

1. **El arranque es ciego y anti-intuitivo:** Al abrir la aplicación, el motor restaura internamente la cola previa (39 pistas) y su posición; sin embargo, la barra de reproducción permanente declara *"Nada sonando. Elige una canción para empezar"*, con duración `0:00 / 0:00` y sin datos de la pista. Al pulsar reproducir, la canción arranca inmediatamente desde el segundo exacto persistido, desconcertando por completo al usuario.
2. **Saludos desfasados respecto a la hora real:** A las 00:30 de la noche / madrugada, la cabecera de Inicio da la bienvenida con *"Buenos días, Nate. Elige el primer tono del día"* o *"Nate, abre la mañana con algo tuyo"*, debido a una condición temporal binaria defectuosa en el cálculo de horas.
3. **Controles y barras estáticas insensatas:** La presencia de 24 barras verticales fijas en la cabecera de Inicio (`EcualizadorBarras.svelte`), que no reaccionan al audio en reposo y flotan solitarias al maximizar o caen en bloque al encoger la ventana, genera una sensación inmediata de diseño inacabado o depuración residual.
4. **Selectores que parecen páginas web y no una aplicación de escritorio:** Los controles de ordenación en Biblioteca, selección de copia en Ajustes y preselección del ecualizador son etiquetas HTML `<select>` nativas sin estilar como popover de escritorio, rompiendo la inmersión del producto.
5. **Imposibilidad de cambiar la foto de perfil y ambigüedad de identidad:** No existe interfaz para actualizar la foto de perfil del usuario (migrada de la V1), mientras que el logotipo circular con la silueta en la barra lateral se percibe visualmente como el avatar propio, provocando frustración.
6. **Desiertos de espacio y falta de dinamismo transversal:** Pantallas como el detalle de un álbum o el juego "A ciegas" dejan entre un 70% y un 80% del área de trabajo como un abismo negro sin textura, sin gradientes, sin carruseles complementarios ni información contextual.
7. **Rupturas al redimensionar la ventana:** En resoluciones compactas (~850px o modo mosaico/tiling), la navegación de Ajustes trunca y oculta secciones vitales (`Privacidad`, `IA`, `Acerca de`) fuera del borde derecho de la pantalla sin scroll ni indicador, mientras que el control deslizante de volumen de la barra inferior se volatiliza.
8. **Omisiones en navegación de catálogo:** La vista de artista carece por completo de la sección de álbumes / discografía, mostrando únicamente una lista plana de canciones desordenadas.

---

## 2. Hallazgos Críticos y Bugs de Lógica de Interfaz

---

### [ALERTA] BUG-01 (QA-01): Arranque ciego con cola persistida pero reproductor vacío ("Nada sonando")
- **Ubicación:** `src-tauri/src/cola.rs` (función `restaurar`), `src-tauri/src/reproductor/mod.rs` (`instantanea`), `src/lib/ui/BarraReproduccion.svelte` y `src/lib/core/reproductor.svelte.ts`.
- **Qué se ve / qué pasa:**  
  Al iniciar la aplicación, el backend lee exitosamente la última sesión de SQLite: se restauran 39 pistas en la cola y el contador de la barra inferior indica correctamente el badge `39`. La tarjeta de Inicio incluso muestra *"RETOMAR REPRODUCCIÓN: Diosa"*.  
  Sin embargo, **la barra inferior permanente de reproducción aparece en blanco absoluto**: portada vacía, título *"Nada sonando"*, subtítulo *"Elige una canción para empezar"*, duración `0:00 / 0:00` y barra de progreso en cero.  
  Cuando el usuario pulsa el botón naranja de Play o presiona la barra espaciadora, la aplicación **comienza a reproducir de inmediato la canción persistida desde el segundo exacto donde se quedó**, poblando bruscamente todos los textos, carátulas y tiempos.
- **Qué piensa / siente el usuario:**  
  *"¿Por qué dice 'Nada sonando' si la cola tiene 39 canciones? Pensé que tenía que elegir otra canción desde cero. Le di a play por curiosidad y de la nada empezó a sonar una canción a mitad de camino. Es horrible: si la app sabe qué canción seguía y en qué segundo estaba, ¿por qué no me la muestra cargada desde el segundo uno?"* Genera desconfianza y sensación de software mal sincronizado.
- **El porqué (Análisis Forense de Código):**  
  En `src-tauri/src/cola.rs`, la función `restaurar(filas, posicion, segundos)` inicializa `self.filas`, `self.posicion` y `self.reanudar_en_seg`, pero **deja `self.activa` en `None`**.  
  En consecuencia, cuando `reproductor/mod.rs::instantanea()` se ejecuta al arrancar:
  ```rust
  pista_id: self.cola.activa().map(|f| f.pista_id), // Devuelve None
  duracion_seg: actual.map_or(0.0, |s| s.duracion_seg), // Devuelve 0.0
  ```
  La instantánea publicada a la UI contiene `pistaId: null` y `duracionSeg: 0`. En Svelte, `const hayPista = $derived(i.pistaId !== null)` evalúa a `false`, disparando la rama `{:else}` que renderiza *"Nada sonando"*.
- **Solución recomendada:**  
  1. En `cola.rs::restaurar()`, si `self.filas` no está vacía y `self.posicion < self.filas.len()`, asignar inmediatamente `self.activa = Some(self.filas[self.posicion])`.
  2. En `reproductor/mod.rs::Servicio::nuevo()`, tras invocar `cola.restaurar()`, resolver la ficha de la pista activa inicial (`self.resolver(activa)`) para que `self.actual` esté presente en reposo (`Estado::Detenido` / `Estado::Pausado`), con su duración real y su posición persistida.
  3. De este modo, la primera instantánea reflejará la pista precargada, su título, portada, duración y segundo de reanudación, con el reproductor en pausa listo para reproducir.

---

### [ALERTA] BUG-02 (QA-02): Saludos anacrónicos y desfasados en la vista de Inicio
- **Ubicación:** `src/routes/+page.svelte:34-36` y textos de saludo en `src/lib/i18n/es.ts`.
- **Qué se ve / qué pasa:**  
  Al abrir la aplicación a altas horas de la noche o en plena madrugada (por ejemplo, a las 00:25 o 01:10 a.m.), el saludo principal en tipografía gigante proclama:  
  *"Buenos días, Nate. Elige el primer tono del día."* o *"Nate, abre la mañana con algo tuyo."*
- **Qué piensa / siente el usuario:**  
  *"Son las doce y media de la noche, ¿por qué la app me dice 'buenos días' y me habla de 'abrir la mañana'? Parece un bot descalibrado que no sabe en qué huso horario vive."*
- **El porqué:**  
  En `src/routes/+page.svelte`, la clasificación de tramos horarios está implementada así:
  ```ts
  const hora = new Date().getHours();
  const lista = hora < 12 ? t.saludosManana : hora < 19 ? t.saludosTarde : t.saludosNoche;
  ```
  A las 00:00 a.m. o 02:00 a.m., `hora` vale `0` o `2`. Al ser menor que `12`, el código asume ciegamente que es la mañana. En español y en la cultura horaria estándar, de 00:00 a 05:59 es "madrugada" o "noche", no mañana.
- **Solución recomendada:**  
  Ajustar el selector de tramos horarios a cuatro cuadrantes lógicos:
  ```ts
  const hora = new Date().getHours();
  const lista =
    hora >= 6 && hora < 12
      ? t.saludosManana
      : hora >= 12 && hora < 19
        ? t.saludosTarde
        : t.saludosNoche;
  ```
  Añadir saludos nocturnos específicos para madrugada en `es.ts` ("Buenas noches", "Música para la madrugada", "Acompaña la noche con algo tuyo").

---

### [ALERTA] BUG-03 (QA-03): Discrepancia entre la tarjeta "Retomar reproducción" y la pista activa
- **Ubicación:** `src/routes/+page.svelte` (`retomar = datos?.paraVolver[0]`) vs `reproductor.instantanea.cola`.
- **Qué se ve / qué pasa:**  
  En la vista de Inicio, la tarjeta destacada muestra:  
  *"RETOMAR REPRODUCCIÓN: Diosa - Myke Towers · Easy Money Baby"*.  
  Sin embargo, la cola restaurada en segundo plano tiene el modo aleatorio activo y su índice apunta a *"ADIVINO - Myke Towers"*.  
  Si el usuario pulsa la tarjeta "Retomar reproducción", suena *"Diosa"* y se vacía o reordena la cola; pero si pulsa el botón Play de la barra inferior, suena *"ADIVINO"*.
- **Qué piensa / siente el usuario:**  
  *"La app me muestra dos cosas distintas como 'lo que estaba escuchando'. No sé qué va a sonar cuando le dé al botón."*
- **El porqué:**  
  La tarjeta "Retomar" se nutre de la consulta SQL de historial (`paraVolver[0]`), mientras que la barra de reproducción se nutre del estado persistido de la cola en `reproductor_sesion`. Son dos fuentes de verdad desalineadas.
- **Solución recomendada:**  
  Si existe una cola de reproducción persistida con pista activa válida, la tarjeta de "Retomar" en Inicio debe reflejar con prioridad absoluta la pista activa de esa cola (`reproductor.pista` o `reproductor.instantanea.pistaId`), sincronizando la acción con la barra de reproducción.

---

### [ALERTA] BUG-04 (QA-04): Desbordamiento horizontal y pérdida de pestañas en Ajustes al reducir la ventana
- **Ubicación:** `src/routes/ajustes/+page.svelte` (`.pestanas-moviles`).
- **Qué se ve / qué pasa:**  
  Cuando la ventana se ajusta a un ancho mediano o compacto (~850px o modo tiling 50% de pantalla en un portátil 1080p), la barra de sub-navegación lateral de Ajustes se convierte en una hilera horizontal superior de pestañas (`Biblioteca`, `Reproducción`, `Apariencia`, `Dispositivos`, `Agregados`, `Privacidad...`).  
  El texto de `Privacidad` se corta antiestéticamente como *"Privacic"*, y las secciones posteriores **`Inteligencia artificial` y `Acerca de` quedan totalmente fuera del monitor (invisibles e inaccesibles)**. El contenedor carece de scroll horizontal o menú de desbordamiento.
- **Qué piensa / siente el usuario:**  
  *"No puedo entrar a la configuración de IA ni a la información de la app si no tengo la ventana maximizada. Se rompieron las pestañas."*
- **El porqué:**  
  El contenedor `.pestanas-moviles` tiene `display: flex; flex-wrap: nowrap; overflow: hidden;`. No permite scroll y los botones hijos tienen anchos fijos que desbordan el ancho disponible.
- **Solución recomendada:**  
  Añadir `overflow-x: auto; scrollbar-width: none; overscroll-behavior-x: contain;` al contenedor de pestañas en móvil/compacto, o sustituirlo por un selector desplegable (`<Select>`) de sección cuando el ancho sea inferior a 700px.

---

### [ALERTA] BUG-05 (QA-05): Desaparición abrupta del deslizador de volumen en la barra inferior al encoger la ventana
- **Ubicación:** `src/lib/ui/BarraReproduccion.svelte` (`.volumen`).
- **Qué se ve / qué pasa:**  
  Al reducir el ancho de la ventana, el control deslizante de volumen se oculta repentinamente por CSS (`display: none`). Solo queda el icono de altavoz, pero **hacer clic sobre el icono no abre ningún control de volumen**: simplemente se queda estático o silencia sin permitir graduar el nivel sonoro.
- **Qué piensa / siente el usuario:**  
  *"En mi ventana pequeña no puedo subir ni bajar el volumen con el ratón. Desapareció la barra y el icono no hace nada."*
- **El porqué:**  
  En pantallas compactas, la regla oculta el slider pero no provee un popover alternativo para el ajuste fino de volumen.
- **Solución recomendada:**  
  En anchos reducidos, convertir el icono de altavoz en un botón interactivo que despliegue un popover vertical con el deslizador de volumen (patrón estándar de Spotify en ventanas compactas).

---

### [ALERTA] BUG-06 (QA-06): Icono y semántica invertidos en el botón de colapso de la barra lateral
- **Ubicación:** `src/lib/ui/NavLateral.svelte:80-100`.
- **Qué se ve / qué pasa:**  
  Cuando la ventana se hace estrecha (< 900px), la barra lateral se colapsa automáticamente a riel estrecho (mostrando únicamente iconos). Sin embargo, el botón inferior de colapso **sigue mostrando la flecha apuntando a la izquierda (`<`) y su `aria-label` sigue diciendo "Colapsar barra lateral"**.
- **Qué piensa / siente el usuario:**  
  *"La barra ya está colapsada, ¿por qué la flecha apunta hacia adentro y dice 'colapsar'? Debería apuntar hacia afuera para expandirla."*
- **El porqué:**  
  El estado `aparienciaActual.barraLateralCompacta` solo cambia cuando el usuario pulsa el botón manualmente, pero no se sincroniza con el colapso automático gobernado por el contenedor CSS / ancho de pantalla.
- **Solución recomendada:**  
  Vincular el estado del icono a la propiedad efectiva de visualización (`data-compacta` o `data-ancho`).

---

### [ALERTA] BUG-07 (QA-07): Foco atrapado en la barra de búsqueda superior (Escape no desenfoca)
- **Ubicación:** `src/lib/ui/BarraSuperior.svelte` (`input`).
- **Qué se ve / qué pasa:**  
  El usuario pulsa `Ctrl+K` para buscar o hace clic en la caja de búsqueda. Si decide no buscar nada y pulsa la tecla `Escape`, **el campo de texto no pierde el foco**. El anillo naranja permanece activo y el cursor sigue parpadeando.  
  Dado que el foco está en un campo de texto, **todos los atajos de teclado globales de la aplicación (Espacio para pausar, flechas, L para letras, F para ampliada, etc.) quedan completamente deshabilitados e inoperantes**.
- **Qué piensa / siente el usuario:**  
  *"Le di a Escape para salir del buscador y la app no responde al espacio ni a los atajos. Tengo que buscar con el ratón un área vacía y hacer clic para poder usar el teclado otra vez."*
- **El porqué:**  
  El elemento `<input type="search">` carece de listener para la tecla `Escape` (`onkeydown={(e) => if (e.key === 'Escape') campo?.blur()}`).
- **Solución recomendada:**  
  Añadir manejador de `Escape` que desenfoque el campo y limpie la consulta si no está en `/buscar`.

---

## 3. Pulido Estético, Falta de Dinamismo y Deformidad de Controles

---

### [ESTÉTICA] DIS-01 (QA-08): Las barras estáticas gruesas en la cabecera de Inicio (`EcualizadorBarras.svelte`)
- **Ubicación:** `src/routes/+page.svelte` y `src/lib/ui/EcualizadorBarras.svelte`.
- **Diagnóstico visual y UX:**  
  El componente renderiza 24 rectángulos verticales gruesos de color degradado sobre un fondo gris oscuro.  
  - **En reposo (música detenida):** Muestra una silueta congelada artificial (`SILUETA_ESTATICA`). Parece una imagen rota o un control de depuración abandonado.  
  - **En ventana maximizada:** El encabezado usa `justify-content: space-between`, enviando este bloque solitario al extremo derecho a 900 píxeles del saludo, desconectado del contenido.  
  - **En ventana compacta:** Cae torpemente debajo del subtítulo, devorando espacio vertical útil.  
- **Veredicto del QA Senior:**  
  Este elemento debe ser **completamente eliminado de la cabecera de Inicio**. La cabecera debe respirar con tipografía limpia. El dinamismo del ecualizador debe pertenecer exclusivamente a la barra de reproducción (la forma de onda activa que ya funciona con picos reales) o a la vista expandida.

---

### [ESTÉTICA] DIS-02 (QA-09): Selectores desplegables que parecen formularios web antiguos
- **Ubicación:**  
  - `src/routes/biblioteca/+page.svelte` (`.selector-orden`)
  - `src/lib/ui/ajustes/SeccionesEscucha.svelte` (Preselección de ecualizador)
  - `src/lib/ui/copia/BloqueCopia.svelte` (Frecuencia de copia)
  - `src/lib/ui/dispositivos/SeccionDispositivos.svelte` (Selector de qué copiar)
  - `src/lib/ui/playlists/DialogoInteligente.svelte` (Filtros de playlist inteligente)
- **Diagnóstico visual y UX:**  
  Todos estos elementos están implementados como `<select class="...">` nativos de HTML. Al hacer clic, abren el menú desplegable gris genérico del navegador WebKit / GTK con flechas duras de formulario web. En una aplicación de escritorio moderna de música, los selectores de ordenación y opciones son botones con menú flotante estético (*Material 3 Menu / Popover*), tipografía a tono y marcas de verificación elegantes.
- **Solución recomendada:**  
  Crear un componente reutilizable `MenuSelector.svelte` basado en la API nativa de Popover (`popover="auto"`), con animación corta de apertura, borde tonal y soporte de teclado (`ArrowUp`, `ArrowDown`, `Enter`).

---

### [ESTÉTICA] DIS-03 (QA-10): Botones de acción apilados y sin jerarquía en la cabecera de Playlists
- **Ubicación:** `src/routes/playlists/+page.svelte` (`.cabecera`).
- **Diagnóstico visual y UX:**  
  En la parte superior de `/playlists`, los botones de acción aparecen desalineados:  
  En la fila superior derecha aparecen `Crear para mí` y `+ Nueva inteligente` (ambos con estilo *outlined* transparente), y directamente debajo de ellos, flotando en solitario en una segunda línea, aparece `+ Nueva playlist` (con relleno naranja sólido).  
  No forman una barra de herramientas unificada; parecen botones arrojados a la cabecera con `flex-wrap` sin calibrar.
- **Solución recomendada:**  
  Unificar los controles en una sola barra de acciones horizontal: botón primario relleno `+ Nueva playlist`, acompañado de un menú desplegable o botones secundarios consistentes `Nueva inteligente` y `Crear para mí`, alineados a la derecha del título.

---

### [ESTÉTICA] DIS-04 (QA-11): Casillas de verificación cuadradas en lugar de interruptores Material 3 en Ajustes
- **Ubicación:** `src/lib/ui/ajustes/SeccionesEscucha.svelte` y `SeccionDispositivos.svelte`.
- **Diagnóstico visual y UX:**  
  Las opciones "Igualar el volumen entre canciones" y "Ecualizador activo" se activan mediante casillas cuadradas (`<input type="checkbox">` de formulario HTML). En reproductores de música modernos y en el estándar de Material 3, las preferencias de audio globales se representan con interruptores deslizantes suaves (*Switch* / *Toggle*). Las casillas cuadradas dan un aspecto de hoja de cálculo o formulario fiscal.
- **Solución recomendada:**  
  Sustituir las casillas cuadradas por el componente `Switch` de `m3-svelte` o un interruptor toggle CSS con animación fluida sin reflujo.

---

### [ESTÉTICA] DIS-05 (QA-12): Desiertos de espacio negro en Detalle de Álbum y A ciegas
- **Ubicación:** `src/routes/biblioteca/album/+page.svelte` y `src/routes/a-ciegas/+page.svelte`.
- **Diagnóstico visual y UX:**  
  - **En `/biblioteca/album`:** Si un álbum tiene pocas pistas (como `$ad Boyz 4 Life` con 1 pista, o un single), la pantalla muestra la portada, los 3 botones y la fila solitaria. El 80% inferior de la ventana es un vacío negro desértico sin gradiente ambiental de la portada, sin créditos, sin botón de artista ni canciones recomendadas.
  - **En `/a-ciegas`:** Las 4 tarjetas de modalidad y los botones de retos ocupan los primeros 250 píxeles. El resto de la pantalla está vacío hasta la barra inferior.
- **Solución recomendada:**  
  1. En detalle de álbum, añadir fondo con gradiente sutil derivado de la portada (`--m3c-primary-container`), bloque de metadatos enriquecidos (discográfica, formato, tasa de bits de los archivos) y sección *"Más álbumes de [Artista]"* en la parte inferior.
  2. En A ciegas, poblar el área inferior con el panel de récords locales: *"Tu mejor racha"*, *"Canciones acertadas esta semana"*, *"Modo favorito"* y gráfico de aciertos.

---

### [ESTÉTICA] DIS-06 (QA-13): El popover de la cola de reproducción desentona con el color ambiental de la portada
- **Ubicación:** `src/lib/ui/BarraReproduccion.svelte` (`.capa-cola`) y `src/lib/ui/PanelCola.svelte`.
- **Diagnóstico visual y UX:**  
  Cuando el usuario se encuentra en la vista expandida de reproducción (`/reproduciendo`) o con letras activas, el fondo de la pantalla adopta el color tonal dinámico de la portada (ej. púrpura profundo con "ADIVINO"). Al pulsar `Ctrl+Q` para desplegar la cola, el popover flota con un fondo gris/marrón carbón estándar (`--m3c-surface-container`), generando un corte visual tosco contra el lienzo teñido.
- **Solución recomendada:**  
  Utilizar tokens de superficie reactivos (`var(--m3c-surface-container-high)`) o aplicar una sutil transparencia tonal coordinada con el esquema activo.

---

### [ESTÉTICA] DIS-07 (QA-14): Rectángulos grises huérfanos por miniaturas no precachéadas en Tu música
- **Ubicación:** `src/lib/ui/perfil/VistaTuMusica.svelte` (listas de Tops).
- **Diagnóstico visual y UX:**  
  En las listas de "Top canciones" y "Top álbumes", cuando una pista no tiene miniatura generada en caché local, se pinta un rectángulo gris plano sin bordes ni icono. Esto arruina la presentación de la sección de estadísticas personales.
- **Solución recomendada:**  
  Asegurar que el elemento sustituto muestre un contenedor estilizado con el icono SVG `<Icon nombre="cancion" />` o `<Icon nombre="album" />` con tinte tonal del tema, idéntico al fallback de Biblioteca.

---

## 4. Convenciones Faltantes y Experiencia de Usuario (Modelos Mentales Rotos)

---

### [EXP] EXP-01 (QA-15): Imposibilidad de cambiar o configurar la foto de perfil del usuario
- **Ubicación:** `src/lib/ui/perfil/VistaTuMusica.svelte` y `src/routes/ajustes/+page.svelte`.
- **Comportamiento observado:**  
  El usuario ve su nombre "Nate" y su foto importada de la V1 en la cabecera de `Tu música`. Sin embargo, no existe ninguna forma de cambiar la imagen: ni haciendo clic en el círculo, ni mediante arrastrar y soltar, ni en los Ajustes generales.
- **Confusión adicional:**  
  El logotipo grande de la marca en la parte superior de la barra lateral (la silueta de mujer con auriculares dentro de un círculo teñido) parece a simple vista un avatar de perfil. El usuario intenta hacer clic sobre él esperando editar su perfil o acceder a sus datos personales.
- **Expectativa QA:**  
  1. En `Tu música` (`/tu-musica`), convertir el círculo de la foto en un control interactivo: al pasar el ratón, superponer un icono de cámara/edición con tooltip *"Cambiar foto de perfil"*; al hacer clic, invocar el diálogo nativo de Tauri para seleccionar una imagen local (PNG, JPG, WebP), guardarla en la carpeta de configuración y actualizar la vista inmediatamente.
  2. En `Ajustes > Biblioteca` o en una sección propia `Perfil`, permitir cambiar tanto el nombre como la foto de perfil con un botón *"Elegir imagen"*.

---

### [EXP] EXP-02 (QA-16): La vista de Artista carece de sección de Discografía / Álbumes
- **Ubicación:** `src/routes/biblioteca/artista/+page.svelte`.
- **Comportamiento observado:**  
  Al entrar al detalle de un artista (por ejemplo, Adele, que indica *"9 álbumes · 35 pistas"*), la pantalla muestra el nombre del artista, los botones de Reproducir/Aleatorio, y a continuación únicamente un encabezado *"Canciones"* con las 35 canciones en una lista plana. **Los 9 álbumes no aparecen por ninguna parte**.
- **Qué espera el usuario:**  
  En Spotify, Apple Music, YouTube Music y en la propia V1 de NB Sound, la página de un artista se organiza con:
  1. Canciones populares / Más escuchadas.
  2. **Discografía / Álbumes:** Cuadrícula o carrusel horizontal con las portadas de sus álbumes para poder entrar a escuchar un álbum específico.
  3. Sencillos y EPs.
- **Expectativa QA:**  
  Restaurar la sección de Álbumes del artista en `/biblioteca/artista/+page.svelte`, consultando los álbumes correspondientes a `artistaId` y mostrándolos en una cuadrícula interactiva.

---

### [EXP] EXP-03 (QA-17): La barra lateral no se oculta en la vista inmersiva de reproducción (`/reproduciendo`)
- **Ubicación:** `src/routes/reproduciendo/+page.svelte` y `src/lib/ui/AppShell.svelte`.
- **Comportamiento observado:**  
  Al pulsar `L` o abrir la vista de letras y reproducción completa, la ventana conserva visible la barra lateral fija con todos los destinos de navegación (`Inicio`, `Biblioteca`, `Playlists`...).  
  Esto aprisiona la carátula y las letras en un área reducida y le quita todo el carácter inmersivo al modo reproductor.
- **Expectativa QA:**  
  Al navegar a `/reproduciendo`, la carcasa principal debe replegar automáticamente la barra lateral a modo oculto o flotante transitorio, expandiendo la portada y las letras para que abarquen el ancho completo del monitor.

---

### [EXP] EXP-04 (QA-18): El botón de Pantalla Completa en la barra inferior no tiene tooltip explicativo
- **Ubicación:** `src/lib/ui/BarraReproduccion.svelte` (icono de pantalla completa).
- **Comportamiento observado:**  
  El botón de pantalla completa en el extremo derecho de la barra inferior carece de `title` que informe del atajo de teclado universal (`F11`), a diferencia de otros botones de la aplicación.

---

## 5. Matriz de Hallazgos y Prioridades de Corrección

| ID | Severidad | Categoría | Pantalla / Módulo | Descripción Resumida |
|---|---|---|---|---|
| **QA-01** | **Crítica** | Lógica / Estado | Barra Reproducción | Barra dice "Nada sonando" al arrancar teniendo cola cargada de 39 canciones |
| **QA-02** | **Alta** | Lógica / i18n | Inicio (`/`) | Saludos dicen "buenos días" y "abrir la mañana" a las 00:30 de la noche |
| **QA-03** | **Alta** | Coherencia | Inicio vs Cola | Tarjeta "Retomar" muestra una pista distinta a la que suena al pulsar Play |
| **QA-04** | **Alta** | Responsividad | Ajustes (`/ajustes`) | Pestañas de Ajustes se truncan y cortan en ventana compacta sin scroll |
| **QA-05** | **Alta** | Responsividad | Barra Reproducción | Deslizador de volumen desaparece en ventana pequeña sin popover alternativo |
| **QA-06** | **Media** | UI / Semántica | NavLateral | Icono del botón de colapso apunta a la izquierda (`<`) estando ya colapsada |
| **QA-07** | **Alta** | Teclado / Accesibilidad | Barra Superior | Tecla `Escape` no desenfoca el buscador, bloqueando todos los atajos |
| **QA-08** | **Media** | Estética / Pulido | Inicio (`/`) | Barras estáticas gruesas y artificiales de ecualizador en la cabecera |
| **QA-09** | **Media** | Componentes UI | Vistas varias | Menús desplegables implementados como `<select>` web sin estilo de app |
| **QA-10** | **Media** | Disposición UI | Playlists (`/playlists`) | Botones de creación apilados de forma caótica y sin alineación |
| **QA-11** | **Baja** | Estética | Ajustes > Audio | Casillas de verificación cuadradas en lugar de interruptores suaves (Switches) |
| **QA-12** | **Media** | Dinamismo / Espacio | Detalle Álbum / A ciegas | Desiertos de espacio negro vacío que transmiten frialdad y abandono |
| **QA-13** | **Baja** | Coherencia Tonal | Panel de Cola | Popover de cola usa superficie gris en lugar de acompañar el tono de portada |
| **QA-14** | **Media** | Estética / Fallback | Tu música (`/tu-musica`) | Rectángulos grises mudos para pistas sin miniatura en tops |
| **QA-15** | **Alta** | Funcional / Perfil | Tu música y Ajustes | Imposibilidad absoluta de cambiar o subir una foto de perfil de usuario |
| **QA-16** | **Alta** | Navegación / Catálogo | Detalle Artista | La vista de artista no muestra los álbumes / discografía del artista |
| **QA-17** | **Media** | Inmersión | Reproducción expandida | La barra lateral permanece visible quitando inmersión a las letras |
| **QA-18** | **Baja** | Accesibilidad | Barra Reproducción | Botón de pantalla completa carece de tooltip de atajo (`F11`) |

---

## 6. Conclusión y Veredicto del QA Senior

La base técnica de Rust y Svelte 5 es sólida y reactiva, pero **la experiencia de usuario sigue sufriendo de asperezas notables que delatan un port acelerado**:
- No es admisible que un reproductor de música de escritorio abra con 39 canciones cargadas y le diga al usuario *"Nada sonando"*, para luego arrancar de golpe al tocar play.
- No es admisible que una cabecera salude dando los *"buenos días"* a la una de la madrugada.
- No es admisible que los selectores de ordenación parezcan un formulario de registro web de los años 90.
- No es admisible que el usuario no pueda actualizar su foto de perfil ni explorar los álbumes de sus artistas favoritos en su propia biblioteca.
- No es admisible que en ventanas compactas las opciones de configuración se salgan de la pantalla y el volumen desaparezca.

Este informe sienta las bases exactas para la siguiente tanda de refinamiento antes de proceder a la firma de las pruebas finales y la publicación de la versión 2.1.0.

