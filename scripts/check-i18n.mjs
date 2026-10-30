/**
 * Portado de NB Books (su F1.7.1): un lint rechaza cualquier texto
 * visible incrustado en el marcado.
 *
 * # Por qué hace falta un script y no basta la disciplina
 *
 * Porque el texto incrustado no falla. La aplicación funciona, se ve bien y
 * pasa todas las pruebas; simplemente hay una frase que nunca se traduce, y
 * quien la descubre es alguien que no lee español y se encuentra media pantalla
 * en un idioma que no entiende. Es exactamente la clase de defecto que solo se
 * detecta si hay una máquina buscándolo.
 *
 * # Qué mira
 *
 * 1. **Los nodos de texto del marcado.** Fuera de `<script>`, de `<style>` y de
 *    los comentarios, todo lo que se vea tiene que venir de una expresión.
 * 2. **Los atributos que el usuario lee u oye.** `aria-label` es texto visible
 *    aunque no se vea: lo dice el lector de pantalla, y dejarlo sin traducir
 *    castiga justo a quien más depende de él.
 *
 * # Qué no mira, y por qué
 *
 * Los diccionarios de `src/lib/i18n/`, que son texto por definición, y
 * los archivos `.ts`, donde una cadena no llega sola a la pantalla: pasa por un
 * componente, y ahí es donde se comprueba. Tampoco mira una entidad suelta ni
 * un signo de puntuación: `·`, `/` y `—` no se traducen.
 *
 * # La salida de emergencia
 *
 * `check-i18n: no es texto` dentro del comentario que precede al elemento.
 * Existe porque hay casos legítimos —una muestra tipográfica, un identificador
 * técnico— y porque una regla sin salida se acaba desactivando entera. El
 * comentario tiene que explicar por qué, y solo exime a lo que va pegado a él.
 */

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { extname, join, relative, resolve } from 'node:path';

const ROOT = resolve(import.meta.dirname, '..');
const FUENTE = join(ROOT, 'src');

/** La marca que exime a lo que venga justo después del comentario. */
const EXCEPCION = 'check-i18n: no es texto';

/**
 * Atributos cuyo valor lee u oye una persona.
 *
 * `title` y `alt` están por lo mismo que `aria-label`: no se ven en la pantalla
 * pero sí se leen en voz alta o al posar el puntero.
 */
const ATRIBUTOS_VISIBLES = [
  'etiqueta',
  'titulo',
  'mensaje',
  'descripcion',
  'aria-label',
  'aria-description',
  'aria-placeholder',
  'aria-roledescription',
  'aria-valuetext',
  'placeholder',
  'title',
  'alt'
];

function recorrer(dir) {
  const salida = [];
  for (const entrada of readdirSync(dir)) {
    const completa = join(dir, entrada);
    if (statSync(completa).isDirectory()) salida.push(...recorrer(completa));
    else salida.push(completa);
  }
  return salida;
}

const problemas = [];

function linea(texto, indice) {
  return texto.slice(0, indice).split('\n').length;
}

/**
 * Si lo que hay justo antes es un comentario que exime este hallazgo.
 *
 * Se busca **el comentario anterior entero**, no unas cuantas líneas: una
 * excepción tiene que poder explicarse, y explicarse ocupa lo que ocupe. Con una
 * ventana de líneas fijas, el comentario largo dejaba de contar justo cuando más
 * falta hacía.
 *
 * Solo cuenta si el comentario está pegado: entre él y el hallazgo no puede
 * haber más que espacios y una etiqueta de apertura. Si no, la marca de una
 * excepción antigua eximiría texto nuevo escrito debajo sin que nadie lo note.
 */
function exento(texto, indice) {
  const antes = texto.slice(0, indice);
  const cierre = antes.lastIndexOf('-->');
  if (cierre < 0) return false;

  const apertura = antes.lastIndexOf('<!--', cierre);
  if (apertura < 0) return false;

  // Entre el comentario y el hallazgo solo puede haber espacios y la etiqueta
  // que abre el elemento.
  const entre = antes.slice(cierre + 3);
  if (/<\/|-->/.test(entre)) return false;
  if (entre.replace(/<[^<>]*>?/g, '').trim().length > 0) return false;

  return antes.slice(apertura, cierre).includes(EXCEPCION);
}

function informar(archivo, texto, indice, mensaje) {
  if (exento(texto, indice)) return;
  problemas.push(`${relative(ROOT, archivo)}:${linea(texto, indice)}  ${mensaje}`);
}

/**
 * Sustituye una región por espacios, conservando los saltos de línea.
 *
 * Se sustituye en lugar de borrar para que los desplazamientos sigan
 * correspondiendo con el archivo original: si no, el número de línea del aviso
 * apuntaría a otro sitio y buscarlo costaría más que arreglarlo.
 */
function vaciar(texto, desde, hasta) {
  const region = texto.slice(desde, hasta).replace(/[^\n]/g, ' ');
  return texto.slice(0, desde) + region + texto.slice(hasta);
}

/** Quita los bloques que no son marcado: script, estilo y comentarios. */
function soloMarcado(texto) {
  let salida = texto;
  const bloques = /<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>|<!--[\s\S]*?-->/g;
  for (const encontrado of texto.matchAll(bloques)) {
    const desde = encontrado.index ?? 0;
    salida = vaciar(salida, desde, desde + encontrado[0].length);
  }
  return salida;
}

/**
 * Quita las expresiones `{...}`, que es de donde tiene que salir el texto.
 *
 * Cuenta llaves para respetar el anidamiento: `{a ? {b} : c}` es una sola
 * expresión, y tratarla como dos dejaría suelto un trozo que parece texto.
 */
/**
 * El código sin comentarios, conservando las posiciones.
 *
 * Se sustituye por espacios en lugar de recortar para que el número de línea que
 * se informa siga siendo el del archivo de verdad. Hace falta porque en los
 * comentarios se explica qué no hacer, y nombrar un defecto no es cometerlo.
 */
function sinComentarios(texto) {
  return texto.replace(/\/\*[\s\S]*?\*\/|\/\/[^\n]*/g, (trozo) =>
    trozo.replace(/[^\n]/g, ' ')
  );
}

function sinExpresiones(texto) {
  let salida = texto;
  let profundidad = 0;
  let inicio = 0;

  for (let i = 0; i < texto.length; i += 1) {
    if (texto[i] === '{') {
      if (profundidad === 0) inicio = i;
      profundidad += 1;
    } else if (texto[i] === '}' && profundidad > 0) {
      profundidad -= 1;
      if (profundidad === 0) salida = vaciar(salida, inicio, i + 1);
    }
  }
  return salida;
}

/**
 * Si un fragmento es texto de verdad.
 *
 * Hacen falta dos letras seguidas: un separador (`·`), una barra, un guion o
 * una unidad suelta no se traducen, y avisar de ellos enseñaría a ignorar el
 * lint, que es la forma más rápida de que deje de servir.
 */
function pareceTexto(fragmento) {
  const limpio = fragmento.replace(/&[a-z]+;|&#\d+;/gi, ' ').trim();
  return /[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}/.test(limpio);
}

for (const archivo of recorrer(FUENTE)) {
  if (extname(archivo) !== '.svelte') continue;

  const original = readFileSync(archivo, 'utf8');
  const marcado = sinExpresiones(soloMarcado(original));

  // 1. Nodos de texto: lo que queda entre una etiqueta que cierra y otra que
  //    abre. Si tiene letras, es una frase que alguien va a leer.
  for (const encontrado of marcado.matchAll(/>([^<>]+)</g)) {
    const contenido = encontrado[1] ?? '';
    if (!pareceTexto(contenido)) continue;
    const desplazamiento = (encontrado.index ?? 0) + 1;
    informar(
      archivo,
      original,
      desplazamiento,
      `texto incrustado "${contenido.trim().slice(0, 45)}": tiene que venir de $lib/i18n`
    );
  }

  // 2. Atributos que se leen o se oyen, con valor literal.
  const atributos = new RegExp(`\\b(${ATRIBUTOS_VISIBLES.join('|')})=(["'])([^"']*)\\2`, 'g');
  for (const encontrado of marcado.matchAll(atributos)) {
    const valor = encontrado[3] ?? '';
    if (!pareceTexto(valor)) continue;
    informar(
      archivo,
      original,
      encontrado.index ?? 0,
      `${encontrado[1]}="${valor.slice(0, 45)}": un atributo que se lee también se traduce`
    );
  }
}

/*
 * Ningún formato se toma del idioma **del sistema**.
 *
 * `toLocaleDateString()` sin argumento usa el del navegador, no el de la
 * aplicación: en un escritorio en inglés escribe `9/2/2026` dentro de una
 * interfaz en español, donde ese mismo texto significa el 9 de febrero. Y no es
 * hipotético: la biblioteca ya lo había corregido para las cifras y Estudio
 * seguía formateando las fechas con el del sistema, así que el criterio existía
 * y se aplicaba en la mitad de los sitios.
 *
 * Lo mismo vale para `Intl.*` construido sin locale. La forma correcta es
 * pasarle `idioma()`, que es lo que la persona eligió.
 */
const FORMATO_DEL_SISTEMA =
  /\.(toLocaleDateString|toLocaleTimeString|toLocaleString)\(\s*\)|new Intl\.(DateTimeFormat|NumberFormat|Collator|DisplayNames|ListFormat|RelativeTimeFormat)\(\s*\)/g;

for (const archivo of recorrer(FUENTE)) {
  if (!/\.(svelte|ts)$/.test(archivo) || archivo.includes('.test.')) continue;
  const original = readFileSync(archivo, 'utf8');
  // Sin comentarios: aquí se explica el defecto y nombrarlo no es cometerlo.
  const codigo = sinComentarios(original);

  for (const encontrado of codigo.matchAll(FORMATO_DEL_SISTEMA)) {
    informar(
      archivo,
      original,
      encontrado.index ?? 0,
      `${encontrado[0].trim()}: el formato sale del idioma del sistema, no del de la interfaz. Pásale idioma()`
    );
  }
}

if (problemas.length > 0) {
  console.error(`\nTextos sin externalizar: ${problemas.length} problema(s)\n`);
  for (const problema of problemas) console.error(`  ${problema}`);
  console.error('\nContrato: src/lib/i18n/es.ts');
  process.exit(1);
}

console.log('Textos de la interfaz: todos salen del diccionario.');
