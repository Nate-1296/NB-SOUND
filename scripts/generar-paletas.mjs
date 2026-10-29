#!/usr/bin/env node
/**
 * Escribe `src/paletas.css`: las paletas de Material 3 de fábrica, claro y oscuro
 * con contraste normal y alto, más las del estado inicial del documento.
 *
 * Portado de `NB_Books/scripts/generar-paletas.mjs`. Existe por el mismo motivo:
 * si las paletas solo se calcularan en JavaScript, el primer fotograma se pintaría
 * sin colores. Y se genera en vez de escribirse porque una copia a mano de lo que
 * calcula una función se desincroniza el día que la función cambia.
 *
 * Uso:
 *   node scripts/generar-paletas.mjs           escribe el archivo
 *   node scripts/generar-paletas.mjs --check   falla si no está al día
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { createServer } from 'vite';

const DESTINO = resolve('src/paletas.css');

const servidor = await createServer({
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent'
});
const { generarVariablesM3 } = await servidor.ssrLoadModule('/src/lib/ui/generadorM3.ts');
const { ESQUEMAS, NIVEL_DE_CONTRASTE, SEMILLA_DE_FABRICA } =
  await servidor.ssrLoadModule('/src/lib/ui/tema.ts');
await servidor.close();

function bloque(selector, oscuro, contraste) {
  const variables = generarVariablesM3(SEMILLA_DE_FABRICA, oscuro, contraste);
  const cuerpo = Object.entries(variables)
    .map(([nombre, valor]) => `  ${nombre}: ${valor};`)
    .join('\n');
  return `${selector} {\n${cuerpo}\n}`;
}

const sangrar = (texto) =>
  texto
    .split('\n')
    .map((l) => `  ${l}`)
    .join('\n');

const bloques = [
  // Antes de que nadie resuelva el tema, el documento sigue al sistema.
  bloque(':root', false, 0),
  `@media (prefers-color-scheme: dark) {\n${sangrar(bloque(':root', true, 0))}\n}`
];
for (const esquema of ESQUEMAS) {
  const oscuro = esquema === 'oscuro';
  bloques.push(bloque(`:root[data-esquema='${esquema}']`, oscuro, NIVEL_DE_CONTRASTE.normal));
  bloques.push(
    bloque(
      `:root[data-esquema='${esquema}'][data-contraste='alto']`,
      oscuro,
      NIVEL_DE_CONTRASTE.alto
    )
  );
}

const contenido = `/*
 * GENERADO POR scripts/generar-paletas.mjs. NO SE EDITA A MANO.
 *
 * Las paletas de fábrica de Material 3: claro y oscuro, con contraste normal y
 * alto, y las dos del estado inicial del documento.
 */

${bloques.join('\n\n')}
`;

if (process.argv.includes('--check')) {
  let actual = '';
  try {
    actual = readFileSync(DESTINO, 'utf8');
  } catch {
    console.error('Paletas: falta src/paletas.css. Ejecuta pnpm paletas');
    process.exit(1);
  }
  if (actual !== contenido) {
    console.error('Paletas: src/paletas.css no es el que genera el generador. Ejecuta pnpm paletas');
    process.exit(1);
  }
  console.log('Paletas: al día.');
} else {
  writeFileSync(DESTINO, contenido);
  console.log(`Paletas: escritas ${bloques.length} en ${DESTINO}`);
}
