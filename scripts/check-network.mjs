#!/usr/bin/env node
/**
 * Una sola puerta de salida de red.
 *
 * `CLAUDE.md` declara innegociable que nada sale del dispositivo sin
 * consentimiento explícito. Ese innegociable lo materializa `src/net.rs`, que
 * comprueba el interruptor general, después el consentimiento por anfitrión y
 * propósito, y solo entonces sale, dejando registro de cada intento.
 *
 * Todo eso vale exactamente lo que valga la afirmación de que **no hay otra
 * puerta**. Y esa afirmación no se puede sostener con disciplina: basta con que
 * alguien, dentro de un año, llame al cliente HTTP desde otro módulo porque le
 * queda a mano. Esto lo impide.
 *
 * Es el mismo mecanismo que mantiene el puente IPC dentro de `$core/ipc`, y por
 * el mismo motivo.
 *
 * Uso: node scripts/check-network.mjs
 */

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

const ROOT = resolve(import.meta.dirname, '..');
const FUENTE = join(ROOT, 'src-tauri', 'src');

/** El único archivo que puede hablar con el cliente HTTP. */
const LA_PUERTA = join(FUENTE, 'net.rs');

/** Nombre del crate cliente. Si cambia, cambia aquí y en `Cargo.toml`. */
const CLIENTE = 'ureq';

/**
 * Los crates que salen a la red con su propio cliente. El de actualizaciones
 * (F7.2.2) solo puede usarse desde la puerta, después de `Red::autorizar`.
 */
const CON_CLIENTE_PROPIO = ['tauri_plugin_updater'];

/** @param {string} dir @returns {string[]} */
function recorrer(dir) {
  const salida = [];
  for (const entrada of readdirSync(dir)) {
    const completo = join(dir, entrada);
    if (statSync(completo).isDirectory()) salida.push(...recorrer(completo));
    else if (entrada.endsWith('.rs')) salida.push(completo);
  }
  return salida;
}

/** Comentarios fuera: mencionar el crate al explicar por qué no se usa es legítimo. */
function sinComentarios(texto) {
  return texto
    .split('\n')
    .map((linea) => (/^\s*(\/\/|\*|\/\*)/.test(linea) ? '' : linea))
    .join('\n');
}

const problemas = [];
const usoDelCliente = new RegExp(`\\b(${[CLIENTE, ...CON_CLIENTE_PROPIO].join('|')})\\s*::`, 'g');

for (const archivo of recorrer(FUENTE)) {
  if (archivo === LA_PUERTA) continue;

  const texto = sinComentarios(readFileSync(archivo, 'utf8'));
  for (const coincidencia of texto.matchAll(usoDelCliente)) {
    const linea = texto.slice(0, coincidencia.index).split('\n').length;
    problemas.push(
      `${relative(ROOT, archivo)}:${linea}  usa "${coincidencia[1]}" fuera de src/net.rs`
    );
  }
}

// Y la puerta tiene que seguir existiendo: si alguien la borra, esta
// comprobación no puede quedarse pasando en verde sobre un proyecto sin puerta.
try {
  const puerta = readFileSync(LA_PUERTA, 'utf8');
  if (!puerta.includes(`${CLIENTE}::`)) {
    problemas.push(`src-tauri/src/net.rs ya no usa "${CLIENTE}": ¿dónde está la puerta?`);
  }
} catch {
  problemas.push('src-tauri/src/net.rs no existe: la puerta de salida de red desapareció');
}

if (problemas.length > 0) {
  console.error(`Salida de red: ${problemas.length} problema(s).\n`);
  for (const p of problemas) console.error(`  ${p}`);
  console.error('\nToda petición saliente pasa por src/net.rs, que comprueba el');
  console.error('interruptor general, el consentimiento y deja registro.');
  console.error('Contrato: CLAUDE.md');
  process.exit(1);
}

console.log('Salida de red: una sola puerta, en src/net.rs.');
