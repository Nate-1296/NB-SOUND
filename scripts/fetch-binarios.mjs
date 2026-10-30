#!/usr/bin/env node
/**
 * Descarga los binarios que viajan en el instalador, con el hash fijado (F0.3.3).
 *
 * Lo que la V1 hacía mal y esto no repite: bajaba ffmpeg de espejos que cambiaban
 * de contenido y de disponibilidad, y el empaquetado fallaba según el día. Aquí
 * cada archivo tiene su SHA-256 en `scripts/binarios.json`; si el que llega no
 * coincide, no se extrae nada. Ningún binario entra al repositorio: se dejan en
 * `src-tauri/binarios/`, que está ignorado.
 *
 * Uso:
 *   node scripts/fetch-binarios.mjs            descarga lo que falte para esta plataforma
 *   node scripts/fetch-binarios.mjs --check    falla si falta algo o no coincide
 */

import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { chmodSync, copyFileSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { arch, platform } from 'node:os';
import { join, resolve } from 'node:path';

const ROOT = resolve(import.meta.dirname, '..');
const DESTINO = join(ROOT, 'src-tauri', 'binarios');
const DESCARGAS = join(DESTINO, '.descargas');
const manifiesto = JSON.parse(readFileSync(join(ROOT, 'scripts', 'binarios.json'), 'utf8'));

const PLATAFORMA = `${{ linux: 'linux', win32: 'windows', darwin: 'macos' }[platform()]}-${
  { x64: 'x86_64', arm64: 'aarch64' }[arch()]
}`;
/** El sufijo que Tauri exige en `externalBin`. */
const TRIPLE = {
  'linux-x86_64': 'x86_64-unknown-linux-gnu',
  'windows-x86_64': 'x86_64-pc-windows-msvc',
  'macos-aarch64': 'aarch64-apple-darwin',
  'macos-x86_64': 'x86_64-apple-darwin'
}[PLATAFORMA];

const entradas = manifiesto[PLATAFORMA];
if (!entradas || !TRIPLE) {
  console.error(`Binarios: no hay manifiesto para ${PLATAFORMA}.`);
  process.exit(1);
}

const comprobar = process.argv.includes('--check');
const sha256 = (ruta) => createHash('sha256').update(readFileSync(ruta)).digest('hex');

/** Los ejecutables llevan el triple; las bibliotecas, no (las carga ONNX Runtime por nombre). */
function nombreFinal(nombre) {
  const esBiblioteca = /\.(so|dll|dylib)$/.test(nombre);
  if (esBiblioteca) return nombre;
  const [base, ext] = nombre.endsWith('.exe') ? [nombre.slice(0, -4), '.exe'] : [nombre, ''];
  return `${base}-${TRIPLE}${ext}`;
}

const sello = join(DESTINO, '.sellos.json');
const sellos = existsSync(sello) ? JSON.parse(readFileSync(sello, 'utf8')) : {};
let fallos = 0;

for (const entrada of entradas) {
  const finales = Object.values(entrada.extraer).map(nombreFinal);
  const alDia =
    sellos[entrada.nombre] === entrada.sha256 && finales.every((f) => existsSync(join(DESTINO, f)));
  if (alDia) continue;
  if (comprobar) {
    console.error(`Binarios: ${entrada.nombre} falta o no es el fijado. Ejecuta pnpm binarios`);
    fallos++;
    continue;
  }

  mkdirSync(DESCARGAS, { recursive: true });
  const archivo = join(DESCARGAS, entrada.url.split('/').pop());
  if (!existsSync(archivo) || sha256(archivo) !== entrada.sha256) {
    console.log(`Binarios: descargando ${entrada.nombre}`);
    const r = spawnSync('curl', ['-fsSL', '--retry', '3', '-o', archivo, entrada.url], {
      stdio: 'inherit'
    });
    if (r.status !== 0) {
      console.error(`Binarios: no se pudo descargar ${entrada.nombre}`);
      process.exit(1);
    }
  }
  const real = sha256(archivo);
  if (real !== entrada.sha256) {
    rmSync(archivo);
    console.error(
      `Binarios: ${entrada.nombre} no coincide con su huella.\n  esperada ${entrada.sha256}\n  recibida ${real}`
    );
    process.exit(1);
  }

  const tmp = join(DESCARGAS, `${entrada.nombre}-extraido`);
  rmSync(tmp, { recursive: true, force: true });
  mkdirSync(tmp, { recursive: true });
  const extraccion = archivo.endsWith('.zip')
    ? spawnSync('unzip', ['-q', '-o', archivo, ...Object.keys(entrada.extraer), '-d', tmp])
    : spawnSync('tar', ['-xf', archivo, '-C', tmp, ...Object.keys(entrada.extraer)]);
  if (extraccion.status !== 0) {
    console.error(`Binarios: no se pudo extraer ${entrada.nombre}`);
    process.exit(1);
  }
  for (const [dentro, nombre] of Object.entries(entrada.extraer)) {
    const final = join(DESTINO, nombreFinal(nombre));
    copyFileSync(join(tmp, dentro), final);
    chmodSync(final, 0o755);
  }
  rmSync(tmp, { recursive: true, force: true });
  sellos[entrada.nombre] = entrada.sha256;
  writeFileSync(sello, `${JSON.stringify(sellos, null, 2)}\n`);
  console.log(`Binarios: ${entrada.nombre} listo`);
}

if (fallos > 0) process.exit(1);
console.log(`Binarios: ${entradas.length} al día para ${PLATAFORMA}.`);
