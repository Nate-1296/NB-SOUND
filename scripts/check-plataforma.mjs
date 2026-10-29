#!/usr/bin/env node
/**
 * Rechaza el código atado a una sola plataforma que no declare que lo está.
 *
 * # Por qué existe
 *
 * Porque el 2026-09-02 se descubrió que **el runtime no compilaba en Windows**.
 * `voice/ssip.rs` hablaba por un socket de dominio Unix sin ninguna condición,
 * y `std::os::unix` no existe en Windows: no es que la voz no funcionara allí,
 * es que el binario entero no se podía construir.
 *
 * Llevaba semanas así y nadie podía verlo. La única máquina donde se compila es
 * Linux, y el CI —que sí declara una matriz con `windows-latest` y
 * `macos-latest`— **nunca ha llegado a ejecutarse**: sus trabajos se cancelan
 * antes de empezar por la facturación de la cuenta. Un mecanismo que no corre
 * no es un mecanismo, y esa es exactamente la clase de cosa que este proyecto
 * no da por buena.
 *
 * Esto no sustituye a compilar de verdad para las tres plataformas, que es lo
 * que hará el CI cuando pueda correr. Lo que hace es cazar la causa concreta
 * que ya nos mordió, en cualquier máquina y en menos de un segundo.
 *
 * # Qué comprueba
 *
 * Que ningún archivo use un símbolo exclusivo de una plataforma si el módulo no
 * está declarado bajo la condición correspondiente. Un módulo declarado
 * `#[cfg(unix)] pub mod ssip;` puede usar lo que quiera de Unix: ya ha dicho
 * que es de Unix.
 *
 * # Lo que no comprueba, dicho como tal
 *
 * No entiende Rust: mira texto. Un símbolo dentro de una función marcada
 * `#[cfg(unix)]` en mitad de un archivo por lo demás portátil lo reconoce por
 * cercanía, no por análisis, así que puede aceptar algo que un compilador
 * rechazaría. Al revés no: si aquí pasa algo, es porque está declarado.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

const RAIZ = resolve(import.meta.dirname, '..');
const FUENTES = join(RAIZ, 'src-tauri', 'src');

/** Símbolos que solo existen en una plataforma, y bajo qué condición valen. */
const EXCLUSIVOS = [
  { patron: /std::os::unix\b/, plataforma: 'unix' },
  { patron: /\bUnixStream\b/, plataforma: 'unix' },
  { patron: /\bUnixListener\b/, plataforma: 'unix' },
  { patron: /\bPermissionsExt\b/, plataforma: 'unix' },
  { patron: /std::os::windows\b/, plataforma: 'windows' },
  { patron: /\bstd::os::fd\b/, plataforma: 'unix' }
];

/** Condiciones que bastan para declarar cada plataforma. */
const CONDICIONES = {
  unix: /cfg\(\s*(unix|target_os\s*=\s*"(linux|macos|android|ios|freebsd)")/,
  windows: /cfg\(\s*(windows|target_os\s*=\s*"windows")/
};

/** Cuántas líneas hacia atrás se busca la condición que ampara un símbolo. */
const CERCANIA = 10;

function archivosRust(directorio) {
  const encontrados = [];
  for (const entrada of readdirSync(directorio)) {
    const ruta = join(directorio, entrada);
    if (statSync(ruta).isDirectory()) encontrados.push(...archivosRust(ruta));
    else if (entrada.endsWith('.rs')) encontrados.push(ruta);
  }
  return encontrados;
}

/**
 * Módulos declarados bajo una condición de plataforma.
 *
 * Se lee de las declaraciones `mod`, que es donde el proyecto decide qué se
 * compila. Cubre también `#[path = "otro.rs"]`, que es como se sirve una
 * implementación distinta detrás del mismo nombre.
 */
function modulosCondicionados(archivos) {
  const condicionados = new Map();
  for (const archivo of archivos) {
    const lineas = readFileSync(archivo, 'utf8').split('\n');
    for (const [i, linea] of lineas.entries()) {
      const declaracion = linea.match(/^\s*(?:pub\s+)?mod\s+([a-z_0-9]+)\s*;/);
      if (!declaracion) continue;

      const antes = lineas.slice(Math.max(0, i - 4), i).join('\n');
      for (const [plataforma, condicion] of Object.entries(CONDICIONES)) {
        if (!condicion.test(antes)) continue;
        // El archivo real puede venir de `#[path = "..."]`.
        const camino = antes.match(/#\[path\s*=\s*"([^"]+)"\]/);
        const nombre = camino ? camino[1].replace(/\.rs$/, '') : declaracion[1];
        condicionados.set(nombre, plataforma);
      }
    }
  }
  return condicionados;
}

const archivos = archivosRust(FUENTES);
const condicionados = modulosCondicionados(archivos);
const problemas = [];

for (const archivo of archivos) {
  const nombre = archivo.split('/').pop().replace(/\.rs$/, '');
  const lineas = readFileSync(archivo, 'utf8').split('\n');

  for (const [i, linea] of lineas.entries()) {
    if (linea.trimStart().startsWith('//')) continue;

    for (const { patron, plataforma } of EXCLUSIVOS) {
      if (!patron.test(linea)) continue;
      // El módulo entero ya declaró de qué plataforma es.
      if (condicionados.get(nombre) === plataforma) continue;
      // O lo declara una condición cercana, para un bloque suelto.
      const antes = lineas.slice(Math.max(0, i - CERCANIA), i + 1).join('\n');
      if (CONDICIONES[plataforma].test(antes)) continue;

      // Dos patrones pueden coincidir en la misma línea (`std::os::unix` y
      // `UnixStream`): es un solo problema, no dos.
      const aviso =
        `  ${relative(RAIZ, archivo)}:${i + 1}  usa algo exclusivo de ${plataforma} sin declararlo\n` +
        `    ${linea.trim()}`;
      if (!problemas.includes(aviso)) problemas.push(aviso);
    }
  }
}

if (problemas.length > 0) {
  console.error('Código atado a una plataforma sin declararlo:\n');
  console.error(problemas.join('\n'));
  console.error(
    '\nUn símbolo de una sola plataforma necesita su `#[cfg(...)]`, o el binario\n' +
      'no se construye en las demás. Si la función no existe fuera de ahí, se\n' +
      'declara ausente: la ausencia se declara, no se disimula.'
  );
  process.exit(1);
}

console.log(
  `Plataformas: ${archivos.length} archivos de Rust, ninguno atado a una sola sin declararlo.`
);
