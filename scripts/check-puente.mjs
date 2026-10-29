#!/usr/bin/env node
/**
 * Comprobación de que el puente está entero y no le sobra nada.
 *
 * # Por qué existe
 *
 * Porque el mismo defecto apareció tres veces el 2026-09-01, y las tres veces
 * llevaba semanas ahí sin que nada fallara:
 *
 *   - **Enlazar notas.** `notes::link` nunca se expuso, así que la sintaxis
 *     `[[Título]]` que la interfaz llevaba prometiendo desde F1.7.1 no la
 *     implementaba nadie.
 *   - **Mudar la biblioteca.** `LibraryRoot::relocate` y
 *     `refresh_all_availability` resolvían F1.2.8 entera, probados en
 *     `tests/mudanza.rs`, sin un solo comando detrás: quien movía sus libros de
 *     disco veía la biblioteca fallar sin nada que pulsar.
 *   - **Exportar anotaciones.** `export_annotations` estaba en el puente y no lo
 *     llamaba nadie, así que el criterio de F1.4.5 se cumplía en una prueba y no
 *     en el producto, porque el archivo no se podía producir.
 *
 * Las tres iteraciones figuraban como **Hecha**. Ninguna prueba mentía: cada una
 * comprobaba su mitad, y lo que faltaba era justo lo que ninguna miraba, que es
 * si las dos mitades están unidas.
 *
 * # Qué comprueba
 *
 *   1. Todo comando registrado en `generate_handler!` tiene una función del
 *      puente que lo llama. Sin ella, la capacidad existe y no se puede usar.
 *   2. Toda función del puente llama a un comando registrado. Si no, falla en
 *      ejecución con un error del runtime que nadie sabe interpretar.
 *   3. Toda función del puente la usa alguien. Una que no usa nadie es
 *      superficie que el webview puede invocar sin que ningún camino de la
 *      aplicación la ejerza: ni se prueba, ni se traduce su fallo, ni se sabe si
 *      todavía funciona.
 *
 * La tercera admite excepciones, porque las hay legítimas; van en `SIN_USO_OK`
 * **con su motivo escrito**. Que añadir una cueste escribir por qué es
 * exactamente el punto: así se decide, en lugar de acumularse.
 *
 * Uso: node scripts/check-puente.mjs
 */

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { extname, join, relative, resolve } from 'node:path';

const ROOT = resolve(import.meta.dirname, '..');
const LIB_RS = join(ROOT, 'src-tauri/src/lib.rs');
// La capa de acceso es una **carpeta** desde F4.5.5: lo que solo usa un panel vive
// en su propio módulo para no entrar en el paquete de arranque. Se leen todos sus
// archivos, que es lo que hace que partirla no abra un hueco por el que colar un
// comando sin que nadie lo llame.
const PUENTE_DIR = join(ROOT, 'src/lib/core/ipc');
const INTERFAZ = [join(ROOT, 'src/routes'), join(ROOT, 'src/lib')];

/**
 * Funciones del puente que pueden no llamarse desde la interfaz, y por qué.
 *
 * Vacío a propósito. Lo que hoy no llama nadie está en la pregunta H4 de
 * `docs/contextual/open-questions/README.md` esperando una decisión: o se retira
 * el comando, que es un cambio de contrato, o se apunta aquí el motivo por el
 * que se queda. Mientras tanto no se apunta ninguno, para que la lista no se
 * convierta en el sitio donde se aparcan las decisiones que no se toman.
 */
const SIN_USO_OK = new Map();

/** @param {string} dir @returns {string[]} */
function recorrer(dir) {
  const salida = [];
  for (const entrada of readdirSync(dir)) {
    const completa = join(dir, entrada);
    if (statSync(completa).isDirectory()) salida.push(...recorrer(completa));
    else if (['.ts', '.svelte'].includes(extname(completa))) salida.push(completa);
  }
  return salida;
}

const problemas = [];

/* --- 1. Lo que el runtime registra -------------------------------------- */

const lib = readFileSync(LIB_RS, 'utf8');
const bloque = /generate_handler!\[([\s\S]*?)\]\)/.exec(lib);
if (!bloque) {
  console.error('No se encontró generate_handler! en src-tauri/src/lib.rs');
  process.exit(1);
}
const registrados = new Set(Array.from(bloque[1].matchAll(/(?:ipc|comandos)::(\w+)/g), (m) => m[1]));

/* --- 2. Lo que el puente ofrece ----------------------------------------- */

const puente = readdirSync(PUENTE_DIR)
  .filter((archivo) => archivo.endsWith('.ts') && !archivo.endsWith('.test.ts'))
  .map((archivo) => readFileSync(join(PUENTE_DIR, archivo), 'utf8'))
  .join('\n');

/**
 * Función del puente y comando al que llama.
 *
 * Se busca el `call<...>('comando')` que sigue a cada `export function`, y no en
 * todo el archivo: una función puede llamar a más de uno —guardar unas
 * anotaciones son un diálogo y una escritura— y lo que importa es que cada
 * comando registrado lo llame alguien, no cuántos llame cada función.
 */
const declaraciones = Array.from(
  puente.matchAll(/export (?:async )?function (\w+)[\s\S]*?(?=\nexport |\n\/\*\*|$)/g)
);
const invocados = new Set();
/** @type {Map<string, string[]>} */
const porFuncion = new Map();

for (const declaracion of declaraciones) {
  const nombre = declaracion[1];
  const comandos = Array.from(declaracion[0].matchAll(/call<[^>]*>\(\s*'(\w+)'/g), (m) => m[1]);
  // `call` es la puerta misma, no un envoltorio de un comando: recibe el nombre
  // como parámetro y la usan los otros archivos de la carpeta. Exigirle una
  // llamada desde la interfaz sería exigir que alguien invoque el puente a mano,
  // que es justo lo que la regla prohíbe.
  if (nombre === 'call') continue;
  porFuncion.set(nombre, comandos);
  for (const comando of comandos) invocados.add(comando);
}

for (const comando of registrados) {
  if (!invocados.has(comando)) {
    problemas.push(
      `${relative(ROOT, LIB_RS)}: el comando "${comando}" está registrado y ninguna función del puente lo llama: la capacidad existe y no se puede usar`
    );
  }
}

for (const [funcion, comandos] of porFuncion) {
  for (const comando of comandos) {
    // Los comandos de complemento (`plugin:...`) los sirve Tauri, no `ipc.rs`.
    if (comando.includes(':') || registrados.has(comando)) continue;
    problemas.push(
      `${relative(ROOT, PUENTE_DIR)}: "${funcion}" llama a "${comando}", que no está registrado en generate_handler!`
    );
  }
}

/* --- 3. Lo que la interfaz usa ------------------------------------------ */

const codigo = INTERFAZ.flatMap(recorrer)
  .filter((archivo) => !archivo.startsWith(PUENTE_DIR))
  .map((archivo) => readFileSync(archivo, 'utf8'))
  .join('\n');

for (const funcion of porFuncion.keys()) {
  if (SIN_USO_OK.has(funcion)) continue;
  if (new RegExp(`\\b${funcion}\\b`).test(codigo)) continue;
  problemas.push(
    `${relative(ROOT, PUENTE_DIR)}: "${funcion}" no la usa nadie: o se conecta, o se retira, o se apunta el motivo en SIN_USO_OK`
  );
}

if (problemas.length > 0) {
  console.error(`Puente: ${problemas.length} problema(s).\n`);
  for (const p of problemas) console.error(`  ${p}`);
  console.error('\nContrato: CLAUDE.md');
  process.exit(1);
}

console.log(
  `Puente: ${registrados.size} comandos, todos con función y todos usados desde la interfaz.`
);
