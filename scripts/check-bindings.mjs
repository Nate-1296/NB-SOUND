#!/usr/bin/env node
/**
 * Comprobación de deriva de los tipos generados del puente IPC.
 *
 * Los tipos de `src/lib/bindings/` los produce `ts-rs` al ejecutar las pruebas
 * de Rust. Si alguien cambia un tipo que cruza el puente y no los regenera, el
 * frontend y el backend divergen en silencio: compila, pasa los tipos y falla en
 * ejecución.
 *
 * Esta comprobación existía únicamente en el flujo de integración continua. Ese
 * flujo no se ejecuta (ver docs/plan/fase-0-fundaciones.md, deuda de la fase),
 * de modo que la regla no la hacía cumplir nada. Aquí se ejecuta en la máquina
 * donde se programa, que hoy es el único sitio donde algo se ejecuta.
 *
 * Regenera los tipos y falla si el árbol de trabajo queda distinto.
 *
 * Uso: node scripts/check-bindings.mjs
 */

import { spawnSync } from 'node:child_process';
import { readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

const ROOT = resolve(import.meta.dirname, '..');
const BINDINGS = 'src/lib/bindings';

function ejecutar(comando, args, opciones = {}) {
  return spawnSync(comando, args, { cwd: ROOT, encoding: 'utf8', ...opciones });
}

const antes = ejecutar('git', ['status', '--porcelain', '--', BINDINGS]);
if (antes.status !== 0) {
  console.error('No se pudo consultar el estado de git.');
  process.exit(1);
}
// Lo que ya estaba modificado o preparado antes de regenerar no es deriva
// causada por este cambio: se descuenta para no culpar al commit equivocado.
const sucioPrevio = new Set(
  antes.stdout
    .split('\n')
    .filter((l) => l.trim().length > 0)
    .map((l) => l.slice(3))
);

const generacion = ejecutar('cargo', ['test', '--quiet', '--lib', 'export_bindings_'], {
  cwd: resolve(ROOT, 'src-tauri'),
  stdio: 'pipe'
});

if (generacion.status !== 0) {
  console.error('\nNo se pudieron regenerar los tipos del puente:\n');
  console.error(generacion.stderr || generacion.stdout);
  process.exit(1);
}

escribirIndice();

const despues = ejecutar('git', ['status', '--porcelain', '--', BINDINGS]);
const derivados = despues.stdout
  .split('\n')
  .filter((l) => l.trim().length > 0)
  .map((l) => l.slice(3))
  .filter((ruta) => !sucioPrevio.has(ruta));

if (derivados.length > 0) {
  console.error('\nLos tipos del puente IPC no están al día:\n');
  for (const ruta of derivados) console.error(`  ${ruta}`);
  console.error(
    '\nSe han regenerado. Revisa el cambio y añádelo al commit.\n' +
      'Un tipo del puente que cambia es un cambio de contrato: comprueba\n' +
      'docs/adr/README.md antes de continuar.\n'
  );
  process.exit(1);
}

console.log('Tipos del puente IPC: al día.');

/**
 * Reescribe el barril `index.ts` a partir de los archivos que `ts-rs` acaba de
 * generar.
 *
 * Se genera y no se mantiene a mano porque el propio directorio declara que no
 * se edita a mano, y sin embargo este archivo había que tocarlo con cada tipo
 * nuevo. Un archivo que la regla dice que no se toca y que en la práctica se
 * toca es una regla que no se cumple.
 */
function escribirIndice() {
  const dir = join(ROOT, BINDINGS);
  const modulos = readdirSync(dir)
    .filter((f) => f.endsWith('.ts') && f !== 'index.ts')
    .map((f) => f.replace(/\.ts$/, ''))
    .sort((a, b) => a.localeCompare(b, 'en'));

  // Los tipos se reexportan con `export type`; los valores generados, no. La
  // distinción se hace por el nombre del archivo, que es minúscula inicial para
  // los valores y mayúscula para los tipos, siguiendo la convención de
  // CLAUDE.md
  const esTipo = (m) => /^[A-Z]/.test(m);

  const contenido = [
    '/**',
    ' * Tipos generados desde Rust por `ts-rs`.',
    ' *',
    ' * **No se editan a mano.** Se regeneran con `pnpm check:bindings`, que además',
    ' * falla si el árbol de trabajo queda sucio: eso significaría que alguien cambió',
    ' * un tipo del puente sin regenerar.',
    ' *',
    ' * Ver `docs/adr/decisions/ADR-001-pila-tecnologica.md`.',
    ' */',
    '',
    ...modulos.filter(esTipo).map((t) => `export type { ${t} } from './${t}';`),
    ...modulos.filter((m) => !esTipo(m)).map((v) => `export * from './${v}';`),
    ''
  ].join('\n');

  const ruta = join(dir, 'index.ts');
  let actual = '';
  try {
    actual = readFileSync(ruta, 'utf8');
  } catch {}
  if (actual !== contenido) {
    writeFileSync(ruta, contenido);
  }
}
