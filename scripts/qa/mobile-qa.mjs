#!/usr/bin/env node

import { execFileSync, spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { request as httpsRequest } from "node:https";
import { connect as tlsConnect } from "node:tls";

import { Inspector, esperar } from "./inspector.mjs";

const DB = process.env.NB_QA_DB;
const APP_PID = Number(process.env.NB_QA_APP_PID ?? 0);
const RAIZ = process.env.NB_QA_RAIZ ?? process.cwd();
const INFORMES = process.env.NB_QA_INFORMES;
const CERT_PATH = process.env.NB_QA_CERT_PATH ?? "";
const inspector = await Inspector.conectar();

let base = "";
let token = "";
let dispositivo = null;
let websocket = null;
let huellaEsperada = "";
let pemEsperado = "";

function salida(nombre, datos) {
  console.log(`QA_MOVIL ${JSON.stringify({ escenario: nombre, datos })}`);
}

function sql(consulta) {
  return execFileSync("sqlite3", ["-readonly", "-separator", "\t", DB, consulta], {
    encoding: "utf8"
  }).trim();
}

function filas(consulta) {
  const texto = sql(consulta);
  return texto ? texto.split("\n").map((linea) => linea.split("\t")) : [];
}

async function invocar(comando, argumentos = {}) {
  return inspector.evaluar(
    `window.__TAURI_INTERNALS__.invoke(${JSON.stringify(comando)}, ${JSON.stringify(argumentos)})`
  );
}

async function esperarHasta(expresion, prueba = Boolean, limite = 10000) {
  const hasta = Date.now() + limite;
  let ultimo;
  while (Date.now() < hasta) {
    try {
      ultimo = await inspector.evaluar(expresion);
      if (prueba(ultimo)) return ultimo;
    } catch (error) {
      ultimo = error;
    }
    await esperar(100);
  }
  throw new Error(`No se cumplió: ${expresion}. Último valor: ${JSON.stringify(ultimo)}`);
}

function comprobar(condicion, mensaje) {
  if (!condicion) throw new Error(mensaje);
}

function normalizarHuella(huella) {
  return String(huella ?? "").replaceAll(":", "").toUpperCase();
}

function huellaDelCertificado() {
  comprobar(CERT_PATH && existsSync(CERT_PATH), `No existe el certificado ${CERT_PATH}`);
  const salidaOpenSsl = execFileSync(
    "openssl",
    ["x509", "-in", CERT_PATH, "-noout", "-fingerprint", "-sha256"],
    { encoding: "utf8" }
  );
  return normalizarHuella(salidaOpenSsl.split("=").at(-1).trim());
}

function comprobarIdentidad(_host, certificado) {
  const huella = normalizarHuella(certificado.fingerprint256);
  if (huella !== huellaEsperada) {
    return new Error(`huella TLS inesperada: ${huella}`);
  }
  return undefined;
}

function peticion({ ruta, metodo = "GET", cuerpo, cabeceras = {}, autenticar = true }) {
  return new Promise((resolve, reject) => {
    const datos = cuerpo === undefined ? null : JSON.stringify(cuerpo);
    const url = new URL(ruta, base);
    const solicitud = httpsRequest(
      {
        hostname: url.hostname,
        port: url.port,
        path: url.pathname + url.search,
        method: metodo,
        ca: pemEsperado,
        rejectUnauthorized: true,
        servername: "nbsound.local",
        checkServerIdentity: comprobarIdentidad,
        headers: {
          ...(autenticar && token ? { Authorization: `Bearer ${token}` } : {}),
          ...(datos
            ? {
                "Content-Type": "application/json",
                "Content-Length": Buffer.byteLength(datos)
              }
            : {}),
          ...cabeceras
        }
      },
      (respuesta) => {
        const partes = [];
        respuesta.on("data", (parte) => partes.push(parte));
        respuesta.on("end", () => {
          resolve({
            estado: respuesta.statusCode,
            cabeceras: respuesta.headers,
            bytes: Buffer.concat(partes)
          });
        });
      }
    );
    solicitud.on("error", reject);
    if (datos) solicitud.write(datos);
    solicitud.end();
  });
}

async function peticionJson(opciones) {
  const respuesta = await peticion(opciones);
  let json = null;
  try {
    json = JSON.parse(respuesta.bytes.toString("utf8"));
  } catch {
    // El estado y el cuerpo se informan juntos.
  }
  return { ...respuesta, json };
}

async function manifest(since, limit = 5000) {
  const respuesta = await peticionJson({
    ruta: `/api/v1/manifest?since=${since}&limit=${limit}`
  });
  comprobar(
    respuesta.estado === 200,
    `manifest respondió ${respuesta.estado}: ${respuesta.bytes.toString("utf8")}`
  );
  return respuesta.json;
}

function iniciarGrabacion(ruta) {
  const indice = indiceFlujoApp();
  comprobar(indice !== null, "No apareció el flujo de audio de NB Sound");
  execFileSync("pactl", ["move-sink-input", String(indice), "nb_sound_qa_ui"]);
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
  return {
    async detener() {
      if (proceso.exitCode !== null || proceso.signalCode !== null) return;
      const terminado = new Promise((resolve) => proceso.once("exit", resolve));
      proceso.kill("SIGINT");
      await terminado;
    }
  };
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

function ejecutarAnalizador(prueba, variables) {
  return execFileSync(
    "cargo",
    [
      "test",
      "--manifest-path",
      `${RAIZ}/src-tauri/Cargo.toml`,
      "--test",
      "qa_audio",
      prueba,
      "--",
      "--ignored",
      "--nocapture",
      "--test-threads=1"
    ],
    {
      cwd: `${RAIZ}/src-tauri`,
      encoding: "utf8",
      env: { ...process.env, ...variables }
    }
  );
}

function descargarAudio(pista) {
  return new Promise((resolve, reject) => {
    const url = new URL(pista.audio_url, base);
    let bytes = 0;
    const solicitud = httpsRequest(
      {
        hostname: url.hostname,
        port: url.port,
        path: url.pathname + url.search,
        method: "GET",
        ca: pemEsperado,
        rejectUnauthorized: true,
        servername: "nbsound.local",
        checkServerIdentity: comprobarIdentidad,
        headers: { Authorization: `Bearer ${token}` }
      },
      (respuesta) => {
        if (respuesta.statusCode !== 200) {
          respuesta.resume();
          reject(new Error(`audio ${pista.id} respondió ${respuesta.statusCode}`));
          return;
        }
        const hash = respuesta.headers["x-nb-sound-hash"];
        if (pista.hash_sha256 && hash !== pista.hash_sha256) {
          respuesta.resume();
          reject(new Error(`audio ${pista.id}: hash de cabecera distinto`));
          return;
        }
        respuesta.on("data", (parte) => {
          bytes += parte.length;
        });
        respuesta.on("end", () => {
          const esperado = Number(respuesta.headers["content-length"] ?? bytes);
          if (bytes !== esperado || bytes === 0) {
            reject(
              new Error(`audio ${pista.id}: ${bytes} bytes recibidos de ${esperado}`)
            );
            return;
          }
          resolve({ bytes, hash });
        });
      }
    );
    solicitud.on("error", reject);
    solicitud.end();
  });
}

function frameCliente(texto) {
  const datos = Buffer.from(texto);
  const mascara = randomBytes(4);
  let cabecera;
  if (datos.length < 126) {
    cabecera = Buffer.from([0x81, 0x80 | datos.length]);
  } else if (datos.length < 65536) {
    cabecera = Buffer.alloc(4);
    cabecera[0] = 0x81;
    cabecera[1] = 0x80 | 126;
    cabecera.writeUInt16BE(datos.length, 2);
  } else {
    cabecera = Buffer.alloc(10);
    cabecera[0] = 0x81;
    cabecera[1] = 0x80 | 127;
    cabecera.writeBigUInt64BE(BigInt(datos.length), 2);
  }
  const enmascarados = Buffer.alloc(datos.length);
  for (let i = 0; i < datos.length; i += 1) {
    enmascarados[i] = datos[i] ^ mascara[i % 4];
  }
  return Buffer.concat([cabecera, mascara, enmascarados]);
}

function frameControl(opcode, datos = Buffer.alloc(0)) {
  const mascara = randomBytes(4);
  const enmascarados = Buffer.alloc(datos.length);
  for (let i = 0; i < datos.length; i += 1) {
    enmascarados[i] = datos[i] ^ mascara[i % 4];
  }
  return Buffer.concat([Buffer.from([0x80 | opcode, 0x80 | datos.length]), mascara, enmascarados]);
}

class WebSocketContrato {
  #socket;
  #buffer;
  #cola = [];
  #historial = [];
  #cerrado = false;
  #fragmentos = Buffer.alloc(0);
  #opcodeFragmento = 0;

  constructor(socket, restante) {
    this.#socket = socket;
    this.#buffer = restante.length ? Buffer.from(restante) : Buffer.alloc(0);
    socket.on("data", (parte) => {
      this.#buffer = Buffer.concat([this.#buffer, parte]);
      this.#procesar();
    });
    socket.on("close", () => {
      this.#cerrado = true;
    });
    socket.on("error", () => {
      this.#cerrado = true;
    });
    this.#procesar();
  }

  static async abrir({ host, puerto, autorizacion }) {
    const socket = tlsConnect({
      host,
      port: puerto,
      ca: pemEsperado,
      rejectUnauthorized: true,
      servername: "nbsound.local",
      checkServerIdentity: comprobarIdentidad
    });
    await new Promise((resolve, reject) => {
      socket.once("secureConnect", resolve);
      socket.once("error", reject);
    });
    const huella = normalizarHuella(socket.getPeerCertificate().fingerprint256);
    comprobar(huella === huellaEsperada, `huella WSS inesperada: ${huella}`);
    const clave = randomBytes(16).toString("base64");
    socket.write(
      [
        "GET /api/v1/control HTTP/1.1",
        `Host: ${host}:${puerto}`,
        "Upgrade: websocket",
        "Connection: Upgrade",
        `Sec-WebSocket-Key: ${clave}`,
        "Sec-WebSocket-Version: 13",
        `Authorization: Bearer ${autorizacion}`,
        "",
        ""
      ].join("\r\n")
    );
    let recibido = Buffer.alloc(0);
    const limite = setTimeout(() => socket.destroy(new Error("WSS sin respuesta")), 5000);
    while (!recibido.includes(Buffer.from("\r\n\r\n"))) {
      recibido = Buffer.concat([recibido, await nuevoDato(socket)]);
    }
    clearTimeout(limite);
    const corte = recibido.indexOf(Buffer.from("\r\n\r\n")) + 4;
    const cabecera = recibido.subarray(0, corte).toString("utf8");
    comprobar(/^HTTP\/1\.1 101\b/m.test(cabecera), `WSS no actualizó: ${cabecera}`);
    return new WebSocketContrato(socket, recibido.subarray(corte));
  }

  #procesar() {
    while (this.#buffer.length >= 2) {
      const primero = this.#buffer[0];
      const segundo = this.#buffer[1];
      const fin = Boolean(primero & 0x80);
      const opcode = primero & 0x0f;
      let largo = segundo & 0x7f;
      let desde = 2;
      if (largo === 126) {
        if (this.#buffer.length < 4) return;
        largo = this.#buffer.readUInt16BE(2);
        desde = 4;
      } else if (largo === 127) {
        if (this.#buffer.length < 10) return;
        const grande = this.#buffer.readBigUInt64BE(2);
        if (grande > BigInt(Number.MAX_SAFE_INTEGER)) {
          this.#socket.destroy(new Error("frame WSS demasiado grande"));
          return;
        }
        largo = Number(grande);
        desde = 10;
      }
      const enmascarado = Boolean(segundo & 0x80);
      const extraMascara = enmascarado ? 4 : 0;
      if (this.#buffer.length < desde + extraMascara + largo) return;
      let mascara = null;
      if (enmascarado) {
        mascara = this.#buffer.subarray(desde, desde + 4);
        desde += 4;
      }
      const datos = Buffer.from(this.#buffer.subarray(desde, desde + largo));
      if (mascara) {
        for (let i = 0; i < datos.length; i += 1) datos[i] ^= mascara[i % 4];
      }
      this.#buffer = this.#buffer.subarray(desde + largo);
      this.#frame(fin, opcode, datos);
    }
  }

  #frame(fin, opcode, datos) {
    if (opcode === 9) {
      this.#socket.write(frameControl(10, datos));
      return;
    }
    if (opcode === 8) {
      this.#cerrado = true;
      return;
    }
    if (opcode === 1) {
      this.#fragmentos = datos;
      this.#opcodeFragmento = opcode;
    } else if (opcode === 0) {
      this.#fragmentos = Buffer.concat([this.#fragmentos, datos]);
    } else {
      return;
    }
    if (!fin) return;
    if (this.#opcodeFragmento === 1) {
      try {
        const frame = JSON.parse(this.#fragmentos.toString("utf8"));
        this.#historial.push(frame);
        if (this.#historial.length > 40) this.#historial.shift();
        this.#cola.push(frame);
      } catch {
        // Una respuesta que no es JSON rompe la propiedad que se está probando.
      }
    }
    this.#fragmentos = Buffer.alloc(0);
    this.#opcodeFragmento = 0;
  }

  enviar(mensaje) {
    comprobar(!this.#cerrado, "El WebSocket se cerró antes de enviar");
    this.#socket.write(frameCliente(JSON.stringify(mensaje)));
  }

  marca() {
    return this.#historial.length;
  }

  async esperar(prueba, limite = 6000) {
    const hasta = Date.now() + limite;
    while (Date.now() < hasta) {
      const indice = this.#cola.findIndex(prueba);
      if (indice >= 0) return this.#cola.splice(indice, 1)[0];
      comprobar(!this.#cerrado, "El WebSocket se cerró antes del frame esperado");
      await esperar(10);
    }
    throw new Error(
      `No llegó un frame WSS a tiempo. Últimos: ${JSON.stringify(this.#historial.slice(-12))}`
    );
  }

  async esperarDesde(desde, prueba, limite = 6000) {
    const hasta = Date.now() + limite;
    while (Date.now() < hasta) {
      const visto = this.#historial.slice(desde).find(prueba);
      if (visto) return visto;
      comprobar(!this.#cerrado, "El WebSocket se cerró antes del frame esperado");
      await esperar(10);
    }
    throw new Error(
      `No llegó un frame WSS a tiempo. Últimos: ${JSON.stringify(this.#historial.slice(-12))}`
    );
  }

  async esperarCierre(limite = 5000) {
    const hasta = Date.now() + limite;
    while (Date.now() < hasta) {
      if (this.#cerrado || this.#socket.destroyed) return;
      await esperar(20);
    }
    throw new Error("El control remoto no se cerró al quitar el dispositivo");
  }

  cerrar() {
    if (this.#socket.destroyed) return;
    this.#socket.write(frameControl(8));
    this.#socket.end();
  }
}

function nuevoDato(socket) {
  return new Promise((resolve, reject) => {
    const alDato = (parte) => {
      limpiar();
      resolve(parte);
    };
    const alError = (error) => {
      limpiar();
      reject(error);
    };
    const limpiar = () => {
      socket.off("data", alDato);
      socket.off("error", alError);
    };
    socket.once("data", alDato);
    socket.once("error", alError);
  });
}

function comprobarRed(direccion) {
  const url = new URL(`https://${direccion}`);
  const host = url.hostname;
  const puerto = url.port;
  const locales = new Set(
    execFileSync("ip", ["-o", "-4", "addr", "show", "scope", "global"], {
      encoding: "utf8"
    })
      .split("\n")
      .map((linea) => linea.match(/\binet ([0-9.]+)\//)?.[1])
      .filter(Boolean)
  );
  locales.add("127.0.0.1");
  comprobar(locales.has(host), `El servidor escucha en una interfaz no local: ${host}`);

  const oyentes = execFileSync("ss", ["-Hltnp"], { encoding: "utf8" })
    .split("\n")
    .filter((linea) => linea.includes(`pid=${APP_PID}`) && linea.includes(`:${puerto}`));
  comprobar(oyentes.length > 0, `No se encontró el puerto ${puerto} de NB Sound`);
  const direccionesLocales = oyentes.map((linea) => linea.trim().split(/\s+/)[3]);
  comprobar(
    direccionesLocales.every(
      (direccionLocal) => !/^(?:0\.0\.0\.0|\*|\[::\]):/.test(direccionLocal)
    ),
    `El servidor escucha en todas las interfaces: ${oyentes.join(" | ")}`
  );

  const conexiones = execFileSync(
    "ss",
    ["-Htnp", "state", "established"],
    { encoding: "utf8" }
  )
    .split("\n")
    .filter((linea) => linea.includes(`pid=${APP_PID}`))
    .map((linea) => linea.replace(/\s+users:.*$/, "").trim().split(/\s+/).at(-1))
    .filter(Boolean);
  const privadas = conexiones.every((extremo) => {
    const limpio = extremo.replace(/^\[|\]$/g, "");
    const hostRemoto = limpio.slice(0, limpio.lastIndexOf(":"));
    return (
      hostRemoto === "127.0.0.1" ||
      hostRemoto === "::1" ||
      /^10\./.test(hostRemoto) ||
      /^192\.168\./.test(hostRemoto) ||
      /^172\.(?:1[6-9]|2\d|3[01])\./.test(hostRemoto) ||
      /^fe80:/i.test(hostRemoto)
    );
  });
  comprobar(privadas, `NB Sound abrió una conexión fuera de la red local: ${conexiones}`);
  return { host, puerto: Number(puerto), oyentes: oyentes.length, conexiones };
}

async function prepararCliente() {
  huellaEsperada = huellaDelCertificado();
  pemEsperado = readFileSync(CERT_PATH, "utf8");
  const emparejar = await invocar("movil_emparejar");
  const estado = await invocar("movil_estado");
  comprobar(estado.activo && estado.direccion, "El servidor móvil no arrancó");
  base = `https://${estado.direccion}`;

  const ping = await peticionJson({ ruta: "/api/v1/ping", autenticar: false });
  comprobar(
    ping.estado === 200 && ping.json?.version_protocolo === 1,
    `ping incompatible: ${ping.estado} ${ping.bytes.toString("utf8")}`
  );

  const pareja = await peticionJson({
    ruta: "/api/v1/pair",
    metodo: "POST",
    autenticar: false,
    cuerpo: {
      codigo: emparejar.codigo,
      nombre_dispositivo: "QA IA Fase 3",
      plataforma: "android"
    }
  });
  comprobar(
    pareja.estado === 200 && pareja.json?.device_token,
    `No se pudo emparejar con el código corto: ${pareja.estado} ${pareja.bytes.toString("utf8")}`
  );
  token = pareja.json.device_token;
  dispositivo = {
    id: pareja.json.dispositivo_id,
    nombre: pareja.json.nombre
  };
  return { emparejar, estado, ping: ping.json };
}

async function comprobarManifiesto() {
  const primero = await manifest(0);
  comprobar(primero.protocolo === 1, `Protocolo ${primero.protocolo}`);
  const since = primero.sync_version_actual;
  const segundo = await manifest(since);
  const repetidas =
    segundo.pistas.length +
    segundo.albums.length +
    segundo.artistas.length +
    segundo.playlists.length +
    segundo.tombstones.length;
  comprobar(repetidas === 0, `La segunda sincronización repitió ${repetidas} entidades`);

  const playlist = primero.playlists.find((p) => p.cover_url);
  comprobar(playlist, "Ninguna playlist trajo su mosaico");
  const mosaico = await peticion({ ruta: playlist.cover_url });
  comprobar(mosaico.estado === 200, `El mosaico respondió ${mosaico.estado}`);
  comprobar(/^image\//.test(mosaico.cabeceras["content-type"] ?? ""), "El mosaico no es imagen");
  const rutaMosaico = `${INFORMES}/fase3-mosaico.jpg`;
  writeFileSync(rutaMosaico, mosaico.bytes);
  const dimensiones = execFileSync(
    "magick",
    ["identify", "-format", "%wx%h", rutaMosaico],
    { encoding: "utf8" }
  );
  comprobar(dimensiones === "600x600", `Mosaico de ${dimensiones}`);

  const playlistNueva = await invocar("crear_playlist", {
    nombre: "QA Fase 3 incremental",
    descripcion: null
  });
  const delta = await manifest(since);
  comprobar(
    delta.playlists.length === 1 && delta.playlists[0].id === playlistNueva,
    `El delta no trajo solo la playlist nueva: ${JSON.stringify(delta.playlists)}`
  );
  const otras =
    delta.pistas.length + delta.albums.length + delta.artistas.length + delta.tombstones.length;
  comprobar(otras === 0, `El delta repitió ${otras} entidades ajenas`);
  await invocar("borrar_playlist", { id: playlistNueva });

  salida("manifiesto", {
    protocolo: primero.protocolo,
    version: since,
    pistas: primero.pistas.length,
    albumes: primero.albums.length,
    artistas: primero.artistas.length,
    playlists: primero.playlists.length,
    repetidasSegundaSync: repetidas,
    playlistMosaico: playlist.id,
    mosaicoBytes: mosaico.bytes.length,
    mosaico: dimensiones,
    deltaPlaylist: { id: playlistNueva, playlists: delta.playlists.length, otras }
  });
  return primero;
}

async function medirDescarga(manifiesto, idsLargos) {
  await invocar("reproductor_orden", {
    orden: { tipo: "reproducirPistas", ids: idsLargos, desde: 0 }
  });
  await invocar("reproductor_orden", {
    orden: { tipo: "aleatorio", activo: false }
  });
  await invocar("reproductor_orden", {
    orden: { tipo: "repeticion", modo: "ninguno" }
  });
  await esperarHasta(
    `(async () => {
      const e = await window.__TAURI_INTERNALS__.invoke("reproductor_estado");
      return e?.estado === "reproduciendo" && e.pistaId === ${idsLargos[0]};
    })()`
  );
  await esperar(800);
  const rutaWav = `${INFORMES}/fase3-descarga.wav`;
  const grabacion = iniciarGrabacion(rutaWav);
  try {
    await inspector.evaluarDirecto(`(() => {
      window.__qaDescargaTerminada = false;
      window.__qaCuadrosResultado = null;
      void (async () => {
      const intervalos = [];
      let anterior = performance.now();
      const inicio = anterior;
      await new Promise((resolve) => {
        const paso = (ahora) => {
          intervalos.push(ahora - anterior);
          anterior = ahora;
          if (window.__qaDescargaTerminada || ahora - inicio >= 180000) resolve();
          else requestAnimationFrame(paso);
        };
        requestAnimationFrame(paso);
      });
      const largos = intervalos.filter((ms) => ms > 50);
      window.__qaCuadrosResultado = {
        fotogramas: intervalos.length,
        maxMs: Math.max(...intervalos),
        p95Ms: [...intervalos].sort((a, b) => a - b)[
          Math.floor(intervalos.length * 0.95)
        ],
        mayores50: largos.length,
        duracionMs: performance.now() - inicio
      };
      })().catch((error) => {
        window.__qaCuadrosResultado = { error: error?.stack || String(error) };
      });
      return true;
    })()`);

    const inicio = process.hrtime.bigint();
    let totalBytes = 0;
    let completadas = 0;
    let siguiente = 0;
    const trabajadores = Array.from({ length: 4 }, async () => {
      while (true) {
        const indice = siguiente;
        siguiente += 1;
        if (indice >= manifiesto.pistas.length) return;
        const resultado = await descargarAudio(manifiesto.pistas[indice]);
        totalBytes += resultado.bytes;
        completadas += 1;
        if (completadas % 250 === 0) {
          console.log(
            `QA_MOVIL_PROGRESO ${JSON.stringify({ completadas, total: manifiesto.pistas.length, bytes: totalBytes })}`
          );
        }
      }
    });
    await Promise.all(trabajadores);
    const duracionSeg = Number(process.hrtime.bigint() - inicio) / 1e9;
    await inspector.evaluar(`window.__qaDescargaTerminada = true`);
    const metricas = await esperarHasta(
      `window.__qaCuadrosResultado`,
      Boolean,
      10000
    );
    comprobar(!metricas.error, `La medición de fotogramas falló: ${metricas.error}`);
    await grabacion.detener();
    comprobar(metricas.mayores50 === 0, `Fotogramas largos: ${JSON.stringify(metricas)}`);
    return { rutaWav, metricas, completadas, totalBytes, duracionSeg };
  } catch (error) {
    await inspector.evaluar(`window.__qaDescargaTerminada = true`).catch(() => {});
    await grabacion.detener();
    throw error;
  }
}

async function medirControl() {
  const audibles = filas(`
    SELECT p.id
    FROM pistas p JOIN stems s ON s.pista_id = p.id
    WHERE p.estado = 'biblioteca' AND s.estado = 'lista' AND p.duracion_seg > 40
    ORDER BY p.duracion_seg DESC, p.id LIMIT 3;
  `).map(([id]) => Number(id));
  comprobar(audibles.length === 3, `No hay tres pistas con instrumental: ${audibles}`);
  const direccion = new URL(base);

  websocket = await WebSocketContrato.abrir({
    host: direccion.hostname,
    puerto: Number(direccion.port),
    autorizacion: token
  });
  const inicial = await websocket.esperar((f) => f.tipo === "estado");

  async function comando(accion, extra, pruebaEstado) {
    const ackEsperado = websocket.esperar(
      (f) => f.tipo === "ack" && (f.accion === accion || f.accion?.accion === accion)
    );
    const estadoEsperado = pruebaEstado
      ? websocket.esperar((f) => f.tipo === "estado" && pruebaEstado(f))
      : null;
    websocket.enviar({ tipo: "comando", accion, ...extra });
    await ackEsperado;
    return estadoEsperado ? estadoEsperado : null;
  }

  await comando(
    "set_queue",
    { ids: audibles, indice: 0, posicion_seg: 0 },
    (f) => f.pista?.id === audibles[0]
  );
  const colaInicial = await websocket.esperar(
    (f) =>
      f.tipo === "cola" &&
      JSON.stringify(f.items.map((i) => i.id)) === JSON.stringify(audibles) &&
      f.indice === 0
  );
  const pausado = await comando("play_pause", {}, (f) => f.reproduciendo === false);
  const reanudado = await comando("play_pause", {}, (f) => f.reproduciendo === true);
  const siguiente = await comando("next", {}, (f) => f.pista?.id === audibles[1]);
  const anterior = await comando("prev", {}, (f) => f.pista?.id === audibles[0]);
  const buscado = await comando("seek", { posicion_seg: 17.5 }, (f) => f.posicion_seg >= 17.4);
  const volumen = await comando("set_volume", { volumen: 37 }, (f) => f.volumen === 37);
  const aleatorio = await comando("shuffle", { activo: true }, (f) => f.aleatorio === true);
  const repeticion = await comando("repeat", { modo: "uno" }, (f) => f.modo_repeticion === "uno");
  const karaoke = await comando("karaoke", {}, (f) => f.karaoke_activo === true);
  await comando("shuffle", { activo: false }, (f) => f.aleatorio === false);

  await comando(
    "set_queue",
    { ids: audibles, indice: 0, posicion_seg: 0 },
    (f) => f.pista?.id === audibles[0]
  );
  const marcaTelefono = websocket.marca();
  await comando("move_queue", { desde: 0, hasta: 1 }, () => true);
  const colaTelefono = await websocket.esperarDesde(
    marcaTelefono,
    (f) =>
      f.tipo === "cola" &&
      JSON.stringify(f.items.map((i) => i.id)) ===
        JSON.stringify([audibles[1], audibles[0], audibles[2]])
  );

  const marcaEquipo = websocket.marca();
  await invocar("reproductor_orden", {
    orden: { tipo: "mover", desde: 0, hasta: 2 }
  });
  const colaEquipo = await websocket.esperarDesde(
    marcaEquipo,
    (f) =>
      f.tipo === "cola" &&
      JSON.stringify(f.items.map((i) => i.id)) ===
        JSON.stringify([audibles[0], audibles[2], audibles[1]])
  );
  const estadoEquipo = await invocar("reproductor_estado");
  comprobar(
    JSON.stringify(estadoEquipo.cola) ===
      JSON.stringify(colaEquipo.items.map((i) => i.id)),
    `La cola del equipo y el móvil difieren: ${JSON.stringify({
      equipo: estadoEquipo.cola,
      movil: colaEquipo.items.map((i) => i.id)
    })}`
  );

  salida("control", {
    inicial: {
      pista: inicial.pista?.id,
      reproduciendo: inicial.reproduciendo,
      karaokeDisponible: inicial.karaoke_disponible
    },
    pistas: audibles,
    colaInicial: colaInicial.items.map((i) => i.id),
    colaTelefono: colaTelefono.items.map((i) => i.id),
    colaEquipo: colaEquipo.items.map((i) => i.id),
    playPause: [pausado.reproduciendo, reanudado.reproduciendo],
    siguiente: siguiente.pista.id,
    anterior: anterior.pista.id,
    posicionSeg: buscado.posicion_seg,
    volumen: volumen.volumen,
    aleatorio: aleatorio.aleatorio,
    repeticion: repeticion.modo_repeticion,
    karaoke: karaoke.karaoke_activo,
    controles: [
      "play_pause",
      "next",
      "prev",
      "seek",
      "set_volume",
      "shuffle",
      "repeat",
      "karaoke",
      "move_queue",
      "set_queue"
    ]
  });
}

async function comprobarDondeSuena() {
  const telefonos = await esperarHasta(
    `window.__TAURI_INTERNALS__.invoke("movil_telefonos")`,
    (lista) =>
      lista.some((t) => t.id === dispositivo.id && t.nombre === dispositivo.nombre && t.controlando),
    10000
  );
  const telefono = telefonos.find((t) => t.id === dispositivo.id);
  await inspector.evaluar(`(() => {
    const boton = document.querySelector(".reproductor button[aria-haspopup='menu']");
    if (!boton) throw new Error("No existe el menú de la barra");
    boton.click();
    return true;
  })()`);
  const texto = await esperarHasta(
    `document.querySelector(".menu[role='menu']")?.innerText ?? ""`,
    (valor) =>
      valor.toLowerCase().includes("dónde suena") &&
      valor.includes(dispositivo.nombre) &&
      valor.includes(`${dispositivo.nombre} lo está controlando`),
    10000
  );
  await inspector.evaluar(`document.querySelector(".reproductor button[aria-haspopup='menu']")?.click()`);
  salida("donde_suena", {
    dispositivo: telefono,
    texto: texto.split("\n").filter(Boolean)
  });
}

async function quitarDispositivo() {
  const id = dispositivo.id;
  await invocar("movil_quitar", { id });
  await websocket.esperarCierre();
  websocket = null;
  const rechazo = await peticionJson({ ruta: "/api/v1/manifest?since=0" });
  comprobar(rechazo.estado === 401, `El token revocado respondió ${rechazo.estado}`);
  const restantes = await invocar("movil_telefonos");
  comprobar(!restantes.some((t) => t.id === id), "El dispositivo sigue en la lista");
  salida("revocacion", {
    dispositivo: id,
    websocketCerrado: true,
    manifestTrasQuitar: rechazo.estado,
    sigueEnLista: false
  });
}

async function main() {
  comprobar(DB && APP_PID && INFORMES, "Faltan variables del arnés móvil");
  const cliente = await prepararCliente();
  const red = comprobarRed(cliente.estado.direccion);
  salida("red", {
    direccion: cliente.estado.direccion,
    bind: red.host,
    puerto: red.puerto,
    oyentes: red.oyentes,
    conexionesLocales: red.conexiones,
    protocolo: cliente.ping.version_protocolo,
    codigoCorto: cliente.emparejar.codigo.length
  });

  const primero = await comprobarManifiesto();
  const idsLargos = filas(`
    SELECT id FROM pistas
    WHERE estado = 'biblioteca' AND duracion_seg > 120
    ORDER BY duracion_seg DESC, id LIMIT 3;
  `).map(([id]) => Number(id));
  if (process.env.NB_QA_SALTAR_DESCARGA !== "1") {
    const descarga = await medirDescarga(primero, idsLargos);
    const analizador = ejecutarAnalizador("una_reproduccion_continua_no_tiene_huecos", {
      NB_QA_WAV: descarga.rutaWav
    });
    const informe = analizador
      .split("\n")
      .find((linea) => linea.includes("INFORME_QA"));
    comprobar(informe, "El analizador no devolvió el informe de continuidad");
    salida("descarga", {
      pistas: descarga.completadas,
      bytes: descarga.totalBytes,
      duracionDescargaSeg: descarga.duracionSeg,
      fotogramas: descarga.metricas,
      analizador: JSON.parse(informe.slice(informe.indexOf("{")))
    });
  }

  await medirControl();
  await comprobarDondeSuena();
  await quitarDispositivo();
}

try {
  await main();
} finally {
  websocket?.cerrar();
  inspector.cerrar();
}
