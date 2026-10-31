#!/usr/bin/env node
/**
 * Ejecuta todos los guardianes de `pnpm verify`, en orden, y se detiene en el
 * primero que falla.
 *
 * Dos de ellos solo tienen algo que vigilar a partir de cierto punto:
 * `check-transacciones` desde que existe la capa de datos (F1.1.1) y
 * `check-listas` desde el primer comando que devuelve una colección. Hasta
 * entonces **no se dan por buenos en silencio**: se anuncian como pendientes,
 * con el motivo, para que nadie lea un verde que no lo es.
 */

import { spawnSync } from 'node:child_process';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

const ROOT = resolve(import.meta.dirname, '..');
const hayDatos = existsSync(resolve(ROOT, 'src-tauri/src/db'));

// Una aproximación del patrón de `check-listas`: un archivo con comandos que
// devuelve un `Vec` que no son bytes. Si se equivoca hacia el sí, el propio
// guardián falla ruidosamente al no encontrar nada; nunca calla un comando real.
function hayListas(dir = resolve(ROOT, 'src-tauri/src')) {
  return readdirSync(dir, { withFileTypes: true }).some((e) => {
    const ruta = join(dir, e.name);
    if (e.isDirectory()) return hayListas(ruta);
    if (!e.name.endsWith('.rs')) return false;
    const texto = readFileSync(ruta, 'utf8');
    return /#\[(?:tauri::)?command/.test(texto) && /->\s*NsResult<Vec<(?!u8>)/.test(texto);
  });
}
const hayComandosDeLista = hayListas();

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
  ['check-paquete'],
  ...(hayDatos ? [['check-transacciones']] : []),
  ...(hayComandosDeLista ? [['check-listas']] : [])
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
  console.log('Pendiente hasta F1.1.1 (no hay capa de datos que vigilar): check-transacciones.');
}
if (!hayComandosDeLista) {
  console.log('Pendiente (ningún comando devuelve todavía una colección): check-listas.');
}
