#!/usr/bin/env node
// Pruebas finales de la Fase 5 (agregados y karaoke) sobre la copia aislada.
// Lo orquesta scripts/qa/ui-qa.sh fase5: este archivo hace cada escenario y deja
// una línea QA_KARAOKE_* con sus cifras; el guion mata y reabre la aplicación
// entre escenarios cuando la prueba lo pide.

import { execFileSync, spawn } from "node:child_process";
import { existsSync, readFileSync, statSync, writeFileSync } from "node:fs";

import { Inspector, esperar } from "./inspector.mjs";

const ESCENARIO = process.argv[2];
const DB = process.env.NB_QA_DB;
const RAIZ = process.env.NB_QA_RAIZ;
const QA = process.env.NB_QA_ROOT;
const INFORMES = process.env.NB_QA_INFORMES;
const APP_PID = Number(process.env.NB_QA_APP_PID ?? 0);
const AGREGADOS = `${QA}/datos/agregados`;
const inspector = await Inspector.conectar();

// La pista que se prepara mientras suena el tono de fondo (prepararla tarda más
// que oírla, así que no puede ser la misma) y la de 48 kHz.
const PISTA_PREPARAR = Number(process.env.NB_QA_PISTA_PREPARAR ?? 3);
const PISTA_FONDO = Number(process.env.NB_QA_PISTA_FONDO);
const PISTA_48K = 468;

function sql(consulta) {
  return execFileSync("sqlite3", ["-readonly", "-separator", "\t", DB, consulta], {
    encoding: "utf8"
  }).trim();
}

function invocar(comando, argumentos = {}) {
  return inspector.evaluar(
    `window.__TAURI_INTERNALS__.invoke(${JSON.stringify(comando)}, ${JSON.stringify(argumentos)})`
  );
}

async function esperarHasta(prueba, limite, descripcion) {
  const hasta = Date.now() + limite;
  let ultimo;
  while (Date.now() < hasta) {
    try {
      ultimo = await prueba();
      if (ultimo) return ultimo;
    } catch (error) {
      ultimo = error;
    }
    await esperar(500);
  }
  throw new Error(`No se cumplió: ${descripcion}. Último: ${JSON.stringify(ultimo)}`);
}

function picoMemoriaMb(pid) {
  const estado = readFileSync(`/proc/${pid}/status`, "utf8");
  return Math.round(Number(estado.match(/^VmHWM:\s+(\d+)/m)[1]) / 1024);
}

function parcial() {
  const ruta = `${AGREGADOS}/.descargas/karaoke-1.zip.parcial`;
  return existsSync(ruta) ? statSync(ruta).size : 0;
}

function indiceFlujoApp() {
  const texto = execFileSync("pactl", ["list", "sink-inputs"], { encoding: "utf8" });
  for (const bloque of texto.split(/\n\n+/)) {
    if (!bloque.includes('application.name = "PipeWire ALSA [nb-sound]"')) continue;
    const indice = bloque.match(/^Sink Input #(\d+)/m)?.[1];
    if (indice) return Number(indice);
  }
  return null;
}

async function iniciarGrabacion(ruta) {
  const indice = await esperarHasta(async () => indiceFlujoApp(), 10000, "flujo de audio");
  execFileSync("pactl", ["move-sink-input", String(indice), "nb_sound_qa_ui"]);
  await esperar(100);
  const proceso = spawn(
    "parec",
    [
      `--monitor-stream=${indice}`,
      "--file-format=wav",
      "--rate=48000",
      "--channels=2",
      "--format=float32le",
      "--latency-msec=20",
      ruta
    ],
    { stdio: "ignore" }
  );
  await esperar(150);
  return {
    async detener() {
      if (proceso.exitCode !== null) return;
      const salida = new Promise((resolve) => proceso.once("exit", resolve));
      proceso.kill("SIGINT");
      await Promise.race([salida, esperar(3000)]);
    }
  };
}

function sinHuecos(wav) {
  const salida = execFileSync(
    "cargo",
    [
      "test",
      "--manifest-path",
      `${RAIZ}/src-tauri/Cargo.toml`,
      "--test",
      "qa_audio",
      "una_reproduccion_continua_no_tiene_huecos",
      "--",
      "--ignored",
      "--nocapture",
      "--test-threads=1"
    ],
    { cwd: `${RAIZ}/src-tauri`, encoding: "utf8", env: { ...process.env, NB_QA_WAV: wav } }
  );
  const linea = salida.split("\n").find((l) => l.includes("INFORME_QA"));
  return JSON.parse(linea.replace(/^.*INFORME_QA /, "")).datos;
}

async function abrirConsola() {
  await esperarHasta(
    () => inspector.evaluar(`Boolean(document.querySelector(".boton-karaoke"))`),
    20000,
    "la barra superior"
  );
  await inspector.evaluar(`(() => {
    const b = [...document.querySelectorAll("button[aria-expanded]")]
      .find((n) => n.getAttribute("aria-label") === "Abrir la consola de karaoke");
    if (!b) throw new Error("no está el botón de la consola");
    if (b.getAttribute("aria-expanded") !== "true") b.click();
    return true;
  })()`);
}

// --- Escenarios ----------------------------------------------------------------------

async function sinAgregado() {
  const estado = await invocar("karaoke_estado");
  if (estado.instalado) throw new Error("La copia ya tiene el agregado de karaoke");
  await invocar("reproductor_orden", { orden: { tipo: "reproducirPistas", ids: [PISTA_FONDO], desde: 0 } });
  await invocar("reproductor_orden", { orden: { tipo: "pausarReanudar" } });
  await abrirConsola();
  const alerta = await esperarHasta(
    () => inspector.evaluar(`document.querySelector(".tarjeta.alerta")?.textContent.trim() ?? ""`),
    8000,
    "la alerta de agregado"
  );
  await inspector.evaluar(`(() => { document.querySelector(".tarjeta.alerta button").click(); return true; })()`);
  const oferta = await esperarHasta(
    () =>
      inspector.evaluar(`(() => {
        const d = [...document.querySelectorAll("dialog[open], [role=dialog]")]
          .map((n) => n.textContent.replace(/\\s+/g, " ").trim())
          .find((t) => /MB/.test(t));
        return d ?? "";
      })()`),
    8000,
    "la oferta con su tamaño"
  );
  const tamano = oferta.match(/(\d+(?:[.,]\d+)?)\s*MB/)?.[0];
  if (!tamano) throw new Error(`La oferta no dice el tamaño: ${oferta}`);
  console.log("QA_KARAOKE_SIN_AGREGADO", JSON.stringify({ alerta, tamano, bytes: estado.bytes }));
}

async function cortarDescarga() {
  const total = 145_667_909;
  void invocar("agregado_instalar", { id: "karaoke" }).catch(() => {});
  const visto = await esperarHasta(
    async () => (parcial() > total * 0.4 ? parcial() : 0),
    600000,
    "el 40 % de la descarga"
  );
  writeFileSync(`${INFORMES}/fase5-parcial.json`, JSON.stringify({ alCortar: visto, total }));
  console.log("QA_KARAOKE_DESCARGA_CORTADA", JSON.stringify({ bytes: visto, total }));
}

async function reanudarEInstalar() {
  const { alCortar, total } = JSON.parse(readFileSync(`${INFORMES}/fase5-parcial.json`, "utf8"));
  const alReabrir = parcial();
  if (alReabrir < alCortar * 0.9) {
    throw new Error(`El parcial no sobrevivió al cierre: ${alReabrir} de ${alCortar}`);
  }
  const inicio = Date.now();
  const resultados = {};
  for (const id of ["karaoke", "analisis", "textoDj"]) {
    const empezado = Date.now();
    await invocar("agregado_instalar", { id });
    const estado = await esperarHasta(
      async () => {
        const todos = await invocar("agregados_estado");
        const e = todos.find((x) => x.id === id);
        if (e?.error) throw new Error(`${id}: ${JSON.stringify(e)}`);
        return e?.instalada ?? e?.instalado ? e : null;
      },
      900000,
      `la instalación de ${id}`
    );
    resultados[id] = { segundos: (Date.now() - empezado) / 1000, version: estado.instalada ?? estado.version };
  }
  // La suma la comprueba el propio instalador antes de descomprimir: si llega
  // a instalado, el ZIP era el del catálogo. Lo que queda por ver es que no
  // empezó de cero: el parcial siguió y desapareció al terminar.
  if (existsSync(`${AGREGADOS}/.descargas/karaoke-1.zip.parcial`)) {
    throw new Error("El parcial sigue ahí tras instalar");
  }
  const marcas = Object.fromEntries(
    ["karaoke", "analisis", "texto-dj"].map((c) => [c, readFileSync(`${AGREGADOS}/${c}/agregado.json`, "utf8").trim()])
  );
  console.log(
    "QA_KARAOKE_INSTALADOS",
    JSON.stringify({ alCortar, alReabrir, total, resultados, marcas, segundos: (Date.now() - inicio) / 1000 })
  );
}

async function prepararConCarga() {
  const nucleos = Number(execFileSync("nproc", { encoding: "utf8" }).trim());
  // Todos los núcleos ocupados, cada uno con un bucle que no hace nada útil.
  const carga = [];
  for (let i = 0; i < nucleos; i += 1) {
    carga.push(spawn("sh", ["-c", "while :; do :; done"], { stdio: "ignore" }));
  }
  const wav = `${INFORMES}/fase5-preparando.wav`;
  let grabacion;
  try {
    await invocar("reproductor_orden", {
      orden: { tipo: "reproducirPistas", ids: [PISTA_FONDO], desde: 0 }
    });
    grabacion = await iniciarGrabacion(wav);
    const memoriaAntes = picoMemoriaMb(APP_PID);
    const inicio = Date.now();
    await invocar("karaoke_preparar", { pistas: [PISTA_PREPARAR] });
    await abrirConsola();
    const avances = new Set();
    await esperarHasta(
      async () => {
        const pct = await inspector.evaluar(`(() => {
          const t = [...document.querySelectorAll(".cola li.activa .turno")].map((n) => n.textContent.trim());
          return t[0] ?? null;
        })()`);
        if (pct) avances.add(pct);
        const fila = sql(`SELECT estado FROM stems WHERE pista_id=${PISTA_PREPARAR};`);
        return fila === "lista" ? fila : null;
      },
      1800000,
      "la preparación con carga"
    );
    const segundos = (Date.now() - inicio) / 1000;
    await grabacion.detener();
    grabacion = null;
    const pico = picoMemoriaMb(APP_PID);
    for (const p of carga) p.kill("SIGKILL");
    const audio = sinHuecos(wav);
    if (avances.size < 3) throw new Error(`El avance no se movió en la consola: ${[...avances]}`);
    if (pico >= 3072) throw new Error(`Pico de memoria de ${pico} MB`);
    console.log(
      "QA_KARAOKE_PREPARADA_CON_CARGA",
      JSON.stringify({ nucleos, segundos, avances: [...avances], memoriaAntes, picoMb: pico, audio })
    );
  } finally {
    for (const p of carga) p.kill("SIGKILL");
    if (grabacion) await grabacion.detener();
  }
}

async function pasarAlInstrumental() {
  await invocar("reproductor_orden", { orden: { tipo: "reproducirPistas", ids: [PISTA_PREPARAR], desde: 0 } });
  await esperarHasta(
    async () => (await invocar("reproductor_estado"))?.karaokeDisponible,
    15000,
    "el micrófono disponible"
  );
  const wav = `${INFORMES}/fase5-instrumental.wav`;
  const grabacion = await iniciarGrabacion(wav);
  await esperar(6000);
  await invocar("reproductor_orden", { orden: { tipo: "karaoke", activo: true } });
  await esperar(6000);
  const estado = await invocar("reproductor_estado");
  await grabacion.detener();
  if (!estado.karaokeActivo) throw new Error("El karaoke no se activó");
  const audio = sinHuecos(wav);
  console.log("QA_KARAOKE_INSTRUMENTAL", JSON.stringify({ karaokeActivo: true, audio }));
}

async function cooler() {
  const sr = execFileSync(
    "ffprobe",
    ["-v", "error", "-select_streams", "a", "-show_entries", "stream=sample_rate", "-of", "csv=p=0",
      `${QA}/biblioteca/${sql(`SELECT ruta FROM pistas WHERE id=${PISTA_48K};`)}`],
    { encoding: "utf8" }
  ).trim();
  const inicio = Date.now();
  await invocar("karaoke_preparar", { pistas: [PISTA_48K] });
  await esperarHasta(
    async () => {
      const e = await invocar("karaoke_estado");
      if (e.fallidas?.some?.((f) => (f.pista ?? f) === PISTA_48K)) throw new Error("falló");
      return sql(`SELECT estado FROM stems WHERE pista_id=${PISTA_48K};`) === "lista";
    },
    1800000,
    "Cooler Than Me preparada"
  );
  await invocar("reproductor_orden", { orden: { tipo: "reproducirPistas", ids: [PISTA_48K], desde: 0 } });
  const boton = await esperarHasta(
    () =>
      inspector.evaluar(`(() => {
        const b = [...document.querySelectorAll("button[aria-pressed]")]
          .find((n) => n.querySelector("svg") && n.getAttribute("aria-label") === "Modo karaoke");
        return b && !b.disabled ? "habilitado" : "";
      })()`),
    15000,
    "el micrófono de la barra habilitado"
  );
  console.log(
    "QA_KARAOKE_48K",
    JSON.stringify({ tasa: Number(sr), segundos: (Date.now() - inicio) / 1000, microfono: boton })
  );
}

try {
  if (ESCENARIO === "sin-agregado") await sinAgregado();
  else if (ESCENARIO === "cortar") await cortarDescarga();
  else if (ESCENARIO === "reanudar") await reanudarEInstalar();
  else if (ESCENARIO === "con-carga") await prepararConCarga();
  else if (ESCENARIO === "instrumental") await pasarAlInstrumental();
  else if (ESCENARIO === "cooler") await cooler();
  else throw new Error(`Escenario desconocido: ${ESCENARIO}`);
} finally {
  inspector.cerrar();
}
