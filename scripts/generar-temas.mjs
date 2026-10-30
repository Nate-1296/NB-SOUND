#!/usr/bin/env node
/**
 * Escribe `src/lib/ui/temas-v1.ts`: los 63 temas de la V1, con todos sus colores,
 * leídos de `legado/ui/modelos_qml.py` (`_TEMAS`).
 *
 * Se genera en vez de copiarse a mano por lo mismo que las paletas: una copia de
 * 945 colores se desincroniza en silencio. La V1 está congelada, así que en la
 * práctica esto solo falla si alguien edita el archivo generado.
 *
 * Uso:
 *   node scripts/generar-temas.mjs           escribe el archivo
 *   node scripts/generar-temas.mjs --check   falla si no está al día
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const ORIGEN = resolve('legado/ui/modelos_qml.py');
const DESTINO = resolve('src/lib/ui/temas-v1.ts');
const CLAVES = [
  'fondo',
  'fondoElevado',
  'superficie',
  'superficieAlt',
  'borde',
  'texto',
  'textoSec',
  'textoMuted',
  'acento',
  'acentoFuerte',
  'hover',
  'seleccion',
  'exito',
  'peligro',
  'advertencia'
];

const fuente = readFileSync(ORIGEN, 'utf8');
const inicio = fuente.indexOf('    _TEMAS = {');
const fin = fuente.indexOf('\n    }\n', inicio);
if (inicio < 0 || fin < 0) {
  console.error('No se encontró _TEMAS en legado/ui/modelos_qml.py.');
  process.exit(1);
}
const bloque = fuente.slice(inicio, fin);

const temas = [];
for (const m of bloque.matchAll(/^ {8}"([a-z0-9_]+)": \{([\s\S]*?)^ {8}\}/gm)) {
  const [, id, cuerpo] = m;
  const valores = Object.fromEntries(
    [...cuerpo.matchAll(/"([a-zA-Z]+)":\s*"([^"]*)"/g)].map((v) => [v[1], v[2]])
  );
  for (const clave of [...CLAVES, 'nombre']) {
    if (!valores[clave]) {
      console.error(`El tema ${id} no tiene "${clave}".`);
      process.exit(1);
    }
  }
  temas.push({ id, valores });
}

if (temas.length !== 63) {
  console.error(`Se esperaban 63 temas y hay ${temas.length}.`);
  process.exit(1);
}

const lineas = temas.map(({ id, valores }) => {
  const colores = CLAVES.map((c) => `${c}: '${valores[c].toLowerCase()}'`).join(', ');
  return `  { id: '${id}', nombre: '${valores.nombre.replace(/'/g, "\\'")}', colores: { ${colores} } }`;
});

const texto = `/*
 * GENERADO POR scripts/generar-temas.mjs DESDE legado/ui/modelos_qml.py. NO SE EDITA A MANO.
 *
 * Los 63 temas de la V1 con todos sus colores (enmienda de ADR-008).
 */

export interface ColoresV1 {
${CLAVES.map((c) => `  readonly ${c}: string;`).join('\n')}
}

export interface TemaV1 {
  readonly id: string;
  readonly nombre: string;
  readonly colores: ColoresV1;
}

export const TEMAS_V1: readonly TemaV1[] = [
${lineas.join(',\n')}
];
`;

if (process.argv.includes('--check')) {
  let actual = '';
  try {
    actual = readFileSync(DESTINO, 'utf8');
  } catch {
    actual = '';
  }
  if (actual !== texto) {
    console.error('src/lib/ui/temas-v1.ts está desactualizado. Ejecuta: node scripts/generar-temas.mjs');
    process.exit(1);
  }
  console.log(`Temas de la V1: ${temas.length}, al día.`);
} else {
  writeFileSync(DESTINO, texto);
  console.log(`Temas de la V1 escritos: ${temas.length}.`);
}
