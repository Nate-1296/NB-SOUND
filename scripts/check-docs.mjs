#!/usr/bin/env node
/**
 * Verificación de integridad de la documentación.
 *
 * Existe porque el 27 % del corpus llegó a estar duplicado o vacío sin que nadie
 * lo notara. La Constitución trata la documentación con el mismo rigor que el
 * código; esto es lo que hace cumplible esa regla.
 *
 * Comprueba:
 *   1. Enlaces internos rotos
 *   2. Archivos vacíos
 *   3. Documentos duplicados (mismo contenido en rutas distintas)
 *   4. Emoticonos
 *   5. Rutas absolutas de una máquina concreta
 *   6. Documentos sin título de primer nivel
 *   7. Filas de tabla que se han tragado el bloque siguiente
 *
 * La sexta comprobación existe por un motivo concreto: durante la Fase 0, un
 * editor con búferes obsoletos sobrescribió varios documentos y les quitó el
 * encabezado. La corrupción pasó desapercibida dos veces porque ninguna
 * comprobación miraba la estructura, solo el contenido.
 *
 * La séptima, por otro igual de concreto: el 2026-08-27 se encontraron cuarenta
 * líneas en las que la última fila de una tabla había absorbido el encabezado,
 * el párrafo o la línea horizontal que venían detrás, por un salto de línea
 * perdido. Al renderizar, ese encabezado desaparece dentro de una celda. Ninguna
 * de las seis comprobaciones anteriores lo veía porque el archivo no estaba
 * vacío, ni truncado, ni duplicado: estaba mal.
 *
 * Uso: node scripts/check-docs.mjs
 */

import { createHash } from 'node:crypto';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';

const ROOT = resolve(import.meta.dirname, '..');
const ROOT_DOCS = ['README.md', 'CLAUDE.md', 'CONTRIBUTING.md', 'CODE_OF_CONDUCT.md', 'SECURITY.md'];

const EMOJI = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{23F0}-\u{23FF}\u{FE0F}]/u;
const ABSOLUTE_PATH = /(?:file:\/\/\/|\/home\/[a-z]|[A-Z]:\\Users\\)/;

/** @param {string} dir @returns {string[]} */
function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      out.push(...walk(full));
    } else if (entry.endsWith('.md')) {
      out.push(full);
    }
  }
  return out;
}

// `docs/v1/` es la documentación archivada de la V1 (ADR-011): no gobierna nada y
// se borra en la Fase 7, así que no se le exigen las reglas de la V2.
const ARCHIVADA = join(ROOT, 'docs', 'v1');

const files = [
  ...walk(join(ROOT, 'docs')).filter((f) => !f.startsWith(ARCHIVADA)),
  ...ROOT_DOCS.map((f) => join(ROOT, f))
];

/** @type {string[]} */
const problems = [];
/** @type {Map<string, string[]>} */
const hashes = new Map();

for (const file of files) {
  const rel = relative(ROOT, file);
  const text = readFileSync(file, 'utf8');

  if (text.trim().length === 0) {
    problems.push(`${rel}: archivo vacío`);
    continue;
  }

  const hash = createHash('sha256').update(text).digest('hex');
  hashes.set(hash, [...(hashes.get(hash) ?? []), rel]);

  // Todo documento empieza con un título de primer nivel. Su ausencia casi
  // siempre significa que el archivo se truncó o se sobrescribió, no que
  // alguien decidiera omitirlo.
  const primeraLinea = text.split('\n').find((l) => l.trim().length > 0) ?? '';
  if (!primeraLinea.startsWith('# ')) {
    problems.push(`${rel}: no empieza con un título de primer nivel (posible truncamiento)`);
  }

  // Una fila de tabla termina en `|`. Si no lo hace, lo que va detrás es un
  // bloque distinto al que se le ha perdido el salto de línea, y al renderizar
  // se convierte en parte de la última celda.
  const lineas = text.split('\n');
  for (const [i, linea] of lineas.entries()) {
    if (linea.startsWith('|') && linea.trim().length > 0 && !linea.trimEnd().endsWith('|')) {
      const tragado = linea.slice(linea.trimEnd().lastIndexOf('|') + 1).trim();
      problems.push(
        `${rel}:${i + 1}: una fila de tabla se ha tragado el bloque siguiente -> ${tragado.slice(0, 60)}`
      );
    }
  }

  if (EMOJI.test(text)) {
    problems.push(`${rel}: contiene emoticonos (docs/README.md, principios)`);
  }

  // Un documento puede necesitar mostrar una ruta absoluta como ejemplo de lo
  // que está prohibido. Ese caso se marca explícitamente en el propio archivo.
  const allowsAbsolute = text.includes('<!-- check-docs: allow-absolute-path -->');
  const absolute = allowsAbsolute ? null : text.match(ABSOLUTE_PATH);
  if (absolute) {
    problems.push(`${rel}: contiene una ruta absoluta de una máquina concreta (${absolute[0]})`);
  }

  for (const [, target] of text.matchAll(/\]\(([^)\s]+)\)/g)) {
    if (/^(https?:|#|mailto:)/.test(target)) continue;
    const path = decodeURIComponent(target.split('#')[0]);
    if (!path) continue;
    try {
      statSync(resolve(dirname(file), path));
    } catch {
      problems.push(`${rel}: enlace roto -> ${target}`);
    }
  }
}

for (const [, paths] of hashes) {
  if (paths.length > 1) {
    problems.push(`documentos duplicados: ${paths.join(', ')}`);
  }
}

if (problems.length > 0) {
  console.error(`\nIntegridad de la documentación: ${problems.length} problema(s)\n`);
  for (const p of problems) console.error(`  ${p}`);
  console.error('');
  process.exit(1);
}

console.log(`Integridad de la documentación: ${files.length} documentos, sin problemas.`);
