#!/usr/bin/env node
/**
 * Ningún Python en la V2.
 *
 * ADR-002 decide que la V2 no ejecuta un intérprete de Python. Esto lo hace
 * comprobable: falla si aparece un archivo `.py`, un `requirements*.txt`, un
 * `pyproject.toml` o un `.qml` de la V1, y si el runtime de Rust lanza un
 * intérprete.
 *
 * Hasta la Fase 7 admitía la V1 congelada en `legado/` y los prototipos de Python
 * de `scripts/prototipos/`. Al retirarse la V1 (F7.1.2) esas excepciones dejaron de
 * tener sentido y se quitaron (F7.1.3): ya no se admite ninguno en ningún sitio.
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
  if (PYTHON.test(archivo)) problemas.push(`${archivo}: archivo de Python o de QML: la V1 se retiró en F7.1.2`);
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
