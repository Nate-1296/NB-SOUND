#!/usr/bin/env node
// La primera apertura del día: NB Sound arranca con todo su trabajo de fondo
// (análisis, auditoría, vectores del DJ y la copia automática que toca) y la
// canción que se pone nada más abrir no puede entrecortarse. Lo orquesta
// scripts/qa/ui-qa.sh arranque-cargado.

import { execFileSync, spawn } from 'node:child_process';

import { Inspector, esperar } from './inspector.mjs';

const DB = process.env.NB_QA_DB;
const RAIZ = process.env.NB_QA_RAIZ;
const INFORMES = process.env.NB_QA_INFORMES;
const SEGUNDOS = Number(process.env.NB_QA_SEGUNDOS ?? 200);
const inspector = await Inspector.conectar();

const sql = (c) => execFileSync('sqlite3', ['-readonly', DB, c], { encoding: 'utf8' }).trim();
const invocar = (c, a = {}) =>
  inspector.evaluar(
    `window.__TAURI_INTERNALS__.invoke(${JSON.stringify(c)}, ${JSON.stringify(a)})`
  );

function indiceFlujoApp() {
  const texto = execFileSync('pactl', ['list', 'sink-inputs'], { encoding: 'utf8' });
  for (const bloque of texto.split(/\n\n+/)) {
    if (!bloque.includes('application.name = "PipeWire ALSA [nb-sound]"')) continue;
    const indice = bloque.match(/^Sink Input #(\d+)/m)?.[1];
    if (indice) return Number(indice);
  }
  return null;
}

try {
  // La más larga de la biblioteca, para que dure toda la medida.
  const pista = Number(
    sql("SELECT id FROM pistas WHERE estado='biblioteca' ORDER BY duracion_seg DESC LIMIT 1;")
  );
  await invocar('reproductor_orden', {
    orden: { tipo: 'reproducirPistas', ids: [pista], desde: 0 }
  });
  let indice = null;
  for (let i = 0; i < 100 && indice === null; i += 1) {
    indice = indiceFlujoApp();
    if (indice === null) await esperar(100);
  }
  execFileSync('pactl', ['move-sink-input', String(indice), 'nb_sound_qa_ui']);
  const wav = `${INFORMES}/arranque-cargado.wav`;
  const parec = spawn(
    'parec',
    [
      `--monitor-stream=${indice}`,
      '--file-format=wav',
      '--rate=48000',
      '--channels=2',
      '--format=float32le',
      '--latency-msec=20',
      wav
    ],
    { stdio: 'ignore' }
  );
  await esperar(SEGUNDOS * 1000);
  const salida = new Promise((r) => parec.once('exit', r));
  parec.kill('SIGINT');
  await Promise.race([salida, esperar(3000)]);
  const copia = sql("SELECT valor FROM preferencias WHERE clave='copia_ultima';");
  const analisis = execFileSync(
    'cargo',
    [
      'test',
      '--manifest-path',
      `${RAIZ}/src-tauri/Cargo.toml`,
      '--test',
      'qa_audio',
      'una_reproduccion_continua_no_tiene_huecos',
      '--',
      '--ignored',
      '--nocapture',
      '--test-threads=1'
    ],
    { cwd: `${RAIZ}/src-tauri`, encoding: 'utf8', env: { ...process.env, NB_QA_WAV: wav } }
  );
  const datos = JSON.parse(
    analisis
      .split('\n')
      .find((l) => l.includes('INFORME_QA'))
      .replace(/^.*INFORME_QA /, '')
  ).datos;
  console.log('QA_ARRANQUE_CARGADO', JSON.stringify({ pista, copiaUltima: copia, audio: datos }));
} finally {
  inspector.cerrar();
}
