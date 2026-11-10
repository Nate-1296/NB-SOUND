#!/usr/bin/env node
// Pruebas finales de la Fase 6 (DJ y A ciegas) sobre la copia aislada. Lo
// orquesta scripts/qa/ui-qa.sh fase6; cada escenario deja una línea QA_DJ_*.

import { execFileSync, spawn } from 'node:child_process';
import { readdirSync, readFileSync, writeFileSync } from 'node:fs';

import { Inspector, esperar } from './inspector.mjs';

const ESCENARIO = process.argv[2];
const DB = process.env.NB_QA_DB;
const RAIZ = process.env.NB_QA_RAIZ;
const QA = process.env.NB_QA_ROOT;
const INFORMES = process.env.NB_QA_INFORMES;
const REGISTROS = `${QA}/registros`;
const APP_PID = Number(process.env.NB_QA_APP_PID ?? 0);
const inspector = await Inspector.conectar();

function sql(consulta) {
  return execFileSync('sqlite3', ['-readonly', '-separator', '\t', DB, consulta], {
    encoding: 'utf8'
  }).trim();
}

function invocar(comando, argumentos = {}) {
  return inspector.evaluar(
    `window.__TAURI_INTERNALS__.invoke(${JSON.stringify(comando)}, ${JSON.stringify(argumentos)})`
  );
}

const estado = () => invocar('reproductor_estado');

/** Pide una sesión sin esperar a la respuesta: medir cuándo suena es la prueba. */
async function pedirSesion(peticion, minutos) {
  await inspector.evaluarDirecto(`(() => {
    window.__qaPedido = null;
    window.__TAURI_INTERNALS__.invoke("dj_pedir", ${JSON.stringify({ peticion, minutos })})
      .then((r) => (window.__qaPedido = r))
      .catch((e) => (window.__qaPedido = { error: String(e) }));
    return true;
  })()`);
}

const pedidoListo = (limite = 120000) =>
  esperarHasta(
    () => inspector.evaluar('window.__qaPedido'),
    limite,
    'la respuesta de dj_pedir',
    100
  );
const orden = async (o) => {
  const r = await invocar('reproductor_orden', { orden: o });
  if (process.env.NB_QA_TRAZA) {
    const e = await estado();
    console.log(
      'TRAZA',
      JSON.stringify(o),
      JSON.stringify({ cola: e.cola, i: e.indiceCola, p: e.pistaId, dj: e.dj?.posicion ?? null })
    );
  }
  return r;
};

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

async function ir(ruta, selector) {
  await inspector.evaluarDirecto(
    `(() => { location.href = ${JSON.stringify(`tauri://localhost${ruta}`)}; return true; })()`
  );
  await esperarHasta(
    () => inspector.evaluar(`Boolean(document.querySelector(${JSON.stringify(selector)}))`),
    15000,
    `la vista ${ruta}`
  );
}

function mpris(propiedad) {
  return execFileSync(
    'busctl',
    [
      '--user',
      'get-property',
      'org.mpris.MediaPlayer2.nbsound',
      '/org/mpris/MediaPlayer2',
      'org.mpris.MediaPlayer2.Player',
      propiedad
    ],
    { encoding: 'utf8' }
  );
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

async function iniciarGrabacion(ruta) {
  const indice = await esperarHasta(async () => indiceFlujoApp(), 10000, 'flujo de audio');
  execFileSync('pactl', ['move-sink-input', String(indice), 'nb_sound_qa_ui']);
  await esperar(100);
  const proceso = spawn(
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
  await esperar(150);
  const inicio = Date.now();
  return {
    inicio,
    async detener() {
      if (proceso.exitCode !== null) return;
      const salida = new Promise((resolve) => proceso.once('exit', resolve));
      proceso.kill('SIGINT');
      await Promise.race([salida, esperar(3000)]);
      // Un parec que no se va seguiría escribiendo en el mismo archivo en la
      // corrida siguiente y estropearía su grabación.
      if (proceso.exitCode === null) proceso.kill('SIGKILL');
    }
  };
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

// --- Hilos y CPU ---------------------------------------------------------------------

function hilos() {
  const carpeta = `/proc/${APP_PID}/task`;
  return readdirSync(carpeta).flatMap((tid) => {
    // Un hilo puede acabar entre listar la carpeta y leerlo.
    let stat;
    let nombre;
    try {
      stat = readFileSync(`${carpeta}/${tid}/stat`, 'utf8');
      nombre = readFileSync(`${carpeta}/${tid}/comm`, 'utf8').trim();
    } catch {
      return [];
    }
    const resto = stat
      .slice(stat.lastIndexOf(')') + 2)
      .trim()
      .split(/\s+/);
    return [{ tid, nombre, ticks: Number(resto[11]) + Number(resto[12]) }];
  });
}

const TICKS = Number(execFileSync('getconf', ['CLK_TCK'], { encoding: 'utf8' }).trim());

// --- Escenarios ----------------------------------------------------------------------

function colaDelUsuario() {
  return sql(
    "SELECT id FROM pistas WHERE estado='biblioteca' AND duracion_seg > 120 ORDER BY id LIMIT 3;"
  )
    .split('\n')
    .map(Number);
}

async function prepararColaDelUsuario() {
  const ids = colaDelUsuario();
  await orden({ tipo: 'reproducirPistas', ids, desde: 1 });
  await esperarHasta(
    async () => (await estado())?.pistaId === ids[1],
    10000,
    'la cola del usuario'
  );
  await orden({ tipo: 'buscar', segundos: 42 });
  await orden({ tipo: 'pausarReanudar' });
  await esperarHasta(async () => (await estado())?.estado === 'pausado', 5000, 'pausa');
  const e = await estado();
  return { cola: e.cola, indiceCola: e.indiceCola, pistaId: e.pistaId };
}

function lineasDelRegistro(desde) {
  const archivos = readdirSync(REGISTROS).filter((n) => n.startsWith('nb-sound.log.'));
  return archivos
    .flatMap((n) => readFileSync(`${REGISTROS}/${n}`, 'utf8').split('\n'))
    .filter((l) => {
      const t = Date.parse(l.slice(0, 27));
      return Number.isFinite(t) && t >= desde;
    });
}

async function sesionCorta() {
  // Los vectores de la biblioteca se calculan al arrancar, con prioridad baja.
  const vectores = await esperarHasta(
    async () => {
      // Solo lo de este arranque: el registro del día acumula las corridas anteriores.
      const lineas = lineasDelRegistro(Date.now() - 3600000);
      const arranque = lineas.findLastIndex((l) => l.includes('arranca NB Sound'));
      return lineas.slice(arranque).find((l) => l.includes('vectores del DJ al día'));
    },
    600000,
    'los vectores del DJ',
    1000
  );
  const precalentado = {
    pistas: Number(vectores.match(/pistas=(\d+)/)?.[1]),
    segundos: Number(vectores.match(/segundos=([\d.]+)/)?.[1])
  };
  const original = await prepararColaDelUsuario();

  // Pedir y medir cuánto tarda en sonar.
  const t0 = Date.now();
  await pedirSesion('fiesta electrónica con mucho bajo', 30);
  const sonando = await esperarHasta(
    async () => {
      const e = await estado();
      return e?.dj && e.estado === 'reproduciendo' ? e : null;
    },
    120000,
    'la sesión sonando',
    50
  );
  const arranqueSeg = (Date.now() - t0) / 1000;
  const pedido = await pedidoListo();
  const respuestaSeg = (Date.now() - t0) / 1000;
  if (pedido.error) throw new Error(`dj_pedir falló: ${pedido.error}`);
  if (pedido.sinCandidatas) throw new Error('El DJ no encontró candidatas');
  if (arranqueSeg >= 3) throw new Error(`La sesión tardó ${arranqueSeg} s en sonar`);

  // Cómo se entendió.
  // La vista del DJ muestra la sesión cuando el reproductor ya la tiene; si llega
  // antes que ella, se vuelve a abrir.
  await ir('/dj', 'main').catch(() => {});
  await esperarHasta(
    async () => {
      if (await inspector.evaluar(`Boolean(document.querySelector(".sesion"))`)) return true;
      await ir('/dj', 'main').catch(() => {});
      return false;
    },
    60000,
    'la sesión en la vista del DJ',
    2000
  );
  const lectura = await esperarHasta(
    () =>
      inspector.evaluar(
        `[...document.querySelectorAll(".lectura .concepto")].map((n) => n.textContent.trim())`
      ),
    10000,
    'la lectura del pedido'
  ).then((l) => (l.length ? l : null));

  // Crece hasta la duración pedida.
  const crecida = await esperarHasta(
    async () => {
      const s = await invocar('dj_sesion', { sesionId: pedido.sesionId });
      const total = s.pistas.reduce((a, p) => a + (p.duracionSeg ?? 0), 0);
      return total >= 30 * 60 * 0.9
        ? { pistas: s.pistas.length, minutos: total / 60, estado: s.estado }
        : null;
    },
    180000,
    'la sesión crece hasta 30 minutos',
    1000
  );

  // La barra la controla.
  const controles = {};
  await orden({ tipo: 'pausarReanudar' });
  controles.pausa =
    (await esperarHasta(async () => (await estado()).estado === 'pausado', 5000, 'pausa')) && true;
  await orden({ tipo: 'pausarReanudar' });
  controles.reanudar =
    (await esperarHasta(
      async () => (await estado()).estado === 'reproduciendo',
      5000,
      'reanudar'
    )) && true;
  const antes = (await estado()).dj.posicion;
  await orden({ tipo: 'siguiente' });
  controles.siguiente = await esperarHasta(
    async () => ((await estado()).dj?.posicion === antes + 1 ? antes + 1 : null),
    15000,
    'siguiente'
  );
  await orden({ tipo: 'anterior' });
  controles.anterior = await esperarHasta(
    async () => ((await estado()).dj?.posicion === antes ? `${antes}` : null),
    15000,
    'anterior'
  );
  await orden({ tipo: 'buscar', segundos: 60 });
  controles.buscar = await esperarHasta(
    async () => {
      const p = (await estado()).posicionSeg;
      return Math.abs(p - 60) < 2 ? p : null;
    },
    5000,
    'buscar'
  );

  // La medida del equipo, que el pedido lanzó.
  const medida = await esperarHasta(
    async () =>
      lineasDelRegistro(t0 - 1000).find((l) => l.includes('perfil del equipo para mezclar')),
    150000,
    'la medida del equipo',
    1000
  );
  const medidaSeg = (Date.parse(medida.slice(0, 27)) - t0) / 1000;
  const factor = Number(medida.match(/factor=([\d.]+)/)?.[1]);
  const perfil = medida.match(/perfil=(\w+)/)?.[1];
  if (!(medidaSeg < 120)) throw new Error(`La medida tardó ${medidaSeg} s`);

  // Otra parecida y Descartar devuelven la cola.
  await inspector.evaluarDirecto(`(() => {
    window.__qaPedido = null;
    window.__TAURI_INTERNALS__.invoke("dj_regenerar", { sesionId: ${pedido.sesionId} })
      .then((r) => (window.__qaPedido = r))
      .catch((e) => (window.__qaPedido = { error: String(e) }));
    return true;
  })()`);
  const otra = await pedidoListo();
  if (otra.error) throw new Error(`dj_regenerar falló: ${otra.error}`);
  await esperarHasta(
    async () => (await estado()).dj?.sesionId === otra.sesionId,
    15000,
    'otra sesión sonando'
  );
  await invocar('dj_descartar', { sesionId: otra.sesionId });
  const devuelta = await esperarHasta(
    async () => {
      const e = await estado();
      return !e.dj ? { cola: e.cola, indiceCola: e.indiceCola, pistaId: e.pistaId } : null;
    },
    10000,
    'la cola del usuario de vuelta'
  );
  if (JSON.stringify(devuelta) !== JSON.stringify(original)) {
    throw new Error(`La cola no volvió: ${JSON.stringify({ original, devuelta })}`);
  }

  // Una sesión sonando para comprobar que vuelve en pausa tras reabrir.
  await pedirSesion('algo alegre para empezar el día', 20);
  const ultima = await pedidoListo();
  await esperarHasta(
    async () => (await estado())?.dj?.sesionId === ultima.sesionId,
    10000,
    'la última sesión'
  );
  writeFileSync(`${INFORMES}/fase6-ultima.json`, JSON.stringify(ultima));

  console.log(
    'QA_DJ_SESION',
    JSON.stringify({
      precalentado,
      arranqueSeg,
      respuestaSeg,
      lectura,
      crecida,
      controles,
      medida: { medidaSeg, factor, perfil },
      colaOriginal: original,
      colaDevuelta: devuelta,
      dj: sonando.dj
    })
  );
}

async function trasReabrir() {
  const { sesionId } = JSON.parse(readFileSync(`${INFORMES}/fase6-ultima.json`, 'utf8'));
  const e = await esperarHasta(
    async () => ((await estado())?.dj ? estado() : null),
    15000,
    'la sesión restaurada'
  );
  if (e.dj.sesionId !== sesionId || e.estado !== 'pausado') {
    throw new Error(`Tras reabrir: ${JSON.stringify(e)}`);
  }
  await invocar('dj_descartar', { sesionId });
  console.log(
    'QA_DJ_REABIERTA',
    JSON.stringify({ sesionId, estado: e.estado, posicion: e.dj.posicion })
  );
}

async function sesionDeUnaHora() {
  const minutos = Number(process.env.NB_QA_MINUTOS_DJ ?? 60);
  await pedirSesion('tranquilo, después más movido, y al final épico', minutos);
  const pedido = await pedidoListo();
  await esperarHasta(async () => (await estado())?.dj, 10000, 'la sesión larga');
  const wav = `${INFORMES}/fase6-sesion.wav`;
  const grabacion = await iniciarGrabacion(wav);
  const mezclas = [];
  let abierta = null;
  const cpu = { normal: { ticks: 0, seg: 0 }, mezcla: { ticks: 0, seg: 0 } };
  const porHilo = {};
  let anterior = hilos();
  let tAnterior = Date.now();
  const fin = Date.now() + minutos * 60 * 1000;
  let terminada = false;
  while (Date.now() < fin && !terminada) {
    await esperar(250);
    const e = await estado();
    const ahora = Date.now();
    const rel = (ahora - grabacion.inicio) / 1000;
    const mezcla = e?.dj?.mezcla ?? null;
    if (mezcla && !abierta) abierta = { inicio: rel, tecnica: mezcla.tecnica };
    if (!mezcla && abierta) {
      mezclas.push([abierta.inicio, rel, abierta.tecnica]);
      abierta = null;
    }
    if (!e?.dj) terminada = true;
    // CPU del motor: el hilo del reproductor y los del audio del sistema.
    const actuales = hilos();
    const tramo = (ahora - tAnterior) / 1000;
    let ticks = 0;
    for (const h of actuales) {
      const previo = anterior.find((x) => x.tid === h.tid);
      if (!previo) continue;
      const d = h.ticks - previo.ticks;
      porHilo[h.nombre] = (porHilo[h.nombre] ?? 0) + d;
      if (h.nombre === 'reproductor' || /cpal|alsa|audio|pw-/i.test(h.nombre)) ticks += d;
    }
    const tipo = mezcla ? 'mezcla' : 'normal';
    cpu[tipo].ticks += ticks;
    cpu[tipo].seg += tramo;
    anterior = actuales;
    tAnterior = ahora;
  }
  await grabacion.detener();
  writeFileSync(`${INFORMES}/fase6-mezclas.json`, JSON.stringify(mezclas));
  const porcentaje = (c) => (c.seg ? (c.ticks / TICKS / c.seg) * 100 : null);
  const cpuNormal = porcentaje(cpu.normal);
  const cpuMezcla = porcentaje(cpu.mezcla);
  // Antes del análisis del audio, que puede fallar por su cuenta: la CPU se mide igual.
  console.log(
    'QA_DJ_CPU',
    JSON.stringify({ cpuNormal, cpuMezcla, segNormal: cpu.normal.seg, segMezcla: cpu.mezcla.seg })
  );
  const audio = analizar('las_mezclas_del_dj_no_tienen_huecos_ni_clics_ni_saltos', {
    NB_QA_WAV: wav,
    NB_QA_MEZCLAS: `${INFORMES}/fase6-mezclas.json`
  });
  const tecnicas = [...new Set(mezclas.map((m) => m[2]))];
  const duracion = (Date.now() - grabacion.inicio) / 1000;
  await invocar('dj_descartar', { sesionId: pedido.sesionId }).catch(() => {});
  if (cpuNormal >= 2 || cpuMezcla >= 4) {
    throw new Error(`CPU del motor: normal ${cpuNormal} %, mezcla ${cpuMezcla} %`);
  }
  const topHilos = Object.entries(porHilo)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([n, t]) => [n, Number(((t / TICKS / duracion) * 100).toFixed(2))]);
  console.log(
    'QA_DJ_HORA',
    JSON.stringify({
      duracionSeg: duracion,
      mezclas: mezclas.length,
      tecnicas,
      cpuNormal,
      cpuMezcla,
      topHilos,
      audio: { ...audio, mezclas: undefined }
    })
  );
}

function conUnaLetraCambiada(titulo) {
  // Una sola letra cambiada, la primera que haya después de la primera; un título
  // sin letras (un número) se escribe tal cual.
  const letras = [...titulo];
  let i = letras.findIndex((c, k) => k > 0 && /\p{L}/u.test(c));
  if (i < 0) i = letras.findIndex((c) => /\p{L}/u.test(c));
  if (i < 0) return titulo;
  letras[i] = letras[i].toLowerCase() === 'x' ? 'y' : 'x';
  return letras.join('');
}

async function aciegas() {
  const modos = (await invocar('aciegas_disponibles')).filter((m) => m.canciones > 0);
  const resultados = [];
  for (const { modo } of modos) {
    const original = await prepararColaDelUsuario();
    const ronda = await invocar('aciegas_iniciar', { modo, retos: 1, evitar: [] });
    const reto = ronda.reto;
    const [titulo, ruta, duracion] = sql(
      `SELECT titulo, ruta, duracion_seg FROM pistas WHERE id=${reto.pistaId};`
    ).split('\t');
    await ir('/a-ciegas', 'main');
    const wav = `${INFORMES}/fase6-aciegas-${modo}.wav`;
    await invocar('aciegas_fragmento');
    const grabacion = await iniciarGrabacion(wav);
    const e = await esperarHasta(
      async () => ((await estado())?.ciego ? estado() : null),
      5000,
      'el fragmento'
    );
    const barra = await inspector.evaluar(
      `[...document.querySelectorAll("section.reproductor .titulo")].map((n) => n.textContent.trim())`
    );
    const metadatos = mpris('Metadata');
    await esperar(Math.min(4500, ronda.segundosFragmento * 1000 - 500));
    await grabacion.detener();
    const delata =
      e.pistaId !== null ||
      barra.some((t) => t.includes(titulo)) ||
      metadatos.includes(JSON.stringify(titulo).slice(1, -1));
    if (delata) throw new Error(`${modo}: la canción se delata: ${JSON.stringify({ e, barra })}`);
    const desde = Number(duracion) <= 60 ? 0 : Math.round(Number(duracion) * 0.3 * 100) / 100;
    const fragmento = analizar('el_fragmento_de_a_ciegas_empieza_en_el_treinta_por_ciento', {
      NB_QA_WAV: wav,
      NB_QA_FUENTE: `${QA}/biblioteca/${ruta}`,
      NB_QA_DESDE: String(desde)
    });
    const escrito = conUnaLetraCambiada(titulo);
    const intento = await invocar('aciegas_intentar', { texto: escrito });
    if (!intento.intento.acierto) {
      throw new Error(
        `${modo}: "${escrito}" no acertó "${titulo}": ${JSON.stringify(intento.intento)}`
      );
    }
    await invocar('aciegas_jugar', { jugada: { tipo: 'cerrar' } });
    const devuelta = await esperarHasta(
      async () => {
        const x = await estado();
        return !x.ciego ? { cola: x.cola, indiceCola: x.indiceCola, pistaId: x.pistaId } : null;
      },
      10000,
      'la cola de vuelta'
    );
    if (JSON.stringify(devuelta) !== JSON.stringify(original)) {
      throw new Error(`${modo}: la cola no volvió: ${JSON.stringify({ original, devuelta })}`);
    }
    resultados.push({ modo, escrito, ratio: intento.intento.ratio, fragmento });
  }
  if (resultados.length === 0) throw new Error('No hay modos de A ciegas disponibles');
  console.log('QA_DJ_ACIEGAS', JSON.stringify(resultados));
}

try {
  if (ESCENARIO === 'sesion') await sesionCorta();
  else if (ESCENARIO === 'reabierta') await trasReabrir();
  else if (ESCENARIO === 'hora') await sesionDeUnaHora();
  else if (ESCENARIO === 'aciegas') await aciegas();
  else throw new Error(`Escenario desconocido: ${ESCENARIO}`);
} finally {
  inspector.cerrar();
}
