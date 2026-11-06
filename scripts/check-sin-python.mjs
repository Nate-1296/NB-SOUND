#!/usr/bin/env node
/**
 * Ningún Python en NB Sound.
 *
 * ADR-002 decide que NB Sound no ejecuta un intérprete de Python. Esto lo hace
 * comprobable: falla si aparece un archivo `.py`, un `requirements*.txt`, un
 * `pyproject.toml` o un `.qml`, y si el runtime de Rust lanza un
 * intérprete.
 *
 * No se admite ninguno en ningún sitio: ni excepciones por carpeta ni prototipos.
 *
 * Uso: node scripts/check-sin-python.mjs
 */

import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const ROOT = resolve(import.meta.dirname, '..');
const PYTHON = /(^|\/)(requirements[^/]*\.txt|pyproject\.toml|[^/]+\.py|[^/]+\.qml)$/;
const LANZA_INTERPRETE = /Command::new\(\s*"(python3?|py|pip3?|uv)"/;

const archivos = spawnSync('git', ['ls-files', '--cached', '--others', '--exclude-standard'], {
  cwd: ROOT,
  encoding: 'utf8'
})
  .stdout.split('\n')
  .filter(Boolean);

const problemas = [];
for (const archivo of archivos) {
  if (PYTHON.test(archivo)) problemas.push(`${archivo}: archivo de Python o de QML`);
  if (archivo.startsWith('src-tauri/src/') && archivo.endsWith('.rs')) {
    if (LANZA_INTERPRETE.test(readFileSync(resolve(ROOT, archivo), 'utf8'))) {
      problemas.push(`${archivo}: lanza un intérprete de Python`);
    }
  }
}

if (problemas.length > 0) {
  console.error('\nNB Sound no ejecuta Python (ADR-002):\n');
  for (const p of problemas) console.error(`  ${p}`);
  console.error('');
  process.exit(1);
}

console.log('Sin Python: NB Sound no trae ni lanza ningún intérprete.');
