#!/usr/bin/env node
/**
 * Toda ruta que llega del webview se canonicaliza antes de usarse (F7.15).
 *
 * # Por qué existe
 *
 * El innegociable de `CLAUDE.md` -"toda ruta que venga de fuera se canonicaliza y
 * se acota"- tenía la utilidad (`security::resolve_within`) y ningún mecanismo, y
 * decía que ningún comando recibía rutas del webview. El 2026-09-24 eran once: las
 * que eligen los diálogos nativos para guardar, importar, instalar o reapuntar. Diez
 * las trataban bien; `relocate_library_root` guardaba la suya tal como llegaba.
 *
 * # Qué comprueba
 *
 * Cada comando del puente (`#[tauri::command]`) con un parámetro que por su nombre
 * es una ruta -`path`, `ruta`, `destino`, `directory`, `folder`, `carpeta`,
 * `source`, `origen`- tiene que pasarlo, dentro del propio comando, por una de las
 * puertas que canonicalizan:
 *
 *   * `destino_admisible(&state, &path)` para guardar donde diga el usuario: lo
 *     canonicaliza y no deja escribir dentro de los datos de la aplicación;
 *   * `Path::new(&path).canonicalize()` o `PathBuf::from(&path).canonicalize()`;
 *   * `security::resolve_within(base, ...)`, que además la acota a una base.
 *
 * # Lo que no puede ver, y por eso no se afirma
 *
 * Una ruta que llega con otro nombre de parámetro, o dentro de un objeto. Y que una
 * ruta canonicalizada se use después para algo que no debería: acotar a una base es
 * decisión de cada comando, y "guardar donde el usuario elija" no tiene base.
 *
 * Uso: node scripts/check-rutas.mjs
 */

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

const RAIZ = resolve(import.meta.dirname, '..');
const FUENTES = join(RAIZ, 'src-tauri', 'src');
const NOMBRE = /^(path|ruta|destino|directory|folder|carpeta|source|origen)$/;
const TIPO = /^(String|PathBuf|&str|&Path|Option<String>|Option<PathBuf>)$/;

function listar(dir) {
  return readdirSync(dir).flatMap((nombre) => {
    const ruta = join(dir, nombre);
    return statSync(ruta).isDirectory() ? listar(ruta) : ruta.endsWith('.rs') ? [ruta] : [];
  });
}

/** El cuerpo de la función que empieza en `desde`, de su primera llave a la que la cierra. */
function cuerpo(codigo, desde) {
  const abre = codigo.indexOf('{', desde);
  let nivel = 0;
  for (let i = abre; i < codigo.length; i += 1) {
    if (codigo[i] === '{') nivel += 1;
    if (codigo[i] === '}') {
      nivel -= 1;
      if (nivel === 0) return codigo.slice(abre, i + 1);
    }
  }
  return '';
}

const escapar = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const fallos = [];
let comandos = 0;
let rutas = 0;
for (const archivo of listar(FUENTES)) {
  const codigo = readFileSync(archivo, 'utf8');
  for (const marca of codigo.matchAll(
    /#\[tauri::command[^\]]*\]\s*(?:#\[[^\]]*\]\s*)*pub (?:const |async )?fn (\w+)\s*(?:<[^>]*>)?\(/g
  )) {
    comandos += 1;
    const abreFirma = marca.index + marca[0].length;
    const cierraFirma = codigo.indexOf(')', abreFirma);
    // Los parámetros no llevan paréntesis dentro salvo `State<'_, T>`, que no los tiene.
    const firma = codigo.slice(abreFirma, cierraFirma);
    const params = firma
      .split(/,(?![^<]*>)/)
      .map((p) => p.trim())
      .filter(Boolean)
      .map((p) => {
        const [nombre, ...tipo] = p.split(':');
        return { nombre: nombre.replace(/^mut\s+/, '').trim(), tipo: tipo.join(':').trim() };
      });
    const texto = cuerpo(codigo, cierraFirma);
    for (const { nombre, tipo } of params) {
      if (!NOMBRE.test(nombre) || !TIPO.test(tipo)) continue;
      rutas += 1;
      const p = escapar(nombre);
      const puertas = [
        new RegExp(`destino_admisible\\([^)]*\\b${p}\\b`),
        new RegExp(`(?:Path::new|PathBuf::from)\\(\\s*&?${p}\\s*\\)\\s*\\.canonicalize\\(\\)`),
        new RegExp(`\\b${p}\\s*\\.canonicalize\\(\\)`),
        new RegExp(`resolve_within\\([^)]*\\b${p}\\b`)
      ];
      if (!puertas.some((puerta) => puerta.test(texto))) {
        const linea = codigo.slice(0, marca.index).split('\n').length;
        fallos.push(`${relative(RAIZ, archivo)}:${linea}  ${marca[1]}(${nombre}: ${tipo})`);
      }
    }
  }
}

if (fallos.length > 0) {
  console.error('check-rutas: hay comandos que usan una ruta del webview sin canonicalizarla.\n');
  for (const fallo of fallos) console.error(`  ${fallo}`);
  console.error(
    '\n  Pásala por destino_admisible, por .canonicalize() o por security::resolve_within dentro del comando.'
  );
  process.exit(1);
}
console.log(`Rutas: ${comandos} comandos, ${rutas} reciben una ruta y todas se canonicalizan.`);
