#!/usr/bin/env node
/**
 * Ejecuta todos los guardianes de `pnpm verify`, en orden, y se detiene en el
 * primero que falla.
 *
 * Dos de ellos solo tienen algo que vigilar cuando existe la capa de datos
 * (F1.1.1). Hasta entonces **no se dan por buenos en silencio**: se anuncian
 * como pendientes, con el motivo, para que nadie lea un verde que no lo es.
 */

import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

const ROOT = resolve(import.meta.dirname, '..');
const hayDatos = existsSync(resolve(ROOT, 'src-tauri/src/db'));

const GUARDIANES = [
  ['check-docs'],
  ['check-sin-python'],
  ['generar-paletas', '--check'],
  ['check-ui'],
  ['check-i18n'],
  ['check-error-contract'],
  ['check-bindings'],
  ['check-puente'],
  ['check-comandos'],
  ['check-network'],
  ['check-registro'],
  ['check-rutas'],
  ['check-plataforma'],
  ['generate-notices', '--check'],
  ...(hayDatos ? [['check-transacciones'], ['check-listas']] : [])
];

for (const [nombre, ...args] of GUARDIANES) {
  const r = spawnSync('node', [resolve(ROOT, 'scripts', `${nombre}.mjs`), ...args], {
    cwd: ROOT,
    stdio: 'inherit'
  });
  if (r.status !== 0) {
    console.error(`\nGuardián fallido: ${nombre}`);
    process.exit(r.status ?? 1);
  }
}

if (!hayDatos) {
  console.log(
    'Pendientes hasta F1.1.1 (no hay capa de datos que vigilar): check-transacciones, check-listas.'
  );
}
