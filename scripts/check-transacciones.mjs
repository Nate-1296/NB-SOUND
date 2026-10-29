#!/usr/bin/env node
/**
 * Rechaza toda transacción de escritura que se abra diferida.
 *
 * # Por qué existe
 *
 * En modo WAL, una transacción diferida que empieza leyendo y **después**
 * escribe tiene que ascender su bloqueo de lectura a bloqueo de escritura, y si
 * otro escritor confirmó algo entre medias SQLite devuelve `SQLITE_BUSY` **de
 * inmediato y sin respetar `busy_timeout`**, porque reintentar dentro de la
 * misma transacción daría una lectura incoherente.
 *
 * Esto ya pasó una vez, se arregló en F1.2.3 y `storage.md` lo daba por
 * resuelto: 12.156 «database is locked» en una sola sesión, y los títulos
 * quedándose con el nombre del archivo porque los metadatos no llegaban a
 * aplicarse. **Y volvió a entrar**: `boards.rs` abría un `BEGIN` a secas, que es
 * `BEGIN DEFERRED`, y la importación real del 2026-09-09 perdió **1.207
 * documentos** con `STORAGE_FAILURE`.
 *
 * Una regla que ya se incumplió una vez, y que no se ve al leer el código
 * -`BEGIN` parece completo-, es exactamente la que necesita un mecanismo.
 *
 * # Qué comprueba
 *
 * Que en el runtime no haya:
 *
 * 1. Ningún `BEGIN` en una cadena SQL que no sea `BEGIN IMMEDIATE`. Incluye
 *    `BEGIN`, `BEGIN TRANSACTION` y `BEGIN DEFERRED`, que son lo mismo.
 * 2. Ninguna llamada a `.transaction()`, que en rusqlite abre diferida por
 *    omisión. Lo que vale es `db::write_transaction`, que es el único sitio
 *    donde se escribe `Immediate`.
 *
 * # Lo que no comprueba, dicho como tal
 *
 * No entiende Rust: mira texto, como `check-plataforma.mjs`. Una transacción
 * abierta desde SQL construido en tiempo de ejecución se le escaparía. Lo que
 * caza es la forma en la que el defecto entró las dos veces.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

const RAIZ = resolve(import.meta.dirname, '..');
const FUENTES = process.argv[2] ? process.argv[2] : join(RAIZ, 'src-tauri', 'src');

/** Lo que abre una transacción sin tomar el bloqueo de escritura. */
const DIFERIDAS = [
  { patron: /"\s*BEGIN\s*"/i, que: 'un `BEGIN` a secas, que es `BEGIN DEFERRED`' },
  { patron: /"\s*BEGIN\s+TRANSACTION/i, que: '`BEGIN TRANSACTION`, que es diferida' },
  { patron: /"\s*BEGIN\s+DEFERRED/i, que: '`BEGIN DEFERRED`' },
  { patron: /\.transaction\s*\(\s*\)/, que: '`.transaction()`, que rusqlite abre diferida' }
];

/**
 * El único sitio donde se decide el comportamiento de las transacciones.
 *
 * Ahí sí se nombra `Immediate` y se explica por qué; vigilarlo a él mismo sería
 * pedirle que no diga lo que existe para decir.
 */
const LA_PUERTA = join('src-tauri', 'src', 'db', 'mod.rs');

function archivosRust(directorio) {
  const encontrados = [];
  for (const entrada of readdirSync(directorio)) {
    const ruta = join(directorio, entrada);
    if (statSync(ruta).isDirectory()) encontrados.push(...archivosRust(ruta));
    else if (entrada.endsWith('.rs')) encontrados.push(ruta);
  }
  return encontrados;
}

const archivos = archivosRust(FUENTES);
const problemas = [];
let vistas = 0;

for (const archivo of archivos) {
  const relativo = relative(RAIZ, archivo);
  const lineas = readFileSync(archivo, 'utf8').split('\n');

  for (const [i, linea] of lineas.entries()) {
    // Los comentarios explican el problema, no lo cometen.
    const limpia = linea.trimStart();
    if (limpia.startsWith('//') || limpia.startsWith('*')) continue;

    if (/\bIMMEDIATE\b/i.test(linea) || /write_transaction/.test(linea)) vistas += 1;
    if (relativo === LA_PUERTA) continue;

    for (const { patron, que } of DIFERIDAS) {
      if (!patron.test(linea)) continue;
      problemas.push(`  ${relativo}:${i + 1}  abre ${que}\n    ${linea.trim()}`);
    }
  }
}

// Un guardián que deja de encontrar lo que vigila da por bueno lo que ya no
// mira. Si nadie abre transacciones de escritura, o esto se quedó apuntando al
// directorio que no es, más vale saberlo.
if (vistas === 0) {
  console.error(`No se encontró ninguna transacción de escritura en ${FUENTES}.`);
  console.error(
    'O la ruta es la que no es, o las transacciones se abren de otra forma y esto\n' +
      'dejó de comprobarlas.'
  );
  process.exit(1);
}

if (problemas.length > 0) {
  console.error('Hay transacciones de escritura abiertas en diferido:\n');
  console.error(problemas.join('\n'));
  console.error(
    '\nEn WAL, una transacción diferida que lee y después escribe recibe SQLITE_BUSY\n' +
      'de inmediato y sin respetar `busy_timeout`. Pasó dos veces: 12.156 bloqueos en\n' +
      'F1.2.3 y 1.207 documentos perdidos en la importación real. Se abre con\n' +
      '`db::write_transaction`, que toma el bloqueo desde la primera instrucción.'
  );
  process.exit(1);
}

console.log(
  `Transacciones: ${archivos.length} archivos de Rust, ninguna de escritura abierta en diferido.`
);
