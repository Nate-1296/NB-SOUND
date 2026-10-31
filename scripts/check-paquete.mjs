#!/usr/bin/env node
/**
 * Rechaza el paquete de arranque que no cabe en su presupuesto, y la carga
 * diferida que ya no difiere nada.
 *
 * Portado de NB Books. Mide la compilación de `build/` (NB Sound no tiene aún
 * suite de interfaz con carpeta propia) y compila si es más vieja que el código.
 *
 * # Por qué existe
 *
 * Porque el presupuesto del paquete estaba escrito desde la Fase 0 y **nadie lo
 * medía al cerrar una iteración**. El 2026-09-10 se midió por primera vez desde
 * agosto y estaba en 504 KB, el doble de los 250 que permite
 * `docs/engineering/architecture/performance-budgets.md` (sección 4.9). Un
 * presupuesto que se mide cuando alguien se acuerda es una aspiración.
 *
 * Y porque la forma de volver a caber, partir el paquete por destino, tiene un
 * modo de fallar que no se ve. Un `import()` cuyo módulo importa también de forma
 * estática algo del arranque **no crea un trozo aparte**: la aplicación funciona
 * igual, la carga "diferida" se resuelve al instante, y el peso vuelve al
 * arranque sin que falle ninguna prueba. Pasó mientras se escribía esto, con el
 * sintetizador de los fondos sonoros: se cargaba a demanda, y seguía entero en el
 * arranque porque otra función del mismo archivo se usaba al abrir.
 *
 * # Qué comprueba
 *
 * 1. Que el JavaScript que se carga antes de la primera pantalla no pase de
 *    250 KB. **Sin comprimir**: es una aplicación de escritorio y los archivos se
 *    leen del disco, así que lo que cuesta no es transferirlos sino leerlos y
 *    compilarlos, y eso crece con el tamaño real.
 * 2. Que cada `import()` del código de `src/` siga siendo un trozo aparte, y que
 *    ese trozo no se cargue al arrancar.
 *
 * # Qué es "el arranque"
 *
 * Lo que el manifiesto de Vite declara como entrada —el cargador de SvelteKit, la
 * aplicación y los nodos de ruta— más todo lo que importan de forma estática. Hay
 * una sola ruta, así que sus nodos se cargan todos al abrir; si algún día hay más,
 * contarán también, y eso hace la cifra más exigente, no menos.
 *
 * # Qué compilación mide
 *
 * La que acaba de hacer la suite de interfaz, que en `pnpm verify` corre justo
 * antes: `build-e2e/`, la misma compilación de producción desviada de carpeta
 * (ver `playwright.config.ts`). Si falta, o es más vieja que el código, compila:
 * medir un paquete viejo sería medir otro.
 *
 * Por eso no está en el gancho de pre-commit: compilar tarda más de lo que un
 * commit puede esperar.
 *
 * Uso:
 *   node scripts/check-paquete.mjs          comprueba
 *   node scripts/check-paquete.mjs --json   imprime las cifras, sin juzgarlas
 */

import { execSync } from 'node:child_process';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';

const RAIZ = resolve(import.meta.dirname, '..');
const PRESUPUESTO_KB = 250;
const COMPILACION = join(RAIZ, 'build');
const MANIFIESTO = join(RAIZ, '.svelte-kit', 'output', 'client', '.vite', 'manifest.json');

/** Lo que, si cambia, cambia el paquete. */
const FUENTES = ['src', 'vite.config.js', 'package.json', 'pnpm-lock.yaml'];

const ALIAS = { '$lib/': 'src/lib/', '$ui/': 'src/lib/ui/', '$core/': 'src/lib/core/' };

const JSON_PEDIDO = process.argv.includes('--json');

function listar(ruta, acepta) {
  if (!existsSync(ruta)) return [];
  if (!statSync(ruta).isDirectory()) return acepta(ruta) ? [ruta] : [];
  return readdirSync(ruta).flatMap((nombre) => listar(join(ruta, nombre), acepta));
}

function compilarSiHaceFalta() {
  const ultimoCambio = Math.max(
    ...FUENTES.flatMap((f) => listar(join(RAIZ, f), () => true)).map((f) => statSync(f).mtimeMs)
  );
  if (existsSync(MANIFIESTO) && statSync(MANIFIESTO).mtimeMs >= ultimoCambio) return;

  // A la salida de error: con `--json`, la estándar es la de las cifras.
  console.error('check-paquete: la compilación falta o es anterior al código; se compila.');
  try {
    execSync('pnpm build', { cwd: RAIZ, stdio: 'pipe' });
  } catch (fallo) {
    // Lo que dice la compilación solo se enseña si falla: si no, son avisos de
    // CSS de terceros que tapan la única línea que importa.
    console.error(String(fallo.stdout ?? ''), String(fallo.stderr ?? ''));
    process.exit(1);
  }
}

/** Los archivos que se cargan antes de la primera pantalla. */
function delArranque(manifiesto) {
  const vistas = new Set();
  const visitar = (clave) => {
    if (vistas.has(clave)) return;
    vistas.add(clave);
    for (const importada of manifiesto[clave].imports ?? []) visitar(importada);
  };
  for (const [clave, trozo] of Object.entries(manifiesto)) if (trozo.isEntry) visitar(clave);
  return new Set([...vistas].map((clave) => manifiesto[clave].file));
}

/** Cada `import()` del código, con el archivo que lo hace. Las pruebas no cuentan. */
function importacionesDiferidas() {
  const codigo = listar(
    join(RAIZ, 'src'),
    (f) => /\.(ts|svelte)$/.test(f) && !/\.test\.ts$/.test(f)
  );
  return codigo.flatMap((archivo) =>
    [...readFileSync(archivo, 'utf8').matchAll(/\bimport\(\s*['"]([^'"]+)['"]\s*\)/g)].map(
      (m) => ({ archivo: relative(RAIZ, archivo), especificador: m[1] })
    )
  );
}

/** La clave del manifiesto que corresponde a lo que se importa, si es un trozo. */
function claveDe(manifiesto, archivo, especificador) {
  let base = null;
  if (especificador.startsWith('.')) {
    base = relative(RAIZ, resolve(RAIZ, dirname(archivo), especificador));
  } else {
    const alias = Object.keys(ALIAS).find((a) => especificador.startsWith(a));
    if (alias) base = ALIAS[alias] + especificador.slice(alias.length);
  }

  if (base === null) {
    // Un paquete: su clave es su ruta dentro de `node_modules`.
    return (
      Object.keys(manifiesto).find(
        (clave) =>
          clave.endsWith(`/node_modules/${especificador}.js`) ||
          clave.endsWith(`/node_modules/${especificador}/index.js`)
      ) ?? null
    );
  }

  // `./paleta.js` nombra a `paleta.ts`: es como TypeScript escribe las importaciones.
  const sinJs = base.replace(/\.js$/, '');
  const candidatas = [base, `${sinJs}.ts`, `${base}.ts`, `${base}.svelte`, `${base}/index.ts`];
  return candidatas.find((clave) => manifiesto[clave]) ?? null;
}

const kb = (bytes) => Math.round((bytes / 1024) * 10) / 10;

compilarSiHaceFalta();

const manifiesto = JSON.parse(readFileSync(MANIFIESTO, 'utf8'));
const arranque = delArranque(manifiesto);
const tamano = (archivo) => statSync(join(COMPILACION, archivo)).size;

const bytesDelArranque = [...arranque].filter((f) => f.endsWith('.js')).reduce((s, f) => s + tamano(f), 0);
const bytesTotales = listar(join(COMPILACION, '_app', 'immutable'), (f) => f.endsWith('.js')).reduce(
  (s, f) => s + statSync(f).size,
  0
);

const fallos = [];
const diferidos = new Map();
for (const { archivo, especificador } of importacionesDiferidas()) {
  const clave = claveDe(manifiesto, archivo, especificador);
  const trozo = clave ? manifiesto[clave] : null;
  if (!trozo?.isDynamicEntry) {
    fallos.push(
      `${archivo}: import('${especificador}') no es un trozo aparte. Algo del arranque importa ` +
        'ese módulo de forma estática, así que se carga al abrir y la espera no ahorra nada.'
    );
  } else if (arranque.has(trozo.file)) {
    fallos.push(
      `${archivo}: import('${especificador}') es un trozo aparte, pero el arranque lo importa ` +
        'igualmente de forma estática.'
    );
  } else {
    diferidos.set(clave, kb(tamano(trozo.file)));
  }
}

if (JSON_PEDIDO) {
  console.log(
    JSON.stringify(
      {
        arranque_kb: kb(bytesDelArranque),
        total_kb: kb(bytesTotales),
        presupuesto_kb: PRESUPUESTO_KB,
        diferidos: Object.fromEntries(diferidos),
        fallos
      },
      null,
      2
    )
  );
  process.exit(0);
}

if (kb(bytesDelArranque) > PRESUPUESTO_KB) {
  fallos.push(
    `El arranque carga ${kb(bytesDelArranque)} KB de JavaScript y el presupuesto es ${PRESUPUESTO_KB}. ` +
      'Lo que se parte es el paquete por destino, no el presupuesto: ver performance-budgets.md, sección 4.11.'
  );
}

if (fallos.length > 0) {
  console.error('check-paquete: el paquete de arranque no cumple.\n');
  for (const fallo of fallos) console.error(`  ${fallo}`);
  process.exit(1);
}

console.log(
  `check-paquete: el arranque carga ${kb(bytesDelArranque)} KB de ${PRESUPUESTO_KB}; ` +
    `${diferidos.size} importaciones diferidas, todas fuera de él (${kb(bytesTotales)} KB en total).`
);
