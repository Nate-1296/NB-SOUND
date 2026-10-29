#!/usr/bin/env node
/**
 * Comprobación del sistema de diseño y de la accesibilidad de los componentes.
 *
 * Portado de NB Books; las reglas son las de su ADR-012, que NB Sound adopta en
 * su ADR-008.
 *
 * Existe porque el criterio de aceptación de F1.6.2 dice que ningún componente
 * base tiene violaciones de accesibilidad automatizables, y una afirmación así
 * sin mecanismo detrás es exactamente lo que este proyecto no se permite.
 *
 * Se apoya en dos cosas y añade una tercera:
 *
 *   1. El compilador de Svelte, que ya avisa de la mayor parte de los defectos
 *      de accesibilidad del marcado. `pnpm check` lo ejecuta con
 *      `--fail-on-warnings`, así que esos avisos bloquean.
 *   2. Biome, que vigila la frontera del puente IPC.
 *   3. Esto: las reglas propias de ADR-012, que ninguna herramienta general
 *      puede conocer.
 *
 * No sustituye a la auditoría con motor de accesibilidad sobre las vistas
 * completas: eso es F1.7.3, y necesita vistas que todavía no existen. Tampoco
 * sustituye a la verificación manual con lector de pantalla, que es F1.7.4.
 *
 * Uso: node scripts/check-ui.mjs
 */

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { extname, join, relative, resolve } from 'node:path';

const ROOT = resolve(import.meta.dirname, '..');
// Otro árbol como argumento, igual que los demás guardianes: es como sus pruebas
// lo rompen a propósito sin tocar el código de verdad.
const FUENTE = process.argv[2] ? resolve(process.argv[2]) : join(ROOT, 'src');

/** La hoja base es el único sitio donde viven los colores y los `!important`. */
const HOJA_BASE = join(FUENTE, 'app.css');

/**
 * Las paletas generadas cuentan como hoja base.
 *
 * Es donde **se definen** los colores, no donde se usan: exigirle que use
 * variables sería pedirle que se defina en términos de sí misma. Lo genera
 * `scripts/generar-paletas.mjs` desde el mismo generador que la aplicación, y de
 * que no se separen se encarga `pnpm check:paletas`.
 */
const PALETAS = join(FUENTE, 'paletas.css');

/**
 * Los únicos componentes que pueden desenfocar el fondo, y por qué.
 *
 * `backdrop-filter` no es un color más: es un filtro que el motor rehace cada
 * vez que cambia lo que hay detrás. Sobre cromo permanente —una barra lateral,
 * un banner, un panel— lo que hay detrás cambia en cada fotograma de
 * desplazamiento, así que el filtro se rehace en cada uno. En WebKitGTK, que es
 * el motor en Linux, eso se ve como parpadeo, y es de dónde venía el "se siente
 * pesada" del 2026-09-01.
 *
 * Sobre un flotante que aparece y se va, en cambio, no cuesta nada apreciable.
 * Esa es la línea, y por eso la lista es de sitios y no de valores: lo que
 * decide si el desenfoque vale la pena no es cuánto desenfoca, sino cuánto rato
 * está en pantalla y qué se mueve por debajo.
 *
 * Añadir uno es una decisión, no un descuido: se añade aquí, con su motivo.
 */
const CRISTAL_PERMITIDO = new Set([]);

/** @param {string} dir @returns {string[]} */
/**
 * Si el elemento donde está el gesto atiende también al teclado.
 *
 * Se busca hacia atrás la apertura de la etiqueta y hacia delante su cierre, y
 * se mira si dentro hay un manejador de teclado. Es una comprobación sobre el
 * marcado y no sobre el comportamiento, así que no demuestra que la tecla haga
 * lo mismo que el gesto; lo que descarta es el caso que la regla persigue, que
 * es no haber puesto ninguna.
 */
function tieneEquivalenteDeTeclado(texto, indice) {
  const apertura = texto.lastIndexOf('<', indice);
  if (apertura < 0) return false;

  // El cierre se busca contando llaves. Un atributo de Svelte lleva una
  // expresión dentro, y una función flecha tiene un `>` en medio: buscar el
  // primer `>` cortaría la etiqueta por la mitad de `() => abrir(item)` y la
  // comprobación miraría donde no es.
  let profundidad = 0;
  let cierre = -1;
  for (let i = apertura; i < texto.length; i += 1) {
    const c = texto[i];
    if (c === '{') profundidad += 1;
    else if (c === '}') profundidad = Math.max(0, profundidad - 1);
    else if (c === '>' && profundidad === 0) {
      cierre = i;
      break;
    }
  }
  if (cierre < 0) return false;

  const etiqueta = texto.slice(apertura, cierre);
  return /\bon(keydown|keyup|keypress)\s*=/.test(etiqueta);
}

function recorrer(dir) {
  const salida = [];
  for (const entrada of readdirSync(dir)) {
    const completo = join(dir, entrada);
    if (statSync(completo).isDirectory()) {
      if (entrada === 'bindings') continue; // Generado desde Rust.
      salida.push(...recorrer(completo));
    } else if (['.svelte', '.css'].includes(extname(entrada))) {
      salida.push(completo);
    }
  }
  return salida;
}

function recorrerTodosLosFuentes(dir) {
  const salida = [];
  for (const entrada of readdirSync(dir)) {
    const completo = join(dir, entrada);
    if (statSync(completo).isDirectory()) {
      if (entrada === 'bindings' || entrada === 'node_modules') continue;
      salida.push(...recorrerTodosLosFuentes(completo));
    } else if (['.svelte', '.ts', '.js'].includes(extname(entrada))) {
      salida.push(completo);
    }
  }
  return salida;
}

const problemas = [];

/** @param {string} archivo @param {string} texto @param {number} indice */
function linea(texto, indice) {
  return texto.slice(0, indice).split('\n').length;
}

function informar(archivo, texto, indice, mensaje) {
  problemas.push(`${relative(ROOT, archivo)}:${linea(texto, indice)}  ${mensaje}`);
}

/**
 * Sustituye los comentarios por espacios, conservando las posiciones.
 *
 * Sin esto, un comentario que explica una regla prohibida la dispara: el propio
 * `app.css` documenta por qué no se apaga el contorno del foco, y esa frase
 * contiene literalmente el texto que se busca.
 */
function sinComentarios(texto) {
  return texto.replace(/\/\*[\s\S]*?\*\/|<!--[\s\S]*?-->/g, (c) => ' '.repeat(c.length));
}

/** Bloques `<style>` de un componente, o el archivo entero si es CSS. */
function estilos(archivo, texto) {
  if (extname(archivo) === '.css') return [{ contenido: texto, desplazamiento: 0 }];

  const bloques = [];
  for (const coincidencia of texto.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)) {
    bloques.push({
      contenido: coincidencia[1] ?? '',
      desplazamiento: (coincidencia.index ?? 0) + (coincidencia[0].indexOf('>') + 1)
    });
  }
  return bloques;
}

/*
 * Un color escrito en un componente, en cualquiera de sus formas.
 *
 * Los nombres CSS entran en la lista porque `color-mix(in srgb, white 4%, …)`
 * es tan literal como `#ffffff` y se colaba entero: la regla existía y el
 * mecanismo no la hacía cumplir. Solo se vigilan los que de verdad aparecen
 * haciendo de color —blanco, negro y los grises— y no las ciento cuarenta
 * palabras del estándar, que ensuciarían con falsos positivos cualquier
 * identificador que se llamara igual.
 *
 * `transparent` y `currentColor` no son colores del tema: no se marcan. El
 * guion que sigue al nombre tampoco: `white-space` es una propiedad, no un
 * color, y marcarla sería enseñar a ignorar el aviso.
 */
const COLOR_LITERAL =
  /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|lab|color)\(|\b(?:white|black|gray|grey|silver)\b(?!-)/g;

/**
 * Emojis y los símbolos tipográficos que se usan como icono.
 *
 * Los rangos cubren pictogramas, símbolos varios, dingbats y banderas; los
 * sueltos son los que aparecen una y otra vez haciendo de icono: aspa, flechas,
 * marca de verificación, punto medio, triángulos de reproducción.
 */
const EMOJI =
  /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}\u{00D7}\u{2022}\u{2713}\u{2714}\u{2190}-\u{21FF}\u{25B6}\u{25C0}\u{2018}]/gu;

/** Palabras que van en minúscula dentro de un título. Ver docs/adr/decisions/ADR-008-sistema-de-diseno.md. */
const FUNCIONALES = new Set([
  'a', 'al', 'ante', 'bajo', 'con', 'contra', 'de', 'del', 'desde', 'e', 'el', 'en', 'entre', 'hacia',
  'hasta', 'la', 'las', 'lo', 'los', 'ni', 'o', 'para', 'por', 'que', 'según', 'sin', 'sobre',
  'tras', 'u', 'un', 'una', 'y'
]);

/**
 * Comprueba el formato de título, y devuelve qué falla o `null`.
 *
 * Solo mira frases que **parecen** un título: sin signos de puntuación finales y
 * de pocas palabras. Una etiqueta que es una frase completa —"Pulsa Escape para
 * volver"— no es un título y no se toca.
 */
function tituloMalFormado(frase) {
  if (/[.:;?!,]/.test(frase)) return null;
  const palabras = frase.trim().split(/\s+/);
  if (palabras.length === 0 || palabras.length > 6) return null;
  if (!/^[A-ZÁÉÍÓÚÑ]/.test(palabras[0])) return null;

  for (let i = 1; i < palabras.length; i += 1) {
    const palabra = palabras[i];
    if (!/^[A-Za-zÁÉÍÓÚÑáéíóúñ]+$/.test(palabra)) continue;
    const minuscula = palabra.toLowerCase();
    const empiezaEnMayuscula = /^[A-ZÁÉÍÓÚÑ]/.test(palabra);

    if (FUNCIONALES.has(minuscula) && empiezaEnMayuscula) {
      return `"${palabra}" es una palabra funcional y va en minúscula dentro de un título`;
    }
    if (!FUNCIONALES.has(minuscula) && !empiezaEnMayuscula) {
      return `"${palabra}" es una palabra significativa y va en mayúscula dentro de un título`;
    }
  }
  return null;
}

for (const archivo of recorrer(FUENTE)) {
  const crudo = readFileSync(archivo, 'utf8');
  const texto = sinComentarios(crudo);
  const esHojaBase = archivo === HOJA_BASE || archivo === PALETAS;

  /*
   * **Ningún medio se reproduce desde el esquema propio de la aplicación.**
   *
   * WebKitGTK entrega el audio a GStreamer, que no sabe hablar ese esquema y
   * responde "fuente no soportada" (performance-budgets.md 4.3.1): hay que traerlo
   * con `fetch` y darlo como `blob:`. La regla se incumplió **dos veces** -la voz de
   * un servicio en la Fase 1, y el audio preparado en la 4, que no sonó nunca en la
   * aplicación-, y ninguna prueba podía verlo porque la suite corre en Chromium,
   * donde la dirección directa suena. Por eso es un guardián y no una nota.
   */
  for (const m of texto.matchAll(
    /<(?:audio|video|source)\b[^>]*\bsrc=\{\s*rutaDeImagen\(|new\s+Audio\(\s*rutaDeImagen\(/g
  )) {
    informar(
      archivo,
      texto,
      m.index ?? 0,
      'un medio reproducido desde el esquema propio: WebKitGTK no lo reproduce; tráelo con `enBlob` de `$lib/voz/preparado`'
    );
  }

  /* --- Reglas sobre los estilos --------------------------------------- */
  for (const { contenido, desplazamiento } of estilos(archivo, texto)) {
    if (!esHojaBase) {
      // Un color literal en un componente no cambia con el tema. El modo
      // oscuro y el alto contraste dejarían de aplicarle en silencio, y solo
      // lo notaría quien depende de ellos.
      for (const c of contenido.matchAll(COLOR_LITERAL)) {
        informar(
          archivo,
          texto,
          desplazamiento + (c.index ?? 0),
          `color literal "${c[0]}": los colores vienen del sistema de diseño, usa var(--m3c-...) o var(--nb-...)`
        );
      }

      /*
       * **La escala de espaciado, con mecanismo.**
       *
       * La regla existía desde el principio -"una sola escala, la de app.css;
       * los valores intermedios no existen"- y no tenía guardián. El 2026-09-10,
       * al traer Material 3, la interfaz pasó de 306 usos de la escala a **uno**
       * y de 17 literales en píxeles a 225. No fue una decisión: ADR-014 deroga
       * el origen de los colores y no dice nada del espaciado.
       *
       * Lo que se pierde no es sólo el ritmo. La escala está en `rem` y los
       * píxeles no, así que con la tipografía al 200 % el texto crece y los
       * márgenes se quedan quietos: quien amplía la letra acaba con el texto
       * pegado a los bordes.
       *
       * Se admiten 0, 1 y 2 píxeles, que son filetes y detalles por debajo del
       * primer paso de la escala, y los porcentajes, que son proporciones.
       *
       * Lo mismo vale para `font-size`, y ahí el daño es mayor: la escala
       * tipográfica multiplica por `--nb-font-scale`, que es el ajuste de tamaño
       * de letra de Ajustes. Con la migración quedaron 139 tamaños escritos a
       * mano, y en todos ellos ese ajuste dejó de hacer nada.
       */
      for (const c of contenido.matchAll(
        /(?:^|[;{])\s*(padding|margin|gap|row-gap|column-gap|border-radius|font-size|(?:padding|margin)-(?:top|right|bottom|left|inline|block)(?:-(?:start|end))?)\s*:\s*([^;{}]+)/g
      )) {
        /*
         * Un valor que ya pasa por un token -`var(--nb-libro-cuerpo, 1.125rem)`-
         * lo gobierna ese token, y su respaldo solo actúa si falta. Y `clamp`
         * con unidades de contenedor es tamaño fluido: la portada mide su título
         * contra su propio ancho, que es más de lo que da un paso de escala. Ni
         * uno ni otro son el descuido que esto busca.
         */
        if (/var\(|clamp\(/.test(c[2])) continue;

        const literal =
          c[1] === 'font-size'
            ? c[2].match(/\b\d+(?:\.\d+)?(?:rem|px|em)\b/)
            : c[2].match(/\b([3-9]\d*|\d{2,})px\b/);
        if (literal) {
          informar(
            archivo,
            texto,
            desplazamiento + (c.index ?? 0),
            `${c[1]}: ${literal[0]} está fuera de la escala: usa var(--nb-space-...), var(--nb-radius-...) o var(--nb-text-...)`
          );
        }
      }

      // `!important` reservado a la red de seguridad de movimiento reducido.
      for (const c of contenido.matchAll(/!important/g)) {
        informar(
          archivo,
          texto,
          desplazamiento + (c.index ?? 0),
          '!important solo se admite en app.css'
        );
      }
    }

    // El desenfoque de fondo, solo donde está justificado. Ver CRISTAL_PERMITIDO.
    if (!esHojaBase && !CRISTAL_PERMITIDO.has(archivo)) {
      for (const c of contenido.matchAll(/(?:-webkit-)?backdrop-filter\s*:/g)) {
        informar(
          archivo,
          texto,
          desplazamiento + (c.index ?? 0),
          'backdrop-filter en cromo permanente: rehace el desenfoque en cada fotograma. Ver CRISTAL_PERMITIDO en scripts/check-ui.mjs'
        );
      }
    }

    // Donde sí se admite, el prefijo no es opcional: WebKitGTK, que es el motor
    // en Linux, solo entiende la forma prefijada, y sin ella el efecto no
    // aparece justo en la plataforma de referencia del proyecto.
    for (const c of contenido.matchAll(/(?<!-webkit-)backdrop-filter\s*:\s*([^;]+);/g)) {
      const gemelo = new RegExp(
        `-webkit-backdrop-filter\\s*:\\s*${c[1].trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*;`
      );
      if (!gemelo.test(contenido)) {
        informar(
          archivo,
          texto,
          desplazamiento + (c.index ?? 0),
          'backdrop-filter sin su gemelo -webkit-: en WebKitGTK no se aplica'
        );
      }
    }

    /*
     * **La barra superior tiene que contener su disposición.**
     *
     * Medido en el motor real el 2026-09-18 —WebKitGTK, con la biblioteca de
     * verdad dentro—: escribir una letra en el buscador costaba 133 ms, de los
     * que 120 eran disposición, porque un cambio de texto en esa barra ensucia
     * todo lo que hay debajo. El mismo campo en el contenido costaba 17 ms y cero
     * de disposición. Con `contain: layout size` en la barra, 17.
     *
     * Solo esa combinación lo corta: `layout` sola, `content` e `inline-size`
     * seguían costando 110 ms. Se comprueba aquí porque en Chromium —que es donde
     * corren los recorridos— el defecto **no aparece**, así que ninguna prueba de
     * tiempo puede cazarlo.
     */
    if (archivo.endsWith('BarraSuperior.svelte')) {
      const barra = contenido.match(/\.superior\s*\{[^}]*\}/s);
      if (barra && !/contain\s*:\s*layout\s+size/.test(barra[0])) {
        informar(
          archivo,
          texto,
          desplazamiento + (barra.index ?? 0),
          'la barra superior sin `contain: layout size`: escribir en ella vuelve a costar cien milisegundos por letra en WebKitGTK'
        );
      }
    }

    /*
     * `will-change` no se usa.
     *
     * Anuncia un cambio permanente, y el motor responde fijando una capa de
     * composición que ya no suelta. En una regla que alcanza a una lista
     * —cada portada de la biblioteca, por ejemplo— eso son tantas capas como
     * elementos: medido el 2026-09-01, cincuenta y cuatro en reposo. Lo que se
     * puede componer, el motor lo compone solo al empezar la transición.
     */
    for (const c of contenido.matchAll(/will-change\s*:/g)) {
      informar(
        archivo,
        texto,
        desplazamiento + (c.index ?? 0),
        'will-change fija una capa de composición por elemento; el motor ya promociona lo que transiciona'
      );
    }

    /*
     * Un `:hover` no puede mover la caja del elemento que lo recibe.
     *
     * `transform: translateY(-4px)` mueve la caja **y su área sensible**. Con el
     * puntero en los últimos píxeles del elemento, levantarlo lo saca de debajo
     * del ratón: el hover se apaga, el elemento vuelve a su sitio y el hover se
     * enciende otra vez. A sesenta fotogramas por segundo eso se ve temblar, y
     * no es un defecto de pintado: es el hover encendiéndose y apagándose de
     * verdad. Lo encontró alguien usando la aplicación el 2026-09-02, en Inicio,
     * en la biblioteca y en Descubrir a la vez.
     *
     * `scale` por encima de 1 sí vale: solo puede agrandar el área, así que el
     * ciclo no puede darse, y la elevación la da la sombra igual de bien.
     *
     * La regla solo aplica cuando **el sujeto del selector es el que recibe el
     * hover**: `.tarjeta:hover .portada` mueve la portada, y el área de la
     * tarjeta no cambia. Por eso se mira si después del `:hover` hay un
     * combinador.
     */
    for (const regla of contenido.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      const selector = regla[1] ?? '';
      const cuerpo = regla[2] ?? '';
      if (!selector.includes(':hover')) continue;
      if (!/(?:transform|translate)\s*:/.test(cuerpo)) continue;

      /*
       * `trimEnd` antes de buscar el combinador. El espacio que hay entre el
       * selector y su llave no es un combinador, y sin quitarlo toda regla escrita
       * como `.x:hover {` —que es como la deja Prettier, o sea todas— contaba como
       * si el hover fuera de otro elemento. La regla no se aplicó nunca sobre CSS
       * formateado: lo destapó la revisión de F5.4.5 rompiéndola a propósito.
       */
      const elHoverEsElSujeto = selector
        .split(',')
        .filter((parte) => parte.includes(':hover'))
        .some((parte) => !/[\s>+~]/.test(parte.slice(parte.lastIndexOf(':hover') + 6).trimEnd()));
      if (!elHoverEsElSujeto) continue;

      /*
       * Se mueve si **algún** argumento no es cero. Antes solo se miraba el
       * primero, así que `translate(0, -2px)` —subir sin moverse en horizontal—
       * pasaba por quieto. Y cuenta también la propiedad suelta `translate`, que
       * mueve la caja exactamente igual que la función.
       */
      const quieto = (argumento) => /^\s*(?:none|-?0(?:\.0+)?(?:px|%|em|rem)?)\s*$/.test(argumento);
      const funciones = /transform\s*:/.test(cuerpo)
        ? [...cuerpo.matchAll(/translate(?:[XYZ]|3d)?\(([^)]*)\)/g)].map((m) => ({
            nombre: m[0],
            argumentos: m[1].split(',')
          }))
        : [];
      const suelta = /(?:^|[;{\s])translate\s*:\s*([^;]+)/.exec(cuerpo);
      const movimiento = [
        ...funciones,
        ...(suelta
          ? [{ nombre: `translate: ${suelta[1].trim()}`, argumentos: suelta[1].trim().split(/\s+/) }]
          : [])
      ].find((candidato) => candidato.argumentos.some((argumento) => !quieto(argumento)));
      if (!movimiento) continue;

      informar(
        archivo,
        texto,
        desplazamiento + (regla.index ?? 0),
        `un :hover que se desplaza saca al elemento de debajo del ratón y parpadea (${movimiento.nombre}); usa scale y sombra`
      );
    }

    /*
     * Un `:hover` no puede cambiar una propiedad que fuerza disposición.
     *
     * La regla de arriba mira si el elemento **se mueve**; esta mira lo que
     * cuesta. `width: 100%` a `max-content` al pasar el ratón obliga al motor a
     * rehacer la disposición de ese subárbol y a comprobar si algo por encima
     * cambia de tamaño, y eso ocurre al entrar y otra vez al salir. Medido el
     * 2026-09-06 en WebKitGTK sobre los dos textos de la tarjeta de "sigue
     * leyendo": sesenta encendidos y apagados cuestan 392 ms, **6,5 ms cada
     * uno**, sobre un presupuesto de fotograma de 16.
     *
     * Con el puntero quieto y la rueda girando, el contenido pasa por debajo y
     * el hover entra y sale de un elemento tras otro: en Inicio hay cuarenta y
     * ocho candidatos y veinticuatro a la vez en pantalla. De ahí viene el
     * parpadeo que se describió como "al mover rápido con la rueda".
     *
     * A diferencia de la anterior, esta regla **no** mira si el sujeto es el
     * hovereado: cambiar la caja de un descendiente cuesta lo mismo, y puede
     * además reajustar a sus antepasados.
     *
     * Color, sombra, contorno, `opacity`, `filter` y `transform` no entran: se
     * componen o se repintan, y ninguno rehace la disposición.
     */
    const DISPOSICION =
      /(?:^|[;{\s])(width|height|min-width|min-height|max-width|max-height|padding(?:-\w+)?|margin(?:-\w+)?|font-size|line-height|letter-spacing|gap|row-gap|column-gap|border-width|border-\w+-width|flex-basis|inset|top|right|bottom|left)\s*:/;
    for (const regla of contenido.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      const selector = regla[1] ?? '';
      const cuerpo = regla[2] ?? '';
      if (!selector.includes(':hover')) continue;
      const propiedad = DISPOSICION.exec(cuerpo);
      if (!propiedad) continue;

      informar(
        archivo,
        texto,
        desplazamiento + (regla.index ?? 0),
        `un :hover que cambia "${propiedad[1]}" rehace la disposición al entrar y al salir (6,5 ms medidos por vez); cambia color, sombra u opacidad`
      );
    }

    /*
     * Ninguna animación en bucle infinito, salvo el indicador de carga.
     *
     * Es la sección 12 de `ui-conventions.md`, que hasta ahora no tenía
     * mecanismo: se retiró el bucle infinito de dos marquesinas en F1.6.17 y
     * **quedaron otras dos**, en la barra lateral y en Estudio, sin que nada lo
     * dijera. Una animación permanente compite por el mismo fotograma que el
     * desplazamiento, y sobre una rejilla es una por cada elemento que se roce.
     *
     * El indicador de carga sí puede: se anima mientras tapa a lo que espera y
     * desaparece con ello, así que no hay nada con lo que competir.
     */
    if (!archivo.endsWith('Spinner.svelte')) {
      for (const c of contenido.matchAll(/animation[^;{}]*\binfinite\b/g)) {
        informar(
          archivo,
          texto,
          desplazamiento + (c.index ?? 0),
          'animación en bucle infinito: compite con el desplazamiento mientras dure; acótala o quítala'
        );
      }
    }

    /*
     * Un pseudoelemento absoluto necesita que su sujeto esté posicionado.
     *
     * `position: absolute` se coloca contra el **antepasado posicionado más
     * cercano**. Si el elemento que lo lleva no lo es, ese antepasado resulta ser
     * cualquier otro, normalmente uno enorme, y un `inset: 0` que debía cubrir una
     * tarjeta pasa a cubrir media aplicación.
     *
     * No es hipotético. El 2026-09-06, `.nb-ficha` y `.nb-sugerencia` compartían
     * el pseudoelemento de la sombra pero tenían bloques separados, y el
     * `position: relative` se añadió solo al primero: al pasar el ratón por
     * "Quizá te interese" aparecía un rectángulo redondeado del tamaño de la
     * vista, con su sombra asomando contra la barra lateral y la superior. Lo vio
     * Nathan usando la aplicación, porque es una **interacción entre dos reglas** y
     * las demás comprobaciones miran una regla cada vez.
     *
     * Se acepta cualquier `position` que cree contexto: `relative`, `absolute`,
     * `sticky` o `fixed`.
     */
    for (const regla of contenido.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      const selector = regla[1] ?? '';
      const cuerpo = regla[2] ?? '';
      if (!selector.includes('::')) continue;
      if (!/position\s*:\s*absolute/.test(cuerpo)) continue;

      for (const parte of selector.split(',')) {
        const sujeto = parte.trim().split('::')[0]?.trim().replace(/:[\w-]+$/, '');
        if (!sujeto || !/^[.#][\w-]+$/.test(sujeto)) continue;

        const propia = new RegExp(
          `(?:^|\\n)\\s*${sujeto.replace('.', '\\.')}\\s*\\{([^{}]*)\\}`
        ).exec(contenido);
        if (propia && /position\s*:\s*(relative|absolute|sticky|fixed)/.test(propia[1] ?? '')) {
          continue;
        }

        informar(
          archivo,
          texto,
          desplazamiento + (regla.index ?? 0),
          `${sujeto} lleva un pseudoelemento absoluto y no está posicionado: se colocará contra un antepasado lejano y cubrirá lo que no debe`
        );
      }
    }

    // Apagar el contorno deja sin rastro visible a quien navega por teclado.
    for (const c of contenido.matchAll(/outline\s*:\s*(?:none|0)\b/g)) {
      informar(
        archivo,
        texto,
        desplazamiento + (c.index ?? 0),
        'outline apagado: el indicador de foco lo define app.css y no se anula'
      );
    }

    // La disposición depende de `data-ancho`, cuya única fuente es anchos.ts.
    // Una consulta de medios por ancho reintroduce el punto de corte en un
    // segundo sitio, y dos fuentes acaban divergiendo.
    for (const c of contenido.matchAll(/@media[^{]*\((?:min|max)-width/g)) {
      informar(
        archivo,
        texto,
        desplazamiento + (c.index ?? 0),
        'consulta de medios por ancho: la clase de ancho la decide src/lib/ui/anchos.ts'
      );
    }
  }

  if (extname(archivo) !== '.svelte') continue;

  /* --- Reglas sobre el marcado ---------------------------------------- */

  // Desactiva el modo de navegación del lector de pantalla. ADR-012 lo prohíbe
  // sobre contenedores de la carcasa.
  for (const c of texto.matchAll(/role=["']application["']/g)) {
    informar(archivo, texto, c.index ?? 0, 'role="application": prohibido por ADR-012');
  }

  // Un tabindex positivo reordena el recorrido del teclado respecto a lo que se
  // ve. Es la misma divergencia entre orden visual y orden del documento que
  // ADR-012 prohíbe, escrita de otra forma.
  for (const c of texto.matchAll(/tabindex=["']?\s*([1-9]\d*)/g)) {
    informar(archivo, texto, c.index ?? 0, `tabindex="${c[1]}": solo se admiten 0 y -1`);
  }

  // Ningún emoji, ningún símbolo haciendo de icono, ninguna letra suelta dentro
  // de un botón. Un emoji lo dibuja el sistema operativo: no hereda el tema y en
  // alto contraste se queda como estaba. Una letra dentro de un botón la lee el
  // lector de pantalla tal cual. Ver docs/adr/decisions/ADR-008-sistema-de-diseno.md.
  for (const c of texto.matchAll(EMOJI)) {
    informar(
      archivo,
      texto,
      c.index ?? 0,
      `"${c[0]}" no se pinta: usa <Icon nombre="..."/> del catálogo (docs/adr/decisions/ADR-008-sistema-de-diseno.md)`
    );
  }

  for (const c of texto.matchAll(/>\s*([A-Za-zÁÉÍÓÚÑáéíóúñ])\s*<\/button>/g)) {
    informar(
      archivo,
      texto,
      c.index ?? 0,
      `un botón con "${c[1]}" dentro: el lector de pantalla lo lee como esa letra, usa un icono`
    );
  }

  // Formato de título: mayúscula en las palabras significativas y minúscula en
  // las funcionales. Se comprueba donde el texto es un título de verdad.
  for (const c of texto.matchAll(/\b(?:titulo|etiqueta)=["']([^"'{}]{4,60})["']/g)) {
    const problema = tituloMalFormado(c[1] ?? '');
    if (problema) {
      informar(archivo, texto, c.index ?? 0, `"${c[1]}": ${problema}`);
    }
  }

  // Ninguna acción exclusiva del ratón. Es criterio de aceptación de F1.6.4 y
  // de F1.4.6, no una recomendación: un gesto de puntero sin equivalente de
  // teclado deja fuera a quien no usa ratón, y el compilador de Svelte no lo ve
  // porque un `<div>` con `role` y `tabindex` le parece correcto.
  //
  // `onclick` no está en la lista: sobre un elemento nativamente enfocable lo
  // dispara también el teclado, y sobre uno que no lo es, el compilador ya
  // obliga a poner el manejador de teclado.
  //
  // Lo que la regla persigue es la **exclusividad**, no el evento. Un elemento
  // que además atiende el teclado ya ofrece las dos vías, y prohibirlo de todos
  // modos empujaría a inventar rodeos peores: fue el caso del doble clic para
  // abrir un libro, que tiene Enter como equivalente en el mismo botón.
  for (const c of texto.matchAll(/on(mousedown|mouseup|mousemove|dblclick|pointerdown|pointermove|drag[a-z]*|wheel)\s*=/g)) {
    if (tieneEquivalenteDeTeclado(texto, c.index ?? 0)) continue;
    informar(
      archivo,
      texto,
      c.index ?? 0,
      `on${c[1]}: es un gesto de puntero sin equivalente de teclado (F1.6.4)`
    );
  }

  // Varios puntos de referencia del mismo tipo sin nombre son indistinguibles
  // en la lista de zonas de un lector de pantalla.
  for (const c of texto.matchAll(/<(nav|aside)\b([^>]*)>/g)) {
    const atributos = c[2] ?? '';
    if (!/aria-label(?:ledby)?[=\s]/.test(atributos)) {
      informar(
        archivo,
        texto,
        c.index ?? 0,
        `<${c[1]}> sin aria-label ni aria-labelledby: la zona quedaría sin nombre`
      );
    }
  }
}

/* --- Los tokens que se usan tienen que existir -------------------------- *
 *
 * `var(--nb-radius-sm)` sin definir no falla en ninguna parte: el navegador
 * ignora la declaración y el control se queda sin redondear. Ocurrió de verdad
 * entre F1.6.2 y F1.6.14, y nadie lo notó en dos iteraciones porque no hay
 * error que mirar.
 *
 * Se comprueban también los del propio `app.css`: un token que se define en un
 * tema y se olvida en otro produce el mismo silencio, y solo lo sufre quien usa
 * el tema que lo perdió.
 */
const hojaBase = readFileSync(HOJA_BASE, 'utf8');

/** Tokens declarados en `app.css`, en cualquiera de sus bloques. */
const declarados = new Set(
  Array.from(hojaBase.matchAll(/^\s*(--nb-[a-z0-9-]+)\s*:/gm), (m) => m[1])
);

for (const archivo of recorrer(FUENTE)) {
  const crudo = readFileSync(archivo, 'utf8');
  const texto = sinComentarios(crudo);

  for (const { contenido, desplazamiento } of estilos(archivo, texto)) {
    // `var(--x, 60)` no falla en silencio: si el token no está, se usa el
    // respaldo. Solo se persigue el uso sin red.
    for (const uso of contenido.matchAll(/var\(\s*(--nb-[a-z0-9-]+)\s*([,)])/g)) {
      const token = uso[1];
      if (uso[2] === ',') continue;
      if (declarados.has(token)) continue;

      // Un token que el propio archivo declara antes de usarlo es suyo: los
      // componentes definen los que solo tienen sentido dentro de ellos.
      if (new RegExp(`${token}\\s*:`).test(contenido)) continue;
      // Y los que llegan por `style:` desde el marcado, igual.
      if (texto.includes(`style:${token}`)) continue;

      informar(
        archivo,
        texto,
        desplazamiento + (uso.index ?? 0),
        `${token} no está definido en app.css: la declaración se ignora en silencio`
      );
    }
  }
}

/* --- Clases que se pintan y que nadie viste --------------------------- *
 *
 * Una clase que aparece en el marcado y no tiene **ni una regla en todo el
 * proyecto** es, casi siempre, una regla que alguien borró sin querer. No es una
 * molestia estética: el 2026-08-31 desapareció la regla de `.nb-lienzo`, que era
 * el `overflow: auto` del contenedor de la biblioteca, y con ella la
 * virtualización entera. Nada falló, nada avisó; la vista simplemente pasó a
 * pedir ciento cincuenta mil tarjetas de una vez.
 *
 * Se busca en todos los archivos a la vez y no en cada uno: una clase puede
 * vestirse desde `app.css`, o desde otro componente con `:global()`, y las dos
 * cosas son legítimas.
 * -------------------------------------------------------------------- */

/** Clases que el marcado usa, por archivo. */
const enElMarcado = new Map();
/** Clases que alguna hoja viste, en cualquier sitio. */
const conRegla = new Set();

for (const archivo of recorrer(FUENTE)) {
  const texto = sinComentarios(readFileSync(archivo, 'utf8'));

  for (const { contenido } of estilos(archivo, texto)) {
    // Los selectores son lo que va antes de una llave de apertura. `:global(x)`
    // entra igual: por dentro lleva el mismo nombre de clase.
    for (const regla of contenido.matchAll(/(^|\})\s*([^{}@]+?)\s*\{/g)) {
      for (const clase of regla[2].matchAll(/\.(nb-[a-z0-9-]+)/g)) conRegla.add(clase[1]);
    }
  }

  if (extname(archivo) !== '.svelte') continue;
  const usadas = new Set();
  // `class="a b"`, `class="a {expr}"` y la forma condicional `class:nb-x={...}`.
  for (const atributo of texto.matchAll(/class=("|')([^"']*)\1/g)) {
    for (const clase of atributo[2].matchAll(/\b(nb-[a-z0-9-]+)\b/g)) usadas.add(clase[1]);
  }
  for (const directiva of texto.matchAll(/class:(nb-[a-z0-9-]+)/g)) usadas.add(directiva[1]);
  if (usadas.size > 0) enElMarcado.set(archivo, { usadas, texto });
}

for (const [archivo, { usadas, texto }] of enElMarcado) {
  for (const clase of usadas) {
    if (conRegla.has(clase)) continue;
    const donde = texto.indexOf(clase);
    informar(
      archivo,
      texto,
      donde < 0 ? 0 : donde,
      `.${clase} se pinta y no tiene ninguna regla: o sobra del marcado, o alguien borró su CSS`
    );
  }
}

/* --- Componentes del sistema de diseño sin usar (R1, F7.18) ------------- *
 *
 * Ningún componente del sistema de diseño puede existir sin una pantalla que
 * lo use. Un componente sin uso es código muerto que acumula coste de
 * mantenimiento y rompe la promesa de F5.4.3.
 *
 * Se comprueba que cada componente `.svelte` de `src/lib/ui/` tenga al menos un
 * consumidor fuera de sus propias pruebas y del archivo de reexportación (`index.ts`).
 * -------------------------------------------------------------------- */

const DIR_UI = join(FUENTE, 'lib', 'ui');
try {
  const componentesUi = readdirSync(DIR_UI)
    .filter((f) => f.endsWith('.svelte'))
    .map((f) => ({ archivo: join(DIR_UI, f), nombre: f.replace(/\.svelte$/, '') }));

  const todosLosFuentes = recorrerTodosLosFuentes(FUENTE);

  for (const { archivo, nombre } of componentesUi) {
    let tieneUso = false;
    const regexUso = new RegExp(`\\b${nombre}\\b`);

    for (const f of todosLosFuentes) {
      if (f === archivo) continue;
      if (f.endsWith('index.ts')) continue;
      if (f.includes('.test.') || f.includes('.spec.')) continue;
      const contenido = readFileSync(f, 'utf8');
      if (regexUso.test(contenido)) {
        tieneUso = true;
        break;
      }
    }

    if (!tieneUso) {
      const texto = readFileSync(archivo, 'utf8');
      informar(
        archivo,
        texto,
        0,
        `${nombre}.svelte: componente del sistema de diseño sin usar en ninguna pantalla (R1)`
      );
    }
  }
} catch {
  // Si no existe la carpeta (por ejemplo en pruebas con fixture acotado), se omite.
}

if (problemas.length > 0) {
  console.error(`Sistema de diseño: ${problemas.length} problema(s).\n`);
  for (const p of problemas) console.error(`  ${p}`);
  console.error('\nContrato: CLAUDE.md');
  process.exit(1);
}

console.log('Sistema de diseño: componentes conformes con ADR-008.');
