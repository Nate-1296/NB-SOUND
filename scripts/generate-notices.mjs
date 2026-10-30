#!/usr/bin/env node
/**
 * Genera THIRD_PARTY_LICENSES.md (portado de NB Books, su F0.4.7).
 *
 * Casi todas las licencias de nuestras dependencias obligan a conservar el aviso
 * de copyright y el texto de la licencia al redistribuir, y la GPL de NB Sound
 * no exime de eso.
 *
 * Se genera automáticamente: un archivo mantenido a mano queda obsoleto en la
 * primera actualización de dependencias.
 *
 * Uso: node scripts/generate-notices.mjs [--check]
 *   --check  falla si el archivo generado difiere del versionado
 *
 * Ver docs/adr/decisions/ADR-010-licencia.md
 */

import { execFileSync } from 'node:child_process';
import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

const ROOT = resolve(import.meta.dirname, '..');
const SALIDA = join(ROOT, 'THIRD_PARTY_LICENSES.md');

/**
 * Licencias admitidas. Debe coincidir con `deny.toml` y con la política de
 * dependencias, y que coincida **no depende de que nadie se acuerde**:
 * `comprobarListasAlineadas` lo verifica más abajo. Tres listas que dicen lo
 * mismo en tres sitios distintos divergen solas, y la que se queda corta deja
 * pasar una licencia que la política prohíbe.
 */
const PERMITIDAS = new Set([
  'Apache-2.0',
  'Apache-2.0 WITH LLVM-exception',
  'MIT',
  'MIT-0',
  'BSD-2-Clause',
  'BSD-3-Clause',
  'ISC',
  'Zlib',
  'Unicode-3.0',
  'CC0-1.0',
  'Unlicense',
  'BSL-1.0',
  'MPL-2.0',
  '0BSD',
  'CDLA-Permissive-2.0',
  // Tipografías: IBM Plex Sans, en static/fuentes/LICENCIAS.md.
  'OFL-1.1',
  // NB Sound es GPL-3.0-or-later (ADR-010): admite lo compatible con ella.
  'GPL-3.0-or-later',
  'GPL-3.0',
  'LGPL-2.1-or-later',
  'LGPL-3.0-or-later'
]);

/**
 * Comprueba que `deny.toml` admite exactamente las mismas licencias que este
 * archivo.
 *
 * Existe porque la política obliga a tocar tres sitios al ampliar la lista, y
 * una regla que exige acordarse de tres sitios se incumple al segundo cambio.
 * Ver deny.toml.
 */
function comprobarListasAlineadas() {
  const deny = readFileSync(join(ROOT, 'deny.toml'), 'utf8');
  const bloque = deny.slice(deny.indexOf('allow = ['), deny.indexOf(']', deny.indexOf('allow = [')));
  const enDeny = new Set([...bloque.matchAll(/"([^"]+)"/g)].map((m) => m[1]));

  const soloAqui = [...PERMITIDAS].filter((l) => !enDeny.has(l));
  const soloEnDeny = [...enDeny].filter((l) => !PERMITIDAS.has(l));

  if (soloAqui.length > 0 || soloEnDeny.length > 0) {
    console.error('Las listas de licencias admitidas no coinciden.\n');
    for (const l of soloAqui) console.error(`  solo en generate-notices.mjs: ${l}`);
    for (const l of soloEnDeny) console.error(`  solo en deny.toml: ${l}`);
    console.error('\nVer deny.toml');
    process.exit(1);
  }
}


function ejecutar(cmd, args, cwd) {
  return execFileSync(cmd, args, { cwd, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
}

/** Dependencias de Rust que acaban en el binario. */
function dependenciasRust() {
  const salida = ejecutar('cargo', ['metadata', '--format-version', '1'], join(ROOT, 'src-tauri'));
  const { packages, resolve: grafo, workspace_members: miembros } = JSON.parse(salida);
  const propios = new Set(miembros);

  return grafo.nodes
    .filter((n) => !propios.has(n.id))
    .map((n) => packages.find((p) => p.id === n.id))
    .filter(Boolean)
    .map((p) => ({
      nombre: p.name,
      version: p.version,
      licencia: p.license ?? (p.license_file ? 'ver archivo de licencia' : 'SIN DECLARAR'),
      repositorio: p.repository ?? ''
    }))
    .sort((a, b) => a.nombre.localeCompare(b.nombre));
}

/** Dependencias de Node incluidas en el bundle del frontend. */
function dependenciasNode() {
  const salida = ejecutar('pnpm', ['licenses', 'list', '--json', '--prod'], ROOT);
  const porLicencia = JSON.parse(salida);

  const paquetes = [];
  for (const [licencia, entradas] of Object.entries(porLicencia)) {
    for (const entrada of entradas) {
      paquetes.push({
        nombre: entrada.name,
        version: Array.isArray(entrada.versions) ? entrada.versions.join(', ') : entrada.version,
        licencia,
        repositorio: entrada.homepage ?? ''
      });
    }
  }
  return paquetes.sort((a, b) => a.nombre.localeCompare(b.nombre));
}

/**
 * Código de terceros **copiado dentro** del repositorio, no traído por un gestor
 * de paquetes.
 *
 * `cargo metadata` no lo ve, así que sin esta lista la atribución que exigen MIT
 * y Apache-2.0 se quedaría fuera del archivo que se distribuye. Cada entrada
 * apunta a la carpeta donde vive su `PROCEDENCIA.md`, y más abajo se comprueba
 * que no haya ninguna carpeta vendorizada sin entrada: una lista a mano que nadie
 * comprueba se queda corta en la segunda vez.
 */
const VENDORIZADOS = [];

/** Carpetas con un `PROCEDENCIA.md`: ahí vive código de fuera. */
function carpetasVendorizadas(raiz) {
  const encontradas = [];
  const recorrer = (dir) => {
    for (const entrada of readdirSync(dir)) {
      if (entrada === 'node_modules' || entrada === 'target' || entrada.startsWith('.')) continue;
      const ruta = join(dir, entrada);
      if (statSync(ruta).isDirectory()) recorrer(ruta);
      else if (entrada === 'PROCEDENCIA.md') encontradas.push(relative(raiz, dir));
    }
  };
  recorrer(join(raiz, 'src-tauri', 'src'));
  return encontradas;
}

function comprobarVendorizados(problemas) {
  const declaradas = new Set(VENDORIZADOS.map((v) => v.carpeta));
  for (const carpeta of carpetasVendorizadas(ROOT)) {
    if (!declaradas.has(carpeta)) {
      problemas.push(
        `Vendorizado: ${carpeta} trae código de fuera y no está en VENDORIZADOS de este script`
      );
    }
  }
}

function tablaVendorizados() {
  const filas = VENDORIZADOS.map(
    (v) =>
      `| \`${v.nombre}\` | ${v.version} | ${v.licencia} | ${v.repositorio} | ${v.copyright} | \`${v.carpeta}\` |`
  );
  return [
    '| Componente | Versión | Licencia | Origen | Copyright | Dónde vive aquí |',
    '|---|---|---|---|---|---|',
    ...filas
  ].join('\n');
}

function tabla(paquetes) {
  const filas = paquetes.map(
    (p) => `| \`${p.nombre}\` | ${p.version} | ${p.licencia} | ${p.repositorio} |`
  );
  return ['| Componente | Versión | Licencia | Origen |', '|---|---|---|---|', ...filas].join('\n');
}

function verificarLicencias(paquetes, origen, problemas) {
  for (const p of paquetes) {
    const licencias = p.licencia.split(/\s+(?:OR|AND)\s+|\//).map((l) => l.trim().replace(/[()]/g, ''));
    if (!licencias.some((l) => PERMITIDAS.has(l))) {
      problemas.push(`${origen}: ${p.nombre}@${p.version} declara "${p.licencia}"`);
    }
  }
}

const rust = dependenciasRust();
const node = dependenciasNode();

const problemas = [];
verificarLicencias(rust, 'Rust', problemas);
verificarLicencias(node, 'Node', problemas);
verificarLicencias(VENDORIZADOS, 'Vendorizado', problemas);
comprobarVendorizados(problemas);

const contenido = `# Componentes de terceros

<!-- GENERADO AUTOMÁTICAMENTE por scripts/generate-notices.mjs. No editar a mano. -->

NB Sound se distribuye bajo GPL-3.0-or-later e incluye software de terceros. Este archivo enumera esos
componentes y sus licencias, en cumplimiento de las obligaciones de atribución de cada una.

Regenerar: \`node scripts/generate-notices.mjs\`

## Binarios que viajan en el instalador

| Componente | Versión | Licencia | Origen | Para qué |
|---|---|---|---|---|
| Chromaprint (\`fpcalc\`) | 1.6.2 | LGPL-2.1-or-later | https://github.com/acoustid/chromaprint | Huella acústica para AcoustID |
| ONNX Runtime | 1.31.1 | MIT | https://github.com/microsoft/onnxruntime | Inferencia de los agregados |
| IBM Plex Sans | 6.x | OFL-1.1 | https://github.com/IBM/plex | Tipografía de la interfaz (\`static/fuentes/LICENCIAS.md\`) |

Los modelos de los agregados no viajan en el instalador: cada uno muestra su licencia en Ajustes > Agregados
(ADR-010).

## Componentes de Rust (${rust.length})

${tabla(rust)}

## Componentes de JavaScript (${node.length})

${tabla(node)}
`;

/**
 * Comprueba que `LICENSE`, `NOTICE` y `THIRD_PARTY_LICENSES.md` viajan dentro del
 * paquete (`bundle.resources` de `src-tauri/tauri.conf.json`) y existen en disco
 * (F7.34).
 *
 * Ver docs/adr/decisions/ADR-010-licencia.md, secciones 3 y 5.
 */
function comprobarEmpaquetado() {
  const rutaConfig = join(ROOT, 'src-tauri', 'tauri.conf.json');
  const config = JSON.parse(readFileSync(rutaConfig, 'utf8'));
  const recursos = config?.bundle?.resources ?? {};
  const requeridos = ['../LICENSE', '../THIRD_PARTY_LICENSES.md'];
  const faltan = [];

  for (const rel of requeridos) {
    if (!(rel in recursos)) {
      faltan.push(`falta "${rel}" en bundle.resources de src-tauri/tauri.conf.json`);
      continue;
    }
    const rutaReal = resolve(join(ROOT, 'src-tauri'), rel);
    try {
      if (!statSync(rutaReal).isFile()) {
        faltan.push(`"${rel}" no es un archivo regular (${rutaReal})`);
      }
    } catch {
      faltan.push(`"${rel}" está en bundle.resources pero no existe en ${rutaReal}`);
    }
  }

  if (faltan.length > 0) {
    console.error('Los avisos legales no viajan completos en el paquete:\n');
    for (const f of faltan) console.error(`  ${f}`);
    console.error('\nVer docs/adr/decisions/ADR-010-licencia.md');
    process.exit(1);
  }
}

comprobarListasAlineadas();
comprobarEmpaquetado();

if (process.argv.includes('--check')) {
  let versionado = '';
  try {
    versionado = readFileSync(SALIDA, 'utf8');
  } catch {
    console.error('THIRD_PARTY_LICENSES.md no existe. Ejecuta: node scripts/generate-notices.mjs');
    process.exit(1);
  }
  if (versionado !== contenido) {
    console.error('THIRD_PARTY_LICENSES.md está desactualizado. Ejecuta: node scripts/generate-notices.mjs');
    process.exit(1);
  }
  console.log('Avisos de terceros: al día.');
} else {
  writeFileSync(SALIDA, contenido);
  console.log(`Avisos generados: ${rust.length} componentes de Rust, ${node.length} de JavaScript.`);
}

if (problemas.length > 0) {
  console.error('\nLicencias no permitidas por la política de dependencias:\n');
  for (const p of problemas) console.error(`  ${p}`);
  console.error('\nVer ADR-010');
  process.exit(1);
}
