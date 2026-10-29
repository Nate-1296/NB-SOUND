#!/usr/bin/env node
/**
 * Ningún registro lleva rutas, títulos ni texto del usuario sin redactar (F7.15).
 *
 * # Por qué existe
 *
 * El innegociable de `CLAUDE.md` -"ningún registro contiene rutas, nombres de
 * usuario ni títulos de documento"- tenía la mitad de su mecanismo: la prueba de
 * humo mira el registro real del binario, pero **nada obligaba a pasar por
 * `redact_path` o `redact_text`**. Una línea nueva con `ruta = %ruta` compilaba,
 * pasaba la suite y escribía en el disco del usuario dónde guarda sus libros.
 *
 * # Qué comprueba
 *
 * Cada invocación de `trace!`, `debug!`, `info!`, `warn!`, `error!` y `event!` en
 * `src-tauri/src`, campo a campo. Un campo cuyo nombre o cuyo valor nombra algo que suele ser del
 * usuario -una ruta, un título, un autor, una consulta, un texto, una URL- tiene que:
 *
 *   * pasar por `redact_path(` o `redact_text(`, o
 *   * ser una medida y no el dato: `.len()`, `.count()`, `.is_empty()`...
 *   * o declarar por qué no es del usuario con un comentario `// no es del usuario:`
 *     dentro de la propia invocación, que es lo que se revisa al leer el cambio.
 *
 * # Lo que no puede ver, y por eso no se afirma
 *
 * El contenido de un error que se registra con `error = %error`: si un error lleva
 * dentro una ruta, esto no lo sabe. Tampoco un valor del usuario guardado en una
 * variable con un nombre que no lo delata. Lo que sí cubre es la forma habitual en
 * que eso entra, que es nombrarlo.
 *
 * Uso: node scripts/check-registro.mjs
 */

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

const RAIZ = resolve(import.meta.dirname, '..');
const FUENTES = join(RAIZ, 'src-tauri', 'src');

/** Lo que suele ser del usuario cuando da nombre a un valor. */
const SOSPECHOSO =
  /(?:^|[^a-z0-9])(ruta|rutas|path|paths|titulo|titulos|title|autor|autores|author|authors|consulta|query|cita|fragmento|texto|text|contenido|cuerpo|body|palabra|url|carpeta|directorio|archivo|file_name|filename|nombre_de_archivo)(?:$|[^a-z0-9])/i;

/** Lo que convierte el dato en una medida del dato. */
const MEDIDA =
  /\.(len|count|is_empty|is_some|is_none|as_millis|as_secs|as_secs_f64|as_micros|extension)\(\)\)*\s*$/;

const MACRO = /\b(?:tracing::)?(trace|debug|info|warn|error|event)!\s*\(/g;

function listar(dir) {
  return readdirSync(dir).flatMap((nombre) => {
    const ruta = join(dir, nombre);
    return statSync(ruta).isDirectory() ? listar(ruta) : ruta.endsWith('.rs') ? [ruta] : [];
  });
}

/** El texto entre el paréntesis que abre en `desde` y el que lo cierra. */
function argumentos(codigo, desde) {
  let nivel = 0;
  let enCadena = false;
  let bruta = false;
  for (let i = desde; i < codigo.length; i += 1) {
    const c = codigo[i];
    if (enCadena) {
      if (!bruta && c === '\\') i += 1;
      else if (c === '"' && (!bruta || codigo[i + 1] !== '#')) enCadena = false;
      continue;
    }
    if (c === '"') {
      enCadena = true;
      bruta = codigo[i - 1] === '#' || codigo[i - 1] === 'r';
    } else if (c === '(' || c === '[' || c === '{') nivel += 1;
    else if (c === ')' || c === ']' || c === '}') {
      nivel -= 1;
      if (nivel === 0) return codigo.slice(desde + 1, i);
    }
  }
  return '';
}

/** Parte por las comas de primer nivel, sin entrar en cadenas ni en llamadas. */
function partir(texto) {
  const partes = [];
  let nivel = 0;
  let enCadena = false;
  let actual = '';
  for (let i = 0; i < texto.length; i += 1) {
    const c = texto[i];
    if (enCadena) {
      actual += c;
      if (c === '\\') {
        actual += texto[i + 1] ?? '';
        i += 1;
      } else if (c === '"') enCadena = false;
      continue;
    }
    if (c === '"') enCadena = true;
    if (c === '(' || c === '[' || c === '{') nivel += 1;
    if (c === ')' || c === ']' || c === '}') nivel -= 1;
    if (c === ',' && nivel === 0) {
      partes.push(actual);
      actual = '';
    } else actual += c;
  }
  if (actual.trim()) partes.push(actual);
  return partes;
}

const sinComentarios = (texto) => texto.replace(/\/\/[^\n]*/g, '').trim();

const fallos = [];
let invocaciones = 0;
for (const archivo of listar(FUENTES)) {
  const codigo = readFileSync(archivo, 'utf8');
  for (const encontrada of codigo.matchAll(MACRO)) {
    invocaciones += 1;
    const inicio = encontrada.index + encontrada[0].length - 1;
    const args = argumentos(codigo, inicio);
    if (/\/\/\s*no es del usuario:/.test(args)) continue;
    const linea = codigo.slice(0, encontrada.index).split('\n').length;
    for (const parte of partir(args)) {
      const limpia = sinComentarios(parte);
      if (limpia.startsWith('"') || limpia.startsWith('r"') || limpia.startsWith('r#"')) continue;
      // `campo = valor`, `%valor`, `?valor` o el atajo `valor`. Delata tanto el
      // nombre del campo como el del valor: `ruta = %destino.display()` es una ruta.
      const conNombre = limpia.includes('=') && !limpia.includes('==');
      const campo = conNombre ? limpia.slice(0, limpia.indexOf('=')).trim() : '';
      const valor = (conNombre ? limpia.slice(limpia.indexOf('=') + 1) : limpia)
        .trim()
        .replace(/^[%?]/, '');
      if (!SOSPECHOSO.test(valor) && !SOSPECHOSO.test(campo)) continue;
      if (/redact_(path|text)\(/.test(valor)) continue;
      if (MEDIDA.test(valor)) continue;
      fallos.push(`${relative(RAIZ, archivo)}:${linea}  ${limpia.replace(/\s+/g, ' ')}`);
    }
  }
}

if (fallos.length > 0) {
  console.error(
    'check-registro: hay campos de registro que pueden llevar datos del usuario sin redactar.\n'
  );
  for (const fallo of fallos) console.error(`  ${fallo}`);
  console.error(
    '\n  Pásalos por redact_path o redact_text, registra su medida (.len()), o di dentro de la invocación' +
      '\n  por qué no son del usuario con "// no es del usuario: <motivo>".'
  );
  process.exit(1);
}
console.log(`Registro: ${invocaciones} invocaciones, ningún dato del usuario sin redactar.`);
