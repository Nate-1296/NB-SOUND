#!/usr/bin/env node
/**
 * Rechaza el comando del puente que corre en el hilo de la ventana.
 *
 * # Por qué existe
 *
 * Porque el 2026-09-09, con el corpus real dentro, se leyó el código y apareció
 * la causa que domina a todas las demás: **los 110 comandos del puente eran
 * síncronos**. En Tauri un comando sin `async` corre en el hilo principal, que
 * es el que atiende la ventana, así que no es que un panel tardara en pintarse:
 * es que la ventana estaba **bloqueada** durante toda la consulta. Con ocho
 * archivos generados eso no se ve; con 152.080 documentos es la diferencia
 * entre una interfaz viva y una congelada.
 *
 * La regla está en la sección 1.3, regla 6 de
 * `CLAUDE.md`, y la sostiene la
 * regla 5 de `CLAUDE.md`. Se arregla con
 * una palabra por comando, que es exactamente la clase de cosa que se vuelve a
 * perder en el siguiente comando que alguien escriba. De ahí este guardián.
 *
 * # Qué comprueba
 *
 * Que todo `#[tauri::command]` sea asíncrono, por el atributo `(async)` o por
 * ser `async fn`. Reconoce también la forma corta `#[command]`, que es lo que
 * se escribe cuando alguien importa `tauri::command`: si solo mirara la forma
 * larga, bastaría un `use` para dejar de estar vigilado.
 *
 * **La excepción es exacta y no se amplía.** Lo que toca la ventana, el diálogo
 * nativo, el menú o la bandeja del sistema se queda en el hilo principal: en
 * Linux la biblioteca gráfica del sistema no es segura entre hilos, y llamarla
 * desde otro hilo no da lentitud, da un fallo. Para acogerse a ella hacen falta
 * las dos cosas a la vez:
 *
 * 1. **Declararlo**, con la línea `Se queda en el hilo principal: <motivo>` en
 *    el comentario del comando.
 * 2. **Demostrarlo**: que la firma o el cuerpo usen de verdad una de esas
 *    cuatro cosas.
 *
 * Pedir las dos es lo que impide que la excepción se convierta en una salida:
 * sin la primera, un comando síncrono pasa sin que nadie lo haya decidido; sin
 * la segunda, basta escribir el comentario para quedarse en el hilo principal
 * sin motivo.
 *
 * # Lo que no comprueba, dicho como tal
 *
 * No entiende Rust: mira texto, como `check-plataforma.mjs`. Reconoce que un
 * comando toca la ventana porque aparece uno de los símbolos de la lista, no
 * porque haya analizado nada, así que un símbolo homónimo lo convencería. Y no
 * dice nada sobre lo que el comando hace **dentro**: un comando asíncrono que
 * quema procesador ya no congela la ventana, pero ocupa un hilo del runtime.
 * Eso es materia de la subfase 5.3, no de aquí.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

const RAIZ = resolve(import.meta.dirname, '..');
const FUENTES = process.argv[2] ? process.argv[2] : join(RAIZ, 'src-tauri', 'src');

/**
 * Lo que obliga a un comando a quedarse en el hilo principal.
 *
 * En Linux, GTK y WebKitGTK solo se pueden tocar desde el hilo que los creó.
 * No es una cuestión de rendimiento: llamarlos desde otro hilo aborta el
 * proceso.
 */
const DEL_HILO_PRINCIPAL = [
  /\bWebviewWindow\b/,
  /\btauri::Window\b/,
  /\bWindow<\s*[A-Za-z]/,
  /\bWindowEvent\b/,
  /\bget_webview_window\s*\(/,
  /\btauri_plugin_dialog\b/,
  /\bDialogExt\b/,
  /\.dialog\s*\(\s*\)/,
  /\bMenuBuilder\b/,
  /\bMenuItem\b/,
  /\bTrayIcon\b/
];

/** La declaración que un comando síncrono tiene que llevar escrita. */
const DECLARACION = /Se queda en el hilo principal:\s*\S/;

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

/**
 * El cuerpo de la función que empieza en `inicio`, contando llaves.
 *
 * Basta con contar: lo que se busca dentro son nombres de tipo, y un tipo
 * dentro de una cadena de texto no cambia la respuesta.
 */
function cuerpo(lineas, inicio) {
  let profundidad = 0;
  let abierto = false;
  const recogidas = [];
  for (let i = inicio; i < lineas.length; i += 1) {
    recogidas.push(lineas[i]);
    for (const caracter of lineas[i]) {
      if (caracter === '{') {
        profundidad += 1;
        abierto = true;
      } else if (caracter === '}') profundidad -= 1;
    }
    if (abierto && profundidad <= 0) break;
  }
  return recogidas.join('\n');
}

/** Los comandos de un archivo, con lo que hace falta para juzgarlos. */
function comandos(archivo) {
  const lineas = readFileSync(archivo, 'utf8').split('\n');
  const encontrados = [];

  for (const [i, linea] of lineas.entries()) {
    const atributo = linea.match(/^\s*#\[(?:tauri::)?command(\((.*)\))?\]\s*$/);
    if (!atributo) continue;

    // Entre el atributo y la firma puede haber otros atributos: `#[must_use]`,
    // `#[allow(...)]`. La firma es la primera línea con `fn`.
    let firma = -1;
    for (let j = i + 1; j < lineas.length && j <= i + 10; j += 1) {
      if (/\bfn\s+[a-z_0-9]+/.test(lineas[j])) {
        firma = j;
        break;
      }
    }
    if (firma === -1) continue;

    const nombre = lineas[firma].match(/\bfn\s+([a-z_0-9]+)/)[1];
    const declaradoAsincrono =
      /\basync\b/.test(atributo[2] ?? '') || /\basync\s+fn\b/.test(lineas[firma]);

    encontrados.push({
      archivo,
      linea: i + 1,
      nombre,
      asincrono: declaradoAsincrono,
      declaracion: lineas
        .slice(Math.max(0, i - COMENTARIO), i)
        .join('\n')
        .split(/\n\s*\n/)
        .pop(),
      codigo: cuerpo(lineas, firma)
    });
  }

  return encontrados;
}

const archivos = archivosRust(FUENTES);
const todos = archivos.flatMap(comandos);
const problemas = [];

for (const comando of todos) {
  if (comando.asincrono) continue;

  const donde = `${relative(RAIZ, comando.archivo)}:${comando.linea}`;
  const toca = DEL_HILO_PRINCIPAL.some((simbolo) => simbolo.test(comando.codigo));
  const declarado = DECLARACION.test(comando.declaracion);

  if (!declarado) {
    problemas.push(
      `  ${donde}  ${comando.nombre} es síncrono y no declara por qué se queda en el hilo principal`
    );
  } else if (!toca) {
    problemas.push(
      `  ${donde}  ${comando.nombre} dice quedarse en el hilo principal, pero no toca ventana,\n` +
        '        diálogo nativo, menú ni bandeja: la excepción no le aplica'
    );
  }
}

// Un guardián que no encuentra nada que vigilar pasa siempre, y eso es peor que
// no tenerlo: da por comprobado lo que dejó de mirar. Mover `ipc.rs` o cambiar
// la forma de declarar un comando bastaría para dejarlo mirando al vacío en
// verde.
if (todos.length === 0) {
  console.error(`No se encontró ningún comando en ${relative(RAIZ, FUENTES) || FUENTES}.`);
  console.error(
    'Un guardián que no vigila nada no es un guardián: o la ruta es la que no es,\n' +
      'o los comandos se declaran de otra forma y esto dejó de comprobarlos.'
  );
  process.exit(1);
}

if (problemas.length > 0) {
  console.error('Hay comandos del puente corriendo en el hilo de la ventana:\n');
  console.error(problemas.join('\n'));
  console.error(
    '\nEn Tauri un comando sin `async` corre en el hilo principal, que es el que\n' +
      'atiende la ventana: mientras dura, la aplicación está congelada. Se arregla\n' +
      'con `#[tauri::command(async)]`. La excepción -ventana, diálogo nativo, menú o\n' +
      'bandeja del sistema- se declara escribiendo "Se queda en el hilo principal:"\n' +
      'con su motivo, y solo vale si el comando toca de verdad alguna de las cuatro.'
  );
  process.exit(1);
}

const enElHilo = todos.filter((comando) => !comando.asincrono).length;
console.log(
  `Comandos: ${todos.length} en el puente, ${todos.length - enElHilo} fuera del hilo de la ventana` +
    (enElHilo > 0 ? `, ${enElHilo} en él con motivo declarado.` : '.')
);
