#!/usr/bin/env node
/**
 * Rechaza el comando del puente que devuelve una colección sin acotar.
 *
 * # Por qué existe
 *
 * Porque el 2026-09-09, con el corpus real dentro, abrir el panel de autores
 * congelaba la ventana, y la causa no era ese panel: era que **nada impedía a
 * una pantalla pedir una lista cuyo tamaño lo decide la biblioteca**. Con ocho
 * archivos de prueba ninguna de estas listas se nota. Con 152.080 documentos,
 * `list_notes` trae lo que haya, `library_annotations` también, y una
 * importación real dejó 1.219 rechazos que viajaban enteros en una respuesta.
 *
 * La regla es la 1 del contrato de carga, en la sección 1.3 de
 * `CLAUDE.md`: toda lista se pide
 * acotada, siempre, aunque hoy quepa. Mientras nada lo impida, volverá a pasar
 * en el siguiente comando que alguien escriba, que es exactamente como llegó a
 * haber cinco.
 *
 * # Qué comprueba
 *
 * Que todo comando que devuelva `Vec<...>` cumpla una de estas dos cosas:
 *
 * 1. **Que se pida acotado**: tiene un parámetro `limit`, o recibe una consulta
 *    que lo lleva dentro -las que acaban en `Query`, como `BrowseQuery`-.
 * 2. **Que declare su cota**, con la línea `Cota: <cuál>` en su comentario. Es
 *    para lo que está acotado por construcción y no por parámetro: los ocho
 *    componentes del runtime, las preferencias, las extensiones instaladas.
 *
 * # Lo que no comprueba, y conviene decirlo
 *
 * **No verifica que una cota declarada sea cierta.** No puede: "las extensiones
 * instaladas" es una afirmación sobre el mundo, no sobre el texto. Lo que hace
 * es obligar a escribirla, y una cota escrita es revisable mientras que el
 * silencio no lo es. Es una diferencia real con `check-comandos.mjs`, donde la
 * excepción sí se puede comprobar mirando el código, y por eso allí se exige y
 * aquí no se finge.
 *
 * Tampoco entiende Rust: mira texto, como `check-plataforma.mjs`.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

const RAIZ = resolve(import.meta.dirname, '..');
const FUENTES = process.argv[2] ? process.argv[2] : join(RAIZ, 'src-tauri', 'src');

/** Lo que basta para considerar que la petición trae su cota. */
const ACOTADO = [/\blimit\s*:\s*u(size|8|16|32|64)\b/, /\blimit\s*:\s*Option<u/, /:\s*\w*Query\b/];

/** La declaración que lleva lo acotado por construcción. */
const COTA = /Cota:\s*\S/;

/** Cuántas líneas de comentario por encima del atributo se leen buscándola. */
const COMENTARIO = 30;

function archivosRust(directorio) {
  const encontrados = [];
  for (const entrada of readdirSync(directorio)) {
    const ruta = join(directorio, entrada);
    if (statSync(ruta).isDirectory()) encontrados.push(...archivosRust(ruta));
    else if (entrada.endsWith('.rs')) encontrados.push(ruta);
  }
  return encontrados;
}

/** La firma de la función que empieza en `inicio`, hasta la llave de apertura. */
function firma(lineas, inicio) {
  const recogidas = [];
  for (let i = inicio; i < lineas.length && i < inicio + 20; i += 1) {
    recogidas.push(lineas[i]);
    if (lineas[i].includes('{')) break;
  }
  return recogidas.join('\n');
}

/** Los comandos de un archivo que devuelven una colección. */
function colecciones(archivo) {
  const lineas = readFileSync(archivo, 'utf8').split('\n');
  const encontrados = [];

  for (const [i, linea] of lineas.entries()) {
    if (!/^\s*#\[(?:tauri::)?command(\(.*\))?\]\s*$/.test(linea)) continue;

    let inicio = -1;
    for (let j = i + 1; j < lineas.length && j <= i + 10; j += 1) {
      if (/\bfn\s+[a-z_0-9]+/.test(lineas[j])) {
        inicio = j;
        break;
      }
    }
    if (inicio === -1) continue;

    const texto = firma(lineas, inicio);
    // Solo las colecciones. Un `Vec<u8>` de bytes no es una lista de filas,
    // pero tampoco hay ninguno en el puente: si lo hubiera, declararía su cota.
    if (!/->\s*NsResult<Vec</.test(texto)) continue;

    encontrados.push({
      archivo,
      linea: inicio + 1,
      nombre: texto.match(/\bfn\s+([a-z_0-9]+)/)[1],
      firma: texto,
      declaracion: lineas
        .slice(Math.max(0, i - COMENTARIO), i)
        .join('\n')
        .split(/\n\s*\n/)
        .pop()
    });
  }

  return encontrados;
}

const archivos = archivosRust(FUENTES);
const todas = archivos.flatMap(colecciones);
const problemas = [];

for (const comando of todas) {
  if (ACOTADO.some((forma) => forma.test(comando.firma))) continue;
  if (COTA.test(comando.declaracion)) continue;

  problemas.push(
    `  ${relative(RAIZ, comando.archivo)}:${comando.linea}  ${comando.nombre} devuelve una lista sin\n` +
      '        acotar y sin declarar por qué no hace falta'
  );
}

if (todas.length === 0) {
  console.error(`No se encontró ningún comando que devuelva una lista en ${FUENTES}.`);
  console.error(
    'Un guardián que no vigila nada no es un guardián: o la ruta es la que no es,\n' +
      'o las colecciones se declaran de otra forma y esto dejó de comprobarlas.'
  );
  process.exit(1);
}

if (problemas.length > 0) {
  console.error('Hay comandos que devuelven listas cuyo tamaño lo decide la biblioteca:\n');
  console.error(problemas.join('\n'));
  console.error(
    '\nToda lista se pide acotada, aunque hoy quepa: con ocho libros no se nota y con\n' +
      'ciento cincuenta mil es la diferencia entre usable e inusable. Se arregla con un\n' +
      'parámetro `limit`, o declarando la cota con "Cota: <cuál>" cuando la lista está\n' +
      'acotada por construcción y no por quien llama.'
  );
  process.exit(1);
}

const declaradas = todas.filter((c) => !ACOTADO.some((forma) => forma.test(c.firma))).length;
console.log(
  `Listas: ${todas.length} comandos devuelven colecciones, ${todas.length - declaradas} acotados por` +
    ` petición y ${declaradas} por construcción declarada.`
);
