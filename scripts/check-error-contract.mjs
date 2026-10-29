#!/usr/bin/env node
/**
 * Comprobación del contrato de errores del runtime.
 *
 * La regla es que ningún error cruce una frontera como cadena de texto: el
 * runtime devuelve `NsResult`, cuyo error serializa un código canónico estable
 * que el frontend traduce. Un `Result<_, String>` rompe eso en silencio: compila,
 * pasa los lints y llega al usuario como un mensaje en inglés, sin traducir y
 * con el riesgo de filtrar rutas o detalles de una biblioteca de terceros.
 *
 * Hasta ahora la regla vivía solo en la disciplina de quien programa. Esto la
 * hace comprobable. Se ejecuta en `pnpm verify` y en el gancho de pre-commit.
 *
 * Uso: node scripts/check-error-contract.mjs
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

const ROOT = resolve(import.meta.dirname, '..');
const FUENTES = join(ROOT, 'src-tauri', 'src');

/**
 * Firmas que devuelven `String` como tipo de error.
 *
 * Cubre tanto `Result<T, String>` como su forma cualificada. El tipo de éxito
 * puede contener comas y genéricos anidados, de ahí la parte perezosa.
 */
const ERROR_COMO_CADENA = /->\s*(?:std::result::)?Result\s*<[^;{]*?,\s*String\s*>/g;

/** Una excepción justificada se marca en la línea anterior con este comentario. */
const EXCEPCION = '// check-error-contract: allow-string';

/** @param {string} dir @returns {string[]} */
function recorrer(dir) {
  const salida = [];
  for (const entrada of readdirSync(dir)) {
    const completa = join(dir, entrada);
    if (statSync(completa).isDirectory()) salida.push(...recorrer(completa));
    else if (entrada.endsWith('.rs')) salida.push(completa);
  }
  return salida;
}

const problemas = [];

for (const archivo of recorrer(FUENTES)) {
  const texto = readFileSync(archivo, 'utf8');
  const lineas = texto.split('\n');

  for (const coincidencia of texto.matchAll(ERROR_COMO_CADENA)) {
    const numero = texto.slice(0, coincidencia.index).split('\n').length;
    const anterior = lineas[numero - 2] ?? '';
    if (anterior.includes(EXCEPCION)) continue;
    problemas.push(`${relative(ROOT, archivo)}:${numero}: ${coincidencia[0].trim()}`);
  }
}

if (problemas.length > 0) {
  console.error('\nContrato de errores: ningún error puede viajar como cadena.\n');
  for (const p of problemas) console.error(`  ${p}`);
  console.error(
    `\nUsa NsResult<T> y una variante de NsError con su código canónico.\n` +
      `Ver CLAUDE.md\n`
  );
  process.exit(1);
}

console.log('Contrato de errores: ninguna firma devuelve String como error.');
