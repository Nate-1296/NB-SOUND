#!/usr/bin/env node
// Pruebas finales de las revisiones QA-R1, QA-R2 y QA-R3 sobre la copia aislada.
// Lo orquesta scripts/qa/ui-qa.sh revisiones. Cada escenario deja una línea
// QA_R <nombre> {ok, ...}; uno que falla no impide los demás.

import { execFileSync, spawnSync } from 'node:child_process';
import {
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync
} from 'node:fs';

import { Inspector, esperar } from './inspector.mjs';

const ESCENARIOS = process.argv.slice(2);
const DB = process.env.NB_QA_DB;
const QA = process.env.NB_QA_ROOT;
const DISPLAY = process.env.DISPLAY;
const inspector = await Inspector.conectar();

const sql = (c) =>
  execFileSync('sqlite3', ['-readonly', '-separator', '\t', DB, c], { encoding: 'utf8' }).trim();
const filas = (c) =>
  sql(c)
    ? sql(c)
        .split('\n')
        .map((l) => l.split('\t'))
    : [];
const invocar = (c, a = {}) =>
  inspector.evaluar(
    `window.__TAURI_INTERNALS__.invoke(${JSON.stringify(c)}, ${JSON.stringify(a)})`
  );
const js = (e) => inspector.evaluar(e);

async function esperarHasta(prueba, limite, descripcion, cada = 200) {
  const hasta = Date.now() + limite;
  let ultimo;
  while (Date.now() < hasta) {
    try {
      ultimo = await prueba();
      if (ultimo) return ultimo;
    } catch (error) {
      ultimo = String(error);
    }
    await esperar(cada);
  }
  throw new Error(`No se cumplió: ${descripcion}. Último: ${JSON.stringify(ultimo)}`);
}

async function ir(ruta, selector = 'main') {
  const enlace = await js(`Boolean(document.querySelector('a[href="${ruta}"]'))`);
  if (ruta !== '/' && enlace) {
    // Como el usuario: por el enlace, sin recargar la página.
    await js(`(() => { document.querySelector('a[href="${ruta}"]').click(); return true; })()`);
    await esperarHasta(
      () =>
        js(
          `location.pathname + location.search === ${JSON.stringify(ruta)} && Boolean(document.querySelector(${JSON.stringify(selector)}))`
        ),
      15000,
      ruta
    );
    await esperar(600);
    return;
  }
  if (ruta === '/') {
    // Ir a la raíz cambiando location no navega estando ya dentro de la app: se usa
    // el enlace de la barra lateral, como haría el usuario.
    await js(`(() => { document.querySelector('a[href="/"]').click(); return true; })()`);
    await esperarHasta(
      () =>
        js(
          `location.pathname === "/" && Boolean(document.querySelector(${JSON.stringify(selector)}))`
        ),
      15000,
      'Inicio'
    );
    await esperar(600);
    return;
  }
  await inspector.evaluarDirecto(
    `(() => { location.href = ${JSON.stringify(`tauri://localhost${ruta}`)}; return true; })()`
  );
  await esperarHasta(
    () =>
      js(
        `document.readyState === "complete" && Boolean(document.querySelector(${JSON.stringify(selector)}))`
      ),
    15000,
    `la vista ${ruta}`
  );
  await esperar(600);
}

const ventanaPrincipal = () =>
  (
    spawnSync('xdotool', ['search', '--onlyvisible', '--name', '^NB Sound$'], {
      encoding: 'utf8',
      env: { ...process.env, DISPLAY }
    }).stdout ?? ''
  )
    .trim()
    .split('\n')
    .filter(Boolean);

function tecla(nombre) {
  const [id] = ventanaPrincipal();
  execFileSync('xdotool', ['windowactivate', '--sync', id], { env: { ...process.env, DISPLAY } });
  execFileSync('xdotool', ['key', '--window', id, nombre], { env: { ...process.env, DISPLAY } });
}

/** Pone el puntero de verdad sobre el primer elemento que casa con el selector. Forzar
 * `:hover` desde el inspector marca el estado pero WebKit no recalcula los estilos. */
async function raton(selector) {
  const r = await js(`(() => {
    const n = document.querySelector(${JSON.stringify(selector)});
    if (!n) return null;
    n.scrollIntoView({ block: "center" });
    const b = n.getBoundingClientRect();
    return { x: Math.round(b.left + Math.min(b.width / 2, 200)), y: Math.round(b.top + b.height / 2) };
  })()`);
  if (!r) return false;
  const [id] = ventanaPrincipal();
  execFileSync('xdotool', ['mousemove', '--window', id, String(r.x), String(r.y)], {
    env: { ...process.env, DISPLAY }
  });
  await esperar(500);
  return true;
}

async function ratonFuera() {
  const [id] = ventanaPrincipal();
  execFileSync('xdotool', ['mousemove', '--window', id, '5', '5'], {
    env: { ...process.env, DISPLAY }
  });
  await esperar(500);
}

const estilo = (selector, props) =>
  js(`(() => {
    const n = document.querySelector(${JSON.stringify(selector)});
    if (!n) return null;
    const c = getComputedStyle(n);
    return Object.fromEntries(${JSON.stringify(props)}.map((p) => [p, c.getPropertyValue(p)]));
  })()`);

// --- Escenarios ----------------------------------------------------------------------

const ESC = {};

ESC.hover = async () => {
  await ir('/biblioteca?vista=pistas', '.fila');
  await ratonFuera();
  const props = ['opacity', 'visibility'];
  const antes = {
    reproducir: await estilo('.fila .reproducir', props),
    favorita: await estilo('.fila .icono.favorita', props),
    menu: await estilo('.fila .acciones .disparador', props)
  };
  await raton('.fila');
  const con = {
    reproducir: await estilo('.fila .reproducir', props),
    cifra: await estilo('.fila .numero .cifra', props),
    favorita: await estilo('.fila .icono.favorita', props),
    menu: await estilo('.fila .acciones .disparador', props)
  };
  await ratonFuera();
  // Con el teclado: el foco dentro de la fila hace lo mismo.
  await js(
    `(() => { document.querySelector(".fila .acciones .disparador")?.focus(); return true; })()`
  );
  await esperar(300);
  const teclado = {
    reproducir: await estilo('.fila .reproducir', props),
    favorita: await estilo('.fila .icono.favorita', props)
  };
  const visible = (e) => e && e.visibility !== 'hidden' && Number(e.opacity) > 0.5;
  const filaOk =
    !visible(antes.reproducir) &&
    visible(con.reproducir) &&
    !visible(con.cifra) &&
    visible(con.favorita) &&
    visible(con.menu) &&
    visible(teclado.favorita);

  // Inicio: tarjetas, flechas de carrusel y el botón grande cambian al pasar por encima.
  await ir('/', '.carcasa');
  await esperar(1500);
  const cambian = {};
  for (const [nombre, sel] of Object.entries({
    tarjeta: 'main .tarjeta',
    flecha: 'main .boton-avance',
    botonGrande: 'main .podio-play'
  })) {
    const ps = ['transform', 'background-color', 'box-shadow', 'opacity', 'filter', 'scale'];
    const a = await estilo(sel, ps);
    if (!a) {
      cambian[nombre] = 'sin elemento';
      continue;
    }
    const primero = await js(`(() => {
      for (const s of ${JSON.stringify(sel.split(', '))}) if (document.querySelector(s)) return s;
      return null;
    })()`);
    await ratonFuera();
    const a2 = await estilo(primero, ps);
    await raton(nombre === 'botonGrande' ? 'main .podio-tarjeta' : primero);
    const b = await estilo(primero, ps);
    await ratonFuera();
    cambian[nombre] = JSON.stringify(a2) !== JSON.stringify(b);
  }
  return {
    ok: filaOk && Object.values(cambian).every((v) => v === true),
    antes,
    con,
    teclado,
    cambian
  };
};

ESC.menu = async () => {
  await ir('/biblioteca?vista=pistas', '.fila .acciones .disparador');
  await js(
    `(() => { document.querySelector(".fila .acciones .disparador").click(); return true; })()`
  );
  await esperar(400);
  const abierto = await js(`(() => {
    const b = document.querySelector(".fila .acciones .disparador").getBoundingClientRect();
    const m = [...document.querySelectorAll(".menu[popover]")].find((x) => x.matches(":popover-open"));
    if (!m) return null;
    const r = m.getBoundingClientRect();
    return { junto: Math.abs(r.top - b.bottom) < 12 || Math.abs(r.bottom - b.top) < 12, foco: document.activeElement?.getAttribute("role") };
  })()`);
  const antes = await js(`document.activeElement?.textContent.trim()`);
  await js(
    `(() => { document.activeElement.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true })); return true; })()`
  );
  const despues = await js(`document.activeElement?.textContent.trim()`);
  // Escape: las teclas sintéticas no cierran un popover (solo lo hacen las del
  // usuario) y las de xdotool no llegan a Xwayland. Lo que se comprueba es que el
  // menú es un popover «auto», que el navegador cierra con Escape y al pulsar fuera.
  const cerrado = await js(
    `[...document.querySelectorAll(".menu[popover]")].every((x) => x.getAttribute("popover") === "auto")`
  );
  await js(
    `(() => { [...document.querySelectorAll(".menu[popover]")].forEach((x) => x.matches(":popover-open") && x.hidePopover()); return true; })()`
  );
  // Cerca del borde inferior se abre hacia arriba.
  const abajo = await js(`(() => {
    const botones = [...document.querySelectorAll(".fila .acciones .disparador")];
    const b = botones.filter((x) => x.getBoundingClientRect().bottom < innerHeight - 20).at(-1);
    b.click();
    return true;
  })()`);
  await esperar(400);
  const haciaArriba = await js(`(() => {
    const botones = [...document.querySelectorAll(".fila .acciones .disparador")];
    const b = botones.find((x) => x.getAttribute("aria-expanded") === "true").getBoundingClientRect();
    const m = [...document.querySelectorAll(".menu[popover]")].find((x) => x.matches(":popover-open")).getBoundingClientRect();
    return { arriba: m.bottom <= b.top + 2, espacioAbajo: innerHeight - b.bottom, alto: m.height };
  })()`);
  await js(
    `(() => { [...document.querySelectorAll(".menu[popover]")].forEach((x) => x.matches(":popover-open") && x.hidePopover()); return true; })()`
  );
  const ok =
    abierto?.junto &&
    abierto.foco === 'menuitem' &&
    antes !== despues &&
    cerrado &&
    abajo &&
    (haciaArriba.arriba || haciaArriba.espacioAbajo > haciaArriba.alto + 8);
  return { ok, abierto, recorre: [antes, despues], cerrado, haciaArriba };
};

ESC.cabecera = async () => {
  const album = Number(
    sql(`SELECT a.id FROM albumes a JOIN pistas p ON p.album_id = a.id
      WHERE p.estado = 'biblioteca' AND a.portada_id IS NOT NULL LIMIT 1;`)
  );
  const artista = Number(sql(`SELECT artista_id FROM albumes WHERE id = ${album};`));
  const playlist = Number(
    sql(`SELECT playlist_id FROM playlist_pistas GROUP BY playlist_id HAVING count(*) > 2 LIMIT 1;`)
  );
  const vistas = {
    album: `/biblioteca/album?id=${album}`,
    artista: `/biblioteca/artista?id=${artista}`,
    playlist: `/playlists/ver?id=${playlist}`
  };
  const leer = () =>
    js(`(() => {
      const n = document.querySelector("header.franja, .franja, header.cabecera");
      return n ? n.style.getPropertyValue("--m3c-primary") || null : "sin cabecera";
    })()`);
  const con = {};
  for (const [k, v] of Object.entries(vistas)) {
    await ir(v);
    con[k] = await esperarHasta(leer, 8000, `color de ${k}`).catch(() => null);
  }
  await invocar('guardar_preferencia', { clave: 'color_por_portada', valor: false });
  const sin = {};
  for (const [k, v] of Object.entries(vistas)) {
    await ir(v);
    await esperar(1500);
    sin[k] = await leer();
  }
  await invocar('guardar_preferencia', { clave: 'color_por_portada', valor: true });
  const ok =
    Object.values(con).every((c) => c && c !== 'sin cabecera') &&
    Object.values(sin).every((c) => c === null || c === '');
  return { ok, con, sin, vistas };
};

ESC.nombre = async () => {
  await ir('/tu-musica');
  const antes = (await invocar('apariencia')).nombreUsuario;
  const editar = async (texto, teclaFinal) => {
    await js(`(() => {
      const b = [...document.querySelectorAll("main button, main h1, main [role=button]")].find((n) => n.textContent.trim() === ${JSON.stringify(antes)} || n.closest(".nombre"));
      (document.querySelector(".nombre-boton") ?? document.querySelector("main .nombre") ?? b).click();
      return true;
    })()`);
    await esperarHasta(
      () => js(`Boolean(document.querySelector(".nombre-campo"))`),
      5000,
      'el campo del nombre'
    );
    await js(`(() => {
      const c = document.querySelector(".nombre-campo");
      c.value = ${JSON.stringify(texto)};
      c.dispatchEvent(new Event("input", { bubbles: true }));
      c.dispatchEvent(new KeyboardEvent("keydown", { key: ${JSON.stringify(teclaFinal)}, bubbles: true }));
      return true;
    })()`);
    await esperar(800);
    return (await invocar('apariencia')).nombreUsuario;
  };
  const cancelado = await editar('No debe quedar', 'Escape');
  const guardado = await editar('Nate QA', 'Enter');
  await ir('/', '.carcasa');
  const saludo = await esperarHasta(
    () => js(`document.querySelector(".saludo h1")?.textContent`),
    8000,
    'el saludo'
  );
  await ir('/ajustes');
  const ajustes = await esperarHasta(
    () => js(`[...document.querySelectorAll("input")].some((i) => i.value === "Nate QA")`),
    8000,
    'el nombre en Ajustes'
  ).catch(() => false);
  await invocar('guardar_preferencia', { clave: 'nombre_usuario', valor: antes });
  return {
    ok: cancelado === antes && guardado === 'Nate QA' && saludo.includes('Nate QA') && ajustes,
    cancelado,
    guardado,
    saludo,
    ajustes
  };
};

ESC.ancladas = async () => {
  const p = (
    await invocar('playlists_listar', {
      consulta: { texto: null, categoria: null, orden: 'recientes' }
    })
  ).find((x) => !x.anclada);
  await invocar('anclar_playlist', { id: p.id, anclada: true });
  await ir('/playlists', '.boton-densidad');
  const densidades = await js(
    `[...document.querySelectorAll(".boton-densidad")].map((b) => b.getAttribute("aria-label"))`
  );
  const vistos = {};
  for (let i = 0; i < densidades.length; i += 1) {
    await js(
      `(() => { document.querySelectorAll(".boton-densidad")[${i}].click(); return true; })()`
    );
    await esperar(600);
    vistos[densidades[i]] = await js(`document.querySelectorAll(".ancla").length`);
  }
  await invocar('anclar_playlist', { id: p.id, anclada: false });
  return { ok: densidades.length === 4 && Object.values(vistos).every((n) => n >= 1), vistos };
};

ESC.pantalla = async () => {
  const pista = Number(
    sql(
      `SELECT p.id FROM pistas p JOIN letras l ON l.pista_id = p.id WHERE l.sincronizadas <> '' AND p.estado='biblioteca' LIMIT 1;`
    )
  );
  await invocar('reproductor_orden', {
    orden: { tipo: 'reproducirPistas', ids: [pista], desde: 0 }
  });
  await ir(`/reproduciendo?letras`, '.vista');
  await js(
    `(() => { window.dispatchEvent(new KeyboardEvent("keydown", { key: "F11", bubbles: true })); return true; })()`
  );
  await esperar(500);
  await raton('.vista');
  const completa = await js(
    `Boolean(document.fullscreenElement) || document.querySelector(".cabecera-vista") !== null`
  );
  await esperar(4500);
  const r = await js(`(() => {
    const cab = document.querySelector(".cabecera-vista");
    const vista = document.querySelector(".vista").getBoundingClientRect();
    const barra = document.querySelector("section.reproductor");
    const barraVisible = barra && getComputedStyle(barra).visibility !== "hidden" && barra.getBoundingClientRect().height > 0 && Number(getComputedStyle(barra).opacity) > 0.1;
    return { oculta: cab?.classList.contains("oculta"), finVista: vista.bottom, alto: innerHeight, barraVisible };
  })()`);
  await js(
    `(() => { window.dispatchEvent(new KeyboardEvent("keydown", { key: "F11", bubbles: true })); return true; })()`
  );
  await invocar('reproductor_orden', { orden: { tipo: 'pausarReanudar' } });
  return { ok: completa && r.oculta && Math.abs(r.finVista - r.alto) < 2, ...r };
};

ESC.mini = async () => {
  const antes = ventanaPrincipal().length;
  const t0 = Date.now();
  await js(
    `(() => { document.dispatchEvent(new KeyboardEvent("keydown", { key: "m", ctrlKey: true, bubbles: true })); return true; })()`
  );
  const abierta = await esperarHasta(
    async () => {
      const n = spawnSync('xdotool', ['search', '--onlyvisible', '--name', 'NB Sound'], {
        encoding: 'utf8',
        env: { ...process.env, DISPLAY }
      })
        .stdout.trim()
        .split('\n')
        .filter(Boolean).length;
      return n > antes ? n : null;
    },
    5000,
    'el minirreproductor',
    50
  );
  const abrirMs = Date.now() - t0;
  await invocar('dejar_minirreproductor', { volver: false });
  await esperar(800);
  const t1 = Date.now();
  await js(
    `(() => { document.dispatchEvent(new KeyboardEvent("keydown", { key: "m", ctrlKey: true, bubbles: true })); return true; })()`
  );
  await esperarHasta(
    async () => {
      const n = spawnSync('xdotool', ['search', '--onlyvisible', '--name', 'NB Sound'], {
        encoding: 'utf8',
        env: { ...process.env, DISPLAY }
      })
        .stdout.trim()
        .split('\n')
        .filter(Boolean).length;
      return n > antes ? n : null;
    },
    5000,
    'el minirreproductor otra vez',
    50
  );
  const reabrirMs = Date.now() - t1;
  await invocar('dejar_minirreproductor', { volver: true });
  await esperar(800);
  const activa = spawnSync('xdotool', ['getactivewindow', 'getwindowname'], {
    encoding: 'utf8',
    env: { ...process.env, DISPLAY }
  }).stdout.trim();
  return {
    ok: abrirMs < 1500 && reabrirMs < 500 && activa === 'NB Sound',
    abierta,
    abrirMs,
    reabrirMs,
    activa
  };
};

ESC.cola = async () => {
  const ids = sql(`SELECT id FROM pistas WHERE estado='biblioteca' ORDER BY id LIMIT 200;`)
    .split('\n')
    .map(Number);
  await invocar('reproductor_orden', { orden: { tipo: 'reproducirPistas', ids, desde: 0 } });
  await invocar('reproductor_orden', { orden: { tipo: 'pausarReanudar' } });
  await ir('/', '.carcasa');
  await js(
    `(() => { document.querySelector("section.reproductor .control.cola").click(); return true; })()`
  );
  await esperarHasta(
    () => js(`document.querySelectorAll(".panel .fila").length > 5`),
    5000,
    'la cola abierta'
  );
  const r = await js(`(() => {
    const lista = document.querySelector(".panel .fila").parentElement;
    const caja = lista.getBoundingClientRect();
    const util = caja.left + lista.clientWidth;
    const filas = [...document.querySelectorAll(".panel .fila")].slice(0, 8);
    const tapadas = filas.filter((f) => [...f.querySelectorAll("button, .duracion")].some((n) => n.getBoundingClientRect().right > util + 0.5)).length;
    return { barra: lista.offsetWidth - lista.clientWidth, tapadas };
  })()`);
  await js(
    `(() => { document.querySelector("section.reproductor .control.cola").click(); return true; })()`
  );
  // Con el cajón del karaoke abierto, lo de debajo no muestra su barra encima.
  await ir('/biblioteca?vista=pistas', '.fila');
  await js(`(() => { document.querySelector(".boton-karaoke").click(); return true; })()`);
  await esperar(800);
  const debajo = await js(`(() => {
    const d = document.querySelector("dialog[open]");
    if (!d) return null;
    const r = d.getBoundingClientRect();
    // Lo que está en el punto del borde izquierdo del cajón es el cajón, no una barra de debajo.
    const el = document.elementFromPoint(r.left + 2, r.top + r.height / 2);
    return { encima: d.contains(el), modal: d.matches(":modal") };
  })()`);
  tecla('Escape');
  return { ok: r.tapadas === 0 && debajo?.encima && debajo.modal, ...r, debajo };
};

ESC.desplazar = async () => {
  const medir = async (ruta, selector, contenedor) => {
    await ir(ruta, selector);
    return js(`new Promise((resolve) => {
      const c = ${contenedor};
      const tiempos = [];
      let anterior = performance.now();
      let n = 0;
      const paso = (t) => {
        tiempos.push(t - anterior);
        anterior = t;
        c.scrollTop += 600;
        n += 1;
        if (n < 150) requestAnimationFrame(paso);
        else {
          const t = tiempos.slice(2);
          // Sostenido: dos fotogramas largos seguidos. Uno suelto, al cargar un tramo
          // nuevo de la lista virtual, no se nota.
          const seguidos = t.filter((x, i) => x > 50 && t[i - 1] > 50).length;
          resolve({ fotogramas: tiempos.length, maximo: Math.max(...t), largos: t.filter((x) => x > 50).length, seguidos });
        }
      };
      requestAnimationFrame(paso);
    })`);
  };
  const desplazable = `(() => { const c = [...document.querySelectorAll("main, main *")].find((n) => n.scrollHeight > n.clientHeight + 100 && /auto|scroll/.test(getComputedStyle(n).overflowY)); return c ?? document.scrollingElement; })()`;
  const pistas = await medir('/biblioteca?vista=pistas', '.fila', desplazable);
  const albumes = await medir('/biblioteca?vista=albumes', 'main', desplazable);
  const playlists = await medir('/playlists', 'main', desplazable);
  // Volver a una vista ya visitada la muestra al momento, con lo de antes.
  await ir('/playlists', 'main');
  const t = Date.now();
  await inspector.evaluarDirecto(
    `(() => { location.href = "tauri://localhost/biblioteca?vista=pistas"; return true; })()`
  );
  await esperarHasta(
    () => js(`document.querySelectorAll(".fila").length > 5`),
    5000,
    'las filas al volver',
    10
  );
  const volverMs = Date.now() - t;
  const ok = [pistas, albumes, playlists].every((m) => m.seguidos === 0 && m.maximo < 100);
  return { ok, pistas, albumes, playlists, volverMs };
};

ESC.barra720 = async () => {
  // KWin virtual no deja cambiar el tamaño de la ventana desde fuera; las barras
  // deciden por su propio ancho (`anchos.ts`), así que se estrecha la página.
  await js(`(() => { document.body.style.width = "720px"; return true; })()`);
  await esperar(1200);
  const ancho = await js(
    'document.querySelector("section.reproductor").getBoundingClientRect().width'
  );
  await js(
    `(() => { [...document.querySelectorAll("section.reproductor button")].find((b) => b.getAttribute("aria-haspopup") === "menu" && /opciones/i.test(b.getAttribute("aria-label") ?? "")).click(); return true; })()`
  );
  await esperar(500);
  const controles = await js(`document.querySelectorAll(".menu .controles .control").length`);
  const etiquetas = await js(
    `[...document.querySelectorAll(".menu .controles .control")].map((b) => b.getAttribute("aria-label"))`
  );

  await js(
    `(() => { [...document.querySelectorAll(".menu .controles .control")].find((b) => b.getAttribute("aria-label") === "Letras").click(); return true; })()`
  );
  await esperar(800);
  const cerrado = await js(`!document.querySelector(".menu .controles")`);
  const ruta = await js('location.pathname + location.search');
  await js(`(() => { document.body.style.width = ""; return true; })()`);
  return {
    ok: ancho <= 730 && controles >= 4 && cerrado && ruta.includes('reproduciendo'),
    ancho,
    etiquetas,
    cerrado,
    ruta
  };
};

ESC.duplicados = async () => {
  const n = await invocar('buscar_duplicados');
  const apartadas = filas(
    `SELECT id, titulo, artista_nombre, album_titulo, duracion_seg FROM pistas WHERE estado = 'duplicado';`
  );
  const sinGemela = [];
  for (const [id, , , , dur] of apartadas) {
    const gemela = sql(`SELECT count(*) FROM pistas b JOIN pistas a ON a.id = ${id}
        WHERE b.estado = 'biblioteca' AND lower(b.titulo) = lower(a.titulo)
          AND lower(b.artista_nombre) = lower(a.artista_nombre) AND lower(coalesce(b.album_titulo,'')) = lower(coalesce(a.album_titulo,''))
          AND abs(b.duracion_seg - ${dur}) <= 2;`);
    if (gemela === '0') sinGemela.push(id);
  }
  return { ok: sinGemela.length === 0, apartadasAhora: n, apartadas: apartadas.length, sinGemela };
};

ESC.karaoke = async () => {
  const lista = Number(
    sql(
      `SELECT s.pista_id FROM stems s JOIN pistas p ON p.id = s.pista_id WHERE s.estado='lista' AND p.estado='biblioteca' LIMIT 1;`
    )
  );
  await invocar('reproductor_orden', {
    orden: { tipo: 'reproducirPistas', ids: [lista], desde: 0 }
  });
  await esperarHasta(
    async () => (await invocar('reproductor_estado'))?.karaokeDisponible,
    10000,
    'karaoke disponible'
  );
  await ir('/', '.carcasa');
  await js(`(() => { document.querySelector(".boton-karaoke").click(); return true; })()`);
  await esperar(800);
  const textoBoton = () =>
    js(
      `[...document.querySelectorAll("dialog[open] button[aria-pressed]")].map((b) => b.textContent.trim())[0] ?? null`
    );
  const antes = await textoBoton();
  await js(
    `(() => { document.querySelector("dialog[open] button[aria-pressed]").click(); return true; })()`
  );
  await esperar(800);
  const despues = await textoBoton();
  const activo = (await invocar('reproductor_estado')).karaokeActivo;
  await js(
    `(() => { document.querySelector("dialog[open] button[aria-pressed]").click(); return true; })()`
  );
  await js(
    `(() => { [...document.querySelectorAll("dialog[open] button")].find((b) => /Verlas|biblioteca/i.test(b.textContent)).click(); return true; })()`
  );
  await esperar(1200);
  const ruta = await js('location.pathname + location.search');
  // Varias pedidas: la primera con su porcentaje y las demás en espera.
  const sin = sql(
    `SELECT id FROM pistas WHERE estado='biblioteca' AND id NOT IN (SELECT pista_id FROM stems) AND duracion_seg BETWEEN 120 AND 200 LIMIT 3;`
  )
    .split('\n')
    .map(Number);
  await invocar('karaoke_preparar', { pistas: sin });
  await js(`(() => { document.querySelector(".boton-karaoke").click(); return true; })()`);
  const turnos = await esperarHasta(
    async () => {
      const t = await js(
        `[...document.querySelectorAll("dialog[open] .cola li .turno")].map((n) => n.textContent.trim())`
      );
      return t.length >= 3 && /%/.test(t[0]) ? t : null;
    },
    60000,
    'la cola del karaoke',
    500
  );
  const primera = (await invocar('karaoke_estado')).preparando?.pista;
  tecla('Escape');
  writeFileSync(`${QA}/informes/revision-karaoke.json`, JSON.stringify({ primera }));
  const ok =
    antes &&
    despues &&
    antes !== despues &&
    activo &&
    ruta.includes('cantar=1') &&
    turnos.slice(1).every((t) => !/%/.test(t));
  return { ok, antes, despues, activo, ruta, turnos, primera };
};

ESC['karaoke-reabierto'] = async () => {
  const { primera } = JSON.parse(readFileSync(`${QA}/informes/revision-karaoke.json`, 'utf8'));
  const sigue = await esperarHasta(
    async () => (await invocar('karaoke_estado')).preparando?.pista,
    30000,
    'la preparación tras reabrir'
  );
  return { ok: sigue === primera, primera, sigue };
};

ESC.papelera = async () => {
  const fuentes = `${QA}/fase4/fuentes/papelera`;
  const antes = Number(sql('SELECT coalesce(max(id),0) FROM pistas;'));
  await invocar('qa_importar_carpeta', { ruta: fuentes });
  const [id, ruta] = await esperarHasta(
    async () =>
      filas(`SELECT id, ruta FROM pistas WHERE id > ${antes} AND titulo = 'QA Papelera';`)[0],
    30000,
    'la pista sintética'
  );
  const lista = await invocar('crear_playlist', { nombre: 'QA IA papelera', descripcion: null });
  await invocar('agregar_a_playlist', { id: lista, pistas: [Number(id)] }).catch(() =>
    invocar('agregar_a_playlist', { playlistId: lista, pistaIds: [Number(id)] })
  );
  await invocar('reproductor_orden', {
    orden: { tipo: 'agregar', ids: [Number(id)], justoDespues: false }
  });
  await invocar('borrar_pista', { id: Number(id), borrarArchivo: true });
  const nombre = ruta.split('/').at(-1);
  const papelera = `${process.env.HOME}/.local/share/Trash`;
  const enPapelera = readdirSync(`${papelera}/files`).find((f) =>
    f.startsWith(nombre.replace(/\.mp3$/, ''))
  );
  const info = enPapelera ? readFileSync(`${papelera}/info/${enPapelera}.trashinfo`, 'utf8') : '';
  const origen = decodeURIComponent(info.match(/^Path=(.*)$/m)?.[1] ?? '');
  // Restaurar: vuelve a su sitio y la papelera queda como estaba.
  let restaurada = false;
  if (enPapelera && origen) {
    mkdirSync(origen.slice(0, origen.lastIndexOf('/')), { recursive: true });
    renameSync(`${papelera}/files/${enPapelera}`, origen);
    rmSync(`${papelera}/info/${enPapelera}.trashinfo`);
    restaurada = existsSync(origen);
    rmSync(origen);
  }
  const enLista = sql(`SELECT count(*) FROM playlist_pistas WHERE pista_id = ${id};`);
  const enCola = (await invocar('reproductor_estado')).cola.includes(Number(id));
  const tumba = sql(`SELECT count(*) FROM tumbas WHERE entidad = 'pista' AND entidad_id = ${id};`);
  await invocar('borrar_playlist', { id: lista });
  return {
    ok: Boolean(enPapelera) && restaurada && enLista === '0' && !enCola && tumba !== '0',
    enPapelera,
    restaurada,
    enLista,
    enCola,
    tumba
  };
};

ESC.cancelar = async () => {
  const fuentes = `${QA}/fase4/fuentes/lote`;
  const antes = Number(sql("SELECT count(*) FROM pistas WHERE titulo LIKE 'QA Lote %';"));
  await invocar('qa_importar_carpeta', { ruta: fuentes });
  await esperarHasta(
    async () => ((await invocar('importacion_progreso')).hechos >= 15 ? true : null),
    120000,
    'quince hechas',
    100
  );
  await invocar('importacion_cancelar');
  await esperarHasta(
    async () => (!(await invocar('importacion_progreso')).activa ? true : null),
    30000,
    'la importación parada'
  );
  const importadas =
    Number(sql("SELECT count(*) FROM pistas WHERE titulo LIKE 'QA Lote %';")) - antes;
  const pendientes = Number(sql('SELECT count(*) FROM pendientes_importacion;'));
  writeFileSync(`${QA}/informes/revision-cancelar.json`, JSON.stringify({ antes, importadas }));
  return { ok: importadas > 0 && importadas < 120 && pendientes === 0, importadas, pendientes };
};

ESC['cancelar-reabierto'] = async () => {
  const { antes, importadas } = JSON.parse(
    readFileSync(`${QA}/informes/revision-cancelar.json`, 'utf8')
  );
  await esperar(15000);
  const ahora = Number(sql("SELECT count(*) FROM pistas WHERE titulo LIKE 'QA Lote %';")) - antes;
  const activa = (await invocar('importacion_progreso')).activa;
  return { ok: ahora === importadas && !activa, importadas, ahora, activa };
};

ESC.foto = async () => {
  await ir('/tu-musica');
  const src = await esperarHasta(
    () =>
      js(
        `[...document.querySelectorAll("main img")].map((i) => i.src).find((s) => /perfil|foto/.test(s)) ?? null`
      ),
    8000,
    'la foto en Tu música'
  );
  const cargada = await js(
    `[...document.querySelectorAll("main img")].find((i) => /perfil|foto/.test(i.src))?.naturalWidth ?? 0`
  );
  return { ok: cargada > 0, src, ancho: cargada };
};

ESC.bienvenida = async () => {
  const bienvenida = await esperarHasta(
    () =>
      js(
        `document.querySelector("section.bienvenida") ? document.querySelector("section.bienvenida").innerText.slice(0, 80) : null`
      ),
    15000,
    'la bienvenida'
  );
  return { ok: Boolean(bienvenida), bienvenida };
};

ESC['bienvenida-carpeta'] = async () => {
  // Con la carpeta ya elegida (lo que hace el selector), lo que se copia en ella entra
  // solo y suena sin reiniciar: el defecto de la instalación nueva que vio Nathan.
  const pista = await esperarHasta(
    () => filas("SELECT id FROM pistas WHERE titulo = 'QA Bienvenida';")[0]?.[0],
    90000,
    'la canción vigilada',
    1000
  );
  await invocar('reproductor_orden', {
    orden: { tipo: 'reproducirPistas', ids: [Number(pista)], desde: 0 }
  });
  const suena = await esperarHasta(
    async () => {
      const e = await invocar('reproductor_estado');
      return e?.estado === 'reproduciendo' && e.posicionSeg > 0.5 ? e.posicionSeg : null;
    },
    10000,
    'que suene'
  );
  return { ok: true, pista, suena };
};

ESC.revisar = async () => {
  await ir('/por-revisar', '.vista');
  const r = await esperarHasta(
    () =>
      js(`(() => {
    const b = [...document.querySelectorAll(".vista button")].find((x) => /^Otras? \\d+ versi/.test(x.textContent.trim()));
    if (!b) return null;
    const antes = document.querySelectorAll(".candidatas li").length;
    b.click();
    return { boton: b.textContent.trim(), antes };
  })()`),
    8000,
    'el botón de otras versiones'
  );
  await esperar(500);
  const desplegadas = await js(`document.querySelectorAll(".candidatas li").length`);
  await js(
    `(() => { [...document.querySelectorAll(".vista button")].find((x) => /Menos versiones/.test(x.textContent)).click(); return true; })()`
  );
  await esperar(500);
  const plegadas = await js(`document.querySelectorAll(".candidatas li").length`);
  return { ok: desplegadas > r.antes && plegadas === r.antes, ...r, desplegadas, plegadas };
};

// La ventana tarda un poco en verse después de que el inspector ya responde.
await esperarHasta(
  async () => ventanaPrincipal().length > 0 || null,
  20000,
  'la ventana visible'
).catch(() => {});
await esperar(1000);

for (const nombre of ESCENARIOS) {
  try {
    const r = await ESC[nombre]();
    console.log('QA_R', nombre, JSON.stringify(r));
  } catch (error) {
    console.log('QA_R', nombre, JSON.stringify({ ok: false, error: String(error).slice(0, 400) }));
  }
}
inspector.cerrar();
