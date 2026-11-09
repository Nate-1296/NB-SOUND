#!/usr/bin/env node
// Pruebas finales de la Fase 8 (forma de onda, inteligentes, resumen de escucha y
// modo fiesta) sobre la copia aislada. Lo orquesta scripts/qa/ui-qa.sh fase8; la
// tarjeta SVG y la copia a un dispositivo pasan por un selector nativo y las hace
// tests/qa_fase8.rs.

import { execFileSync, spawn } from 'node:child_process';
import { readdirSync, readFileSync } from 'node:fs';
import { request as httpRequest } from 'node:http';
import { request as httpsRequest, Agent as HttpsAgent } from 'node:https';

import { Inspector, esperar } from './inspector.mjs';

const ESCENARIO = process.argv[2];
const DB = process.env.NB_QA_DB;
const RAIZ = process.env.NB_QA_RAIZ;
const QA = process.env.NB_QA_ROOT;
const INFORMES = process.env.NB_QA_INFORMES;
const APP_PID = Number(process.env.NB_QA_APP_PID ?? 0);
const CERT_PATH = process.env.NB_QA_CERT_PATH ?? '';
const inspector = await Inspector.conectar();

const sql = (c) =>
  execFileSync('sqlite3', ['-readonly', '-separator', '\t', DB, c], { encoding: 'utf8' }).trim();
const invocar = (c, a = {}) =>
  inspector.evaluar(
    `window.__TAURI_INTERNALS__.invoke(${JSON.stringify(c)}, ${JSON.stringify(a)})`
  );

async function esperarHasta(prueba, limite, descripcion, cada = 300) {
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

async function ir(ruta) {
  await inspector.evaluarDirecto(
    `(() => { location.href = ${JSON.stringify(`tauri://localhost${ruta}`)}; return true; })()`
  );
  await esperarHasta(
    () =>
      inspector.evaluar(
        `document.readyState === "complete" && Boolean(document.querySelector("main"))`
      ),
    15000,
    ruta
  );
  await esperar(500);
}

function analizar(prueba, variables) {
  const salida = execFileSync(
    'cargo',
    [
      'test',
      '--manifest-path',
      `${RAIZ}/src-tauri/Cargo.toml`,
      '--test',
      'qa_audio',
      prueba,
      '--',
      '--ignored',
      '--nocapture',
      '--test-threads=1'
    ],
    { cwd: `${RAIZ}/src-tauri`, encoding: 'utf8', env: { ...process.env, ...variables } }
  );
  const linea = salida.split('\n').find((l) => l.includes('INFORME_QA'));
  return JSON.parse(linea.replace(/^.*INFORME_QA /, '')).datos;
}

function indiceFlujoApp() {
  const texto = execFileSync('pactl', ['list', 'sink-inputs'], { encoding: 'utf8' });
  for (const bloque of texto.split(/\n\n+/)) {
    if (!bloque.includes('application.name = "PipeWire ALSA [nb-sound]"')) continue;
    const indice = bloque.match(/^Sink Input #(\d+)/m)?.[1];
    if (indice) return Number(indice);
  }
  return null;
}

async function grabar(ruta, segundos) {
  const indice = await esperarHasta(async () => indiceFlujoApp(), 10000, 'flujo de audio');
  execFileSync('pactl', ['move-sink-input', String(indice), 'nb_sound_qa_ui']);
  const p = spawn(
    'parec',
    [
      `--monitor-stream=${indice}`,
      '--file-format=wav',
      '--rate=48000',
      '--channels=2',
      '--format=float32le',
      '--latency-msec=20',
      ruta
    ],
    { stdio: 'ignore' }
  );
  await esperar(segundos * 1000);
  const salida = new Promise((r) => p.once('exit', r));
  p.kill('SIGINT');
  await Promise.race([salida, esperar(3000)]);
}

function ticksHilo(nombre) {
  const carpeta = `/proc/${APP_PID}/task`;
  for (const tid of readdirSync(carpeta)) {
    if (readFileSync(`${carpeta}/${tid}/comm`, 'utf8').trim() !== nombre) continue;
    const t = readFileSync(`${carpeta}/${tid}/stat`, 'utf8');
    const r = t
      .slice(t.lastIndexOf(')') + 2)
      .trim()
      .split(/\s+/);
    return Number(r[11]) + Number(r[12]);
  }
  return 0;
}

// --- Forma de onda (F8.1) --------------------------------------------------------------

async function formaDeOnda() {
  const pistas = sql(`SELECT p.id, p.ruta FROM pistas p JOIN sonoridad s ON s.pista_id = p.id
      WHERE p.estado = 'biblioteca' AND length(s.picos) = 1000 AND p.ruta NOT LIKE 'qa/%'
      ORDER BY p.id LIMIT 10;`)
    .split('\n')
    .map((l) => l.split('\t'));
  const correlaciones = [];
  for (const [id, ruta] of pistas) {
    const picos = await invocar('forma_de_onda', { pistaId: Number(id) });
    const r = analizar('la_forma_de_onda_sigue_al_audio', {
      NB_QA_FUENTE: `${QA}/biblioteca/${ruta}`,
      NB_QA_PICOS: JSON.stringify(picos)
    });
    correlaciones.push(Number(r.correlacion.toFixed(3)));
  }
  if (correlaciones.length !== 10)
    throw new Error(`Solo ${correlaciones.length} pistas con forma de onda`);

  // En una sesión del DJ, la barra marca la entrada y la salida de la que suena.
  await inspector.evaluarDirecto(`(() => {
    window.__qaPedido = null;
    window.__TAURI_INTERNALS__.invoke("dj_pedir", { peticion: "algo alegre", minutos: 20 })
      .then((r) => (window.__qaPedido = r));
    return true;
  })()`);
  const pedido = await esperarHasta(
    () => inspector.evaluar('window.__qaPedido'),
    120000,
    'la sesión'
  );
  const dj = await esperarHasta(
    async () => (await invocar('reproductor_estado'))?.dj,
    15000,
    'la sesión sonando'
  );
  const marcas = await esperarHasta(
    () =>
      inspector.evaluar(`(() => {
      const barra = document.querySelector("section.reproductor");
      const t = barra?.querySelectorAll("[class*=entrada], [class*=salida]") ?? [];
      return t.length >= 2 ? [...t].map((n) => n.className) : null;
    })()`),
    10000,
    'las marcas del DJ en la barra'
  ).catch(() => null);
  await invocar('dj_descartar', { sesionId: pedido.sesionId });

  // Poblar los picos de toda la biblioteca en segundo plano no se nota.
  const pendientesAntes = Number(sql('SELECT count(*) FROM sonoridad WHERE picos IS NULL;'));
  const fondo = Number(process.env.NB_QA_PISTA_FONDO);
  await invocar('reproductor_orden', {
    orden: { tipo: 'reproducirPistas', ids: [fondo], desde: 0 }
  });
  const t0 = ticksHilo('sonoridad');
  const inicio = Date.now();
  const wav = `${INFORMES}/fase8-picos.wav`;
  await grabar(wav, 60);
  const cpu = ((ticksHilo('sonoridad') - t0) / 100 / ((Date.now() - inicio) / 1000)) * 100;
  const pendientesDespues = Number(sql('SELECT count(*) FROM sonoridad WHERE picos IS NULL;'));
  const audio = analizar('una_reproduccion_continua_no_tiene_huecos', { NB_QA_WAV: wav });
  if (cpu >= 100) throw new Error(`La medición usó ${cpu} % de un núcleo`);
  if (!(pendientesDespues < pendientesAntes)) throw new Error('No avanzaron los picos pendientes');
  console.log(
    'QA_F8_FORMA',
    JSON.stringify({
      correlaciones,
      dj: { entrada: dj.entradaSeg, salida: dj.salidaSeg, marcas },
      picos: { pendientesAntes, pendientesDespues, cpu },
      audio: { huecos: audio.huecosMs, discontinuidades: audio.discontinuidades }
    })
  );
}

// --- Inteligentes (F8.2), con el cliente del teléfono ----------------------------------

let base = '';
let token = '';
let pem = '';
const agente = new HttpsAgent({ keepAlive: true, maxSockets: 1 });

function peticionMovil(ruta, metodo = 'GET', cuerpo) {
  return new Promise((resolve, reject) => {
    const datos = cuerpo === undefined ? null : JSON.stringify(cuerpo);
    const url = new URL(ruta, base);
    const s = httpsRequest(
      {
        hostname: url.hostname,
        port: url.port,
        path: url.pathname + url.search,
        method: metodo,
        agent: agente,
        ca: pem,
        servername: 'nbsound.local',
        checkServerIdentity: () => undefined,
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(datos
            ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(datos) }
            : {})
        }
      },
      (r) => {
        const partes = [];
        r.on('data', (p) => partes.push(p));
        r.on('end', () => {
          const texto = Buffer.concat(partes).toString('utf8');
          let json = null;
          try {
            json = JSON.parse(texto);
          } catch {
            /* el estado basta */
          }
          resolve({ estado: r.statusCode, json, texto });
        });
      }
    );
    s.on('error', reject);
    if (datos) s.write(datos);
    s.end();
  });
}

async function emparejarMovil() {
  pem = readFileSync(CERT_PATH, 'utf8');
  const emparejar = await invocar('movil_emparejar');
  const estado = await invocar('movil_estado');
  base = `https://${estado.direccion}`;
  const p = await peticionMovil('/api/v1/pair', 'POST', {
    codigo: emparejar.codigo,
    nombre_dispositivo: 'QA IA Fase 8',
    plataforma: 'android'
  });
  if (p.estado !== 200) throw new Error(`No se pudo emparejar: ${p.estado} ${p.texto}`);
  token = p.json.device_token;
}

async function manifest(since) {
  const r = await peticionMovil(`/api/v1/manifest?since=${since}&limit=5000`);
  if (r.estado !== 200) throw new Error(`manifest ${r.estado}`);
  return r.json;
}

const regla = (animo, soloFavoritas) => ({
  bpmMin: 90,
  bpmMax: 140,
  energiaMin: null,
  energiaMax: null,
  animo,
  conInstrumental: null,
  soloFavoritas,
  reproduccionesMin: null,
  reproduccionesMax: null,
  escuchadaEnDias: null,
  sinEscucharDias: null,
  anioMin: null,
  anioMax: null,
  genero: null,
  orden: 'bpmAsc',
  limite: 200
});

const pistasDe = async (id) =>
  (await invocar('playlist_pistas', { id, desde: 0, limite: 500 })) ?? [];

async function inteligentes() {
  await emparejarMovil();
  const inicio = (await manifest(0)).sync_version_actual;
  // El ánimo con más candidatas, para que la regla tenga de dónde elegir.
  let elegido = null;
  for (const animo of [
    'bailable',
    'energetica',
    'feliz',
    'fiesta',
    'tranquila',
    'intensa',
    'nocturna',
    'triste'
  ]) {
    const todas = await invocar('crear_playlist_inteligente', {
      nombre: `QA sondeo ${animo}`,
      descripcion: null,
      regla: regla(animo, false)
    });
    const lista = await pistasDe(todas);
    const ids = lista.pistas.map((p) => p.id);
    await invocar('borrar_playlist', { id: todas });
    if (ids.length >= 5) {
      elegido = { animo, ids };
      break;
    }
  }
  if (!elegido) throw new Error('Ningún ánimo da cinco pistas entre 90 y 140 BPM');
  const favoritasAntes = new Set(
    sql('SELECT id FROM pistas WHERE favorita = 1;').split('\n').map(Number)
  );
  const nueva = elegido.ids.find((id) => !favoritasAntes.has(id));
  const id = await invocar('crear_playlist_inteligente', {
    nombre: 'QA IA inteligente',
    descripcion: null,
    regla: regla(elegido.animo, true)
  });
  const antes = (await pistasDe(id)).pistas.map((p) => p.id);
  const delta1 = await manifest(inicio);
  const recibida = delta1.playlists.find((p) => p.id === id);
  if (!recibida) throw new Error('El teléfono no recibió la inteligente');
  await invocar('fijar_favorita', { pistaId: nueva, favorita: true });
  const despues = await esperarHasta(
    async () => {
      const l = await pistasDe(id);
      const ids = l.pistas.map((p) => p.id);
      return ids.includes(nueva) ? ids : null;
    },
    15000,
    'la favorita nueva dentro de la inteligente'
  );
  const delta2 = await esperarHasta(
    async () => {
      const m = await manifest(delta1.sync_version_actual);
      const p = m.playlists.find((x) => x.id === id);
      return p?.pista_ids?.includes(nueva) ? p : null;
    },
    15000,
    'el teléfono recibe la favorita nueva en la inteligente'
  );
  await invocar('fijar_favorita', { pistaId: nueva, favorita: false });
  await invocar('borrar_playlist', { id });

  // Crear para mí.
  const creadas = await invocar('regenerar_playlists_automaticas');
  const automaticas = Number(
    sql("SELECT count(*) FROM playlists WHERE tipo = 'automatica' AND origen = 'generado';") || 0
  );
  console.log(
    'QA_F8_INTELIGENTES',
    JSON.stringify({
      animo: elegido.animo,
      candidatas: elegido.ids.length,
      antes: antes.length,
      despues: despues.length,
      nueva,
      enElTelefono: delta2.pista_ids.length,
      creadasParaMi: creadas,
      automaticas
    })
  );
}

// --- Resumen de escucha (F8.3) ----------------------------------------------------------

async function resumen() {
  const todo = await invocar('resumen_escucha', { periodo: null });
  const anio = todo.periodosDisponibles.find((p) => /^\d{4}$/.test(p));
  const mes = todo.periodosDisponibles.find((p) => /^\d{4}-\d{2}$/.test(p));
  const porAnio = await invocar('resumen_escucha', { periodo: anio });
  const porMes = mes ? await invocar('resumen_escucha', { periodo: mes }) : null;
  const historial = Number(
    sql(`SELECT count(*) FROM historial WHERE strftime('%Y', reproducida_en) = '${anio}';`) || -1
  );
  if (todo.mapaCalor.length !== 168)
    throw new Error(`El mapa de calor tiene ${todo.mapaCalor.length} celdas`);
  if (todo.mapaCalor.reduce((a, b) => a + b, 0) !== todo.reproducciones) {
    throw new Error('El mapa de calor no suma las reproducciones');
  }
  await ir('/tu-musica');
  const dom = await esperarHasta(
    () =>
      inspector.evaluar(`(() => {
    const svgs = document.querySelectorAll("main svg").length;
    const celdas = document.querySelectorAll("[class*=calor] [class*=celda], [class*=mapa] rect, [class*=calor] rect").length;
    return svgs > 0 ? { svgs, celdas } : null;
  })()`),
    15000,
    'el radar y el mapa en Tu música'
  );
  console.log(
    'QA_F8_RESUMEN',
    JSON.stringify({
      periodos: todo.periodosDisponibles.length,
      anio,
      reproduccionesAnio: porAnio.reproducciones,
      historialAnio: historial,
      mes,
      reproduccionesMes: porMes?.reproducciones ?? null,
      radar: Object.keys(todo.radar).length,
      mapaCalor: todo.mapaCalor.length,
      dom
    })
  );
}

// --- Modo fiesta (F8.5) ------------------------------------------------------------------

function http(url, metodo = 'GET', cabeceras = {}, cuerpo) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const datos = cuerpo === undefined ? null : JSON.stringify(cuerpo);
    const s = httpRequest(
      {
        hostname: u.hostname,
        port: u.port,
        path: u.pathname + u.search,
        method: metodo,
        headers: {
          ...cabeceras,
          ...(datos
            ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(datos) }
            : {})
        }
      },
      (r) => {
        const partes = [];
        r.on('data', (p) => partes.push(p));
        r.on('end', () =>
          resolve({ estado: r.statusCode, texto: Buffer.concat(partes).toString('utf8') })
        );
      }
    );
    s.on('error', reject);
    if (datos) s.write(datos);
    s.end();
  });
}

async function fiesta() {
  let e = await invocar('fiesta_encender', { activo: true });
  if (!e.activo || !e.url || !e.qr)
    throw new Error(`La fiesta no se encendió: ${JSON.stringify(e)}`);
  const url = new URL(e.url);
  const tokenFiesta = url.pathname.split('/').at(-1);
  const h = { 'x-fiesta-token': tokenFiesta };
  const pagina = await http(e.url);
  const busqueda = await http(`${url.origin}/api/buscar?q=amor`, 'GET', h);
  const encontradas = JSON.parse(busqueda.texto);
  const lista = encontradas.pistas ?? encontradas.resultados ?? encontradas;
  const ids = lista.slice(0, 3).map((p) => p.id ?? p.pistaId);
  // Entre dos sugerencias del mismo invitado hay diez segundos de espera
  // (ENFRIAMIENTO_SUGERENCIA): se comprueba que la segunda antes de tiempo se frena.
  let frenada = null;
  for (const [k, id] of ids.slice(0, 2).entries()) {
    if (k > 0) {
      frenada = (await http(`${url.origin}/api/sugerir`, 'POST', h, { pistaId: id, alias: 'QA' }))
        .estado;
      await esperar(10500);
    }
    const r = await http(`${url.origin}/api/sugerir`, 'POST', h, { pistaId: id, alias: 'QA' });
    if (r.estado !== 200) throw new Error(`Sugerir respondió ${r.estado}: ${r.texto}`);
  }
  e = await esperarHasta(
    async () => {
      const x = await invocar('fiesta_estado');
      return x.sugerencias.length >= 2 ? x : null;
    },
    5000,
    'las sugerencias en NB Sound'
  );
  const [a, b] = e.sugerencias;
  const colaAntes = (await invocar('reproductor_estado'))?.cola ?? [];
  await invocar('fiesta_resolver_sugerencia', { id: a.id, aceptar: true, bloquear: false });
  await invocar('fiesta_resolver_sugerencia', { id: b.id, aceptar: false, bloquear: false });
  const colaDespues = (await invocar('reproductor_estado'))?.cola ?? [];
  if (!colaDespues.includes(a.pista.id))
    throw new Error('La sugerencia aceptada no entró en la cola');
  // Modo automático: lo que se sugiere entra solo.
  await invocar('fiesta_modo_automatico', { activo: true });
  await esperar(10500);
  const r3 = await http(`${url.origin}/api/sugerir`, 'POST', h, { pistaId: ids[2], alias: 'QA' });
  const automatica = await esperarHasta(
    async () => {
      const c = (await invocar('reproductor_estado'))?.cola ?? [];
      return c.includes(ids[2]) ? true : null;
    },
    5000,
    'la sugerencia automática en la cola'
  );
  // Rotar el QR deja sin efecto el enlace anterior.
  const rotado = await invocar('fiesta_regenerar_qr');
  const viejo = await http(`${url.origin}/api/estado`, 'GET', h);
  const paginaVieja = await http(e.url);
  const nuevo = await http(rotado.url);
  await invocar('fiesta_modo_automatico', { activo: false });
  await invocar('fiesta_encender', { activo: false });
  if (viejo.estado !== 401 || paginaVieja.estado !== 401 || nuevo.estado !== 200) {
    throw new Error(
      `Tras rotar: viejo ${viejo.estado}, página vieja ${paginaVieja.estado}, nueva ${nuevo.estado}`
    );
  }
  console.log(
    'QA_F8_FIESTA',
    JSON.stringify({
      pagina: pagina.estado,
      busqueda: lista.length,
      sugeridas: 2,
      aceptada: a.pista.id,
      descartada: b.pista.id,
      enfriamiento: frenada,
      colaAntes: colaAntes.length,
      colaDespues: colaDespues.length,
      automatica: r3.estado === 200 && automatica,
      rotado: { viejo: viejo.estado, paginaVieja: paginaVieja.estado, nuevo: nuevo.estado }
    })
  );
}

try {
  if (ESCENARIO === 'forma') await formaDeOnda();
  else if (ESCENARIO === 'inteligentes') await inteligentes();
  else if (ESCENARIO === 'resumen') await resumen();
  else if (ESCENARIO === 'fiesta') await fiesta();
  else throw new Error(`Escenario desconocido: ${ESCENARIO}`);
} finally {
  agente.destroy();
  inspector.cerrar();
}
