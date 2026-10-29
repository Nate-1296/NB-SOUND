#!/usr/bin/env node
/**
 * Ningún Python en la V2.
 *
 * ADR-002 decide que la V2 no ejecuta un intérprete de Python. Esto lo hace
 * comprobable: falla si aparece un archivo `.py`, un `requirements*.txt` o un
 * `pyproject.toml` fuera de los dos sitios donde se admiten, y si el runtime de
 * Rust lanza un intérprete.
 *
 * Excepciones, con su motivo:
 *   - `legado/`: la V1 congelada (ADR-011), que se borra en la Fase 7.
 *   - `scripts/prototipos/`: los prototipos de la Fase 0 que convierten modelos o
 *     miden la paridad contra la V1. Son herramientas de desarrollo, nunca viajan
 *     en el instalador.
 *
 * Uso: node scripts/check-sin-python.mjs
 */

import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const ROOT = resolve(import.meta.dirname, '..');
const PERMITIDOS = ['legado/', 'scripts/prototipos/'];
const PYTHON = /(^|\/)(requirements[^/]*\.txt|pyproject\.toml|[^/]+\.py)$/;
const LANZA_INTERPRETE = /Command::new\(\s*"(python3?|py|pip3?|uv)"/;

const archivos = spawnSync('git', ['ls-files', '--cached', '--others', '--exclude-standard'], {
  cwd: ROOT,
  encoding: 'utf8'
})
  .stdout.split('\n')
  .filter(Boolean);

const problemas = [];
for (const archivo of archivos) {
  if (PERMITIDOS.some((p) => archivo.startsWith(p))) continue;
  if (PYTHON.test(archivo)) problemas.push(`${archivo}: archivo de Python fuera de legado/`);
  if (archivo.startsWith('src-tauri/src/') && archivo.endsWith('.rs')) {
    if (LANZA_INTERPRETE.test(readFileSync(resolve(ROOT, archivo), 'utf8'))) {
      problemas.push(`${archivo}: lanza un intérprete de Python`);
    }
  }
}

if (problemas.length > 0) {
  console.error('\nLa V2 no ejecuta Python (ADR-002):\n');
  for (const p of problemas) console.error(`  ${p}`);
  console.error('');
  process.exit(1);
}

console.log('Sin Python: la V2 no trae ni lanza ningún intérprete.');
