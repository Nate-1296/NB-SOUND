#!/usr/bin/env node

import { execFileSync, spawn, spawnSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { request as httpsRequest } from "node:https";
import { Inspector, esperar } from "./inspector.mjs";

const ESCENARIO = process.argv[2];
const DB = process.env.NB_QA_DB;
const APP_PID = Number(process.env.NB_QA_APP_PID ?? 0);
const RAIZ = process.env.NB_QA_RAIZ ?? process.cwd();
let CERT_FINGERPRINT = process.env.NB_QA_CERT_FINGERPRINT ?? "";
const CERT_PATH = process.env.NB_QA_CERT_PATH ?? "";
const inspector = await Inspector.conectar();

function salida(nombre, datos) {
  console.log(`QA_UI ${JSON.stringify({ escenario: nombre, datos })}`);
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

function esperaHasta(expresion, prueba = Boolean, limite = 8000) {
  return (async () => {
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
    let pagina = "";
    try {
      pagina = JSON.stringify(
        await inspector.evaluar(
          `({url: location.href, titulo: document.title, texto: document.body?.innerText.slice(0, 300)})`
        )
      );
    } catch {}
    throw new Error(
      `No se cumplió: ${expresion}. Último valor: ${JSON.stringify(ultimo)}. Página: ${pagina}`
    );
  })();
}

async function ir(ruta, selector = ".carcasa") {
  if (ruta === "/") {
    const enlace = await inspector.evaluar(
      `Boolean(document.querySelector('.destino[href="/"]'))`
    );
    if (enlace) {
      await inspector.evaluar(
        `(() => { document.querySelector('.destino[href="/"]').click(); return true; })()`
      );
      await esperaHasta(`location.pathname === "/" && Boolean(document.querySelector(${JSON.stringify(selector)}))`);
      await esperar(150);
      return;
    }
  }
  await inspector.evaluarDirecto(
    `(() => {
      location.href = ${JSON.stringify(`tauri://localhost${ruta}`)};
      return true;
    })()`
  );
  await esperaHasta(
    `document.readyState === "complete" && Boolean(document.querySelector(${JSON.stringify(selector)}))`
  );
  await esperar(150);
}

async function invocar(comando, argumentos = {}) {
  return inspector.evaluar(
    `window.__TAURI_INTERNALS__.invoke(${JSON.stringify(comando)}, ${JSON.stringify(argumentos)})`
  );
}

async function clicTexto(selector, texto) {
  return inspector.evaluar(`(() => {
    const nodo = [...document.querySelectorAll(${JSON.stringify(selector)})]
      .find((n) => n.textContent.trim() === ${JSON.stringify(texto)});
    if (!nodo) throw new Error("No existe " + ${JSON.stringify(selector)} + " con " + ${JSON.stringify(texto)});
    nodo.click();
    return true;
  })()`);
}

async function clicContiene(selector, texto) {
  return inspector.evaluar(`(() => {
    const nodo = [...document.querySelectorAll(${JSON.stringify(selector)})]
      .find((n) => n.textContent.includes(${JSON.stringify(texto)}));
    if (!nodo) throw new Error("No existe " + ${JSON.stringify(selector)} + " con " + ${JSON.stringify(texto)});
    nodo.click();
    return true;
  })()`);
}

async function escribir(selector, valor) {
  return inspector.evaluar(`(() => {
    const campo = document.querySelector(${JSON.stringify(selector)});
    if (!campo) throw new Error("No existe el campo " + ${JSON.stringify(selector)});
    const prototipo = campo instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototipo, "value").set.call(campo, ${JSON.stringify(valor)});
    campo.dispatchEvent(new Event("input", { bubbles: true }));
    campo.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  })()`);
}

async function tecla(key, opciones = {}, elemento = "window") {
  return inspector.evaluar(`(() => {
    const destino = ${elemento === "window" ? "window" : `document.querySelector(${JSON.stringify(elemento)})`};
    if (!destino) throw new Error("No existe el destino del teclado");
    destino.dispatchEvent(new KeyboardEvent("keydown", Object.assign({
      key: ${JSON.stringify(key)}, bubbles: true, cancelable: true
    }, ${JSON.stringify(opciones)})));
    return true;
  })()`);
}

function peticionJson({ base, ruta, metodo = "GET", token, cuerpo }) {
  return new Promise((resolve, reject) => {
    const url = new URL(ruta, base);
    const datos = cuerpo === undefined ? null : JSON.stringify(cuerpo);
    const solicitud = httpsRequest(
      {
        hostname: url.hostname,
        port: url.port,
        path: url.pathname + url.search,
        method: metodo,
        rejectUnauthorized: false,
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(datos
            ? {
                "Content-Type": "application/json",
                "Content-Length": Buffer.byteLength(datos)
              }
            : {})
        }
      },
      (respuesta) => {
        let texto = "";
        respuesta.setEncoding("utf8");
        respuesta.on("data", (parte) => {
          texto += parte;
        });
        respuesta.on("end", () => {
          let json = null;
          try {
            json = JSON.parse(texto);
          } catch {
            // Se informa junto con el código de estado.
          }
          resolve({ estado: respuesta.statusCode, json, texto, cabeceras: respuesta.headers });
        });
      }
    );
    solicitud.on("socket", (socket) => {
      socket.once("secureConnect", () => {
        const huella = socket.getPeerCertificate().fingerprint256?.replaceAll(":", "").toUpperCase();
        const fijada = CERT_FINGERPRINT.replaceAll(":", "").toUpperCase();
        if (fijada && huella !== fijada) {
          solicitud.destroy(new Error(`huella TLS inesperada: ${huella}`));
        }
      });
    });
    solicitud.on("error", reject);
    if (datos) solicitud.write(datos);
    solicitud.end();
  });
}

async function abrirMovil() {
  const emparejar = await invocar("movil_emparejar");
  const estado = await invocar("movil_estado");
  if (!estado.activo || !estado.direccion) {
    throw new Error(`El servidor móvil no arrancó: ${JSON.stringify(estado)}`);
  }
  if (!CERT_FINGERPRINT && CERT_PATH && existsSync(CERT_PATH)) {
    const salidaOpenSsl = execFileSync(
      "openssl",
      ["x509", "-in", CERT_PATH, "-noout", "-fingerprint", "-sha256"],
      { encoding: "utf8" }
    );
    CERT_FINGERPRINT = salidaOpenSsl.split("=").at(-1).trim().replaceAll(":", "").toUpperCase();
  }
  const base = `https://${estado.direccion}`;
  const pareja = await peticionJson({
    base,
    ruta: "/api/v1/pair",
    metodo: "POST",
    cuerpo: {
      codigo: emparejar.codigo,
      nombre_dispositivo: "QA IA",
      plataforma: "desktop"
    }
  });
  if (pareja.estado !== 200 || !pareja.json?.device_token) {
    throw new Error(`No se pudo emparejar el cliente QA: ${pareja.estado} ${pareja.texto}`);
  }
  return { base, token: pareja.json.device_token, estado, codigo: emparejar.codigo };
}

async function manifest(cliente, since = 0) {
  const respuesta = await peticionJson({
    base: cliente.base,
    ruta: `/api/v1/manifest?since=${since}&limit=10000`,
    token: cliente.token
  });
  if (respuesta.estado !== 200) {
    throw new Error(`manifest respondió ${respuesta.estado}: ${respuesta.texto}`);
  }
  return respuesta.json;
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

async function asegurarFlujoNulo() {
  let indice = null;
  for (let i = 0; i < 100 && indice === null; i += 1) {
    indice = indiceFlujoApp();
    if (indice === null) await esperar(50);
  }
  if (indice === null) throw new Error("No apareció el flujo de audio de NB Sound");
  execFileSync("pactl", ["move-sink-input", String(indice), "nb_sound_qa_ui"]);
  await esperar(100);
  return indice;
}

async function iniciarGrabacion(ruta) {
  const indice = await asegurarFlujoNulo();
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
  await esperar(120);
  return {
    async detener() {
      proceso.kill("SIGINT");
      await new Promise((resolve) => proceso.once("exit", resolve));
    }
  };
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

function hilo(nombre) {
  if (!APP_PID) throw new Error("falta NB_QA_APP_PID");
  const carpeta = `/proc/${APP_PID}/task`;
  for (const tid of readdirSync(carpeta)) {
    if (readFileSync(`${carpeta}/${tid}/comm`, "utf8").trim() === nombre) return tid;
  }
  return null;
}

function ticksHilo(tid) {
  const texto = readFileSync(`/proc/${APP_PID}/task/${tid}/stat`, "utf8");
  const resto = texto.slice(texto.lastIndexOf(")") + 2).trim().split(/\s+/);
  return Number(resto[11]) + Number(resto[12]);
}

function contarVentanas() {
  const resultado = spawnSync("xdotool", ["search", "--onlyvisible", "--name", "^NB Sound$"], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"]
  });
  return (resultado.stdout ?? "").trim().split("\n").filter(Boolean).length;
}

async function escenarioInicio() {
  await ir("/");
  await esperaHasta(`document.querySelector(".saludo h1") !== null`, Boolean, 12000);
  const datos = await inspector.evaluar(`(() => {
    const textos = [...document.querySelectorAll("h2.seccion")].map((n) => n.textContent.trim());
    return {
      saludo: document.querySelector(".saludo h1")?.textContent.trim() ?? null,
      retomar: document.querySelector("#inicio-retomar")?.textContent.trim() ?? null,
      marquesina: Boolean(document.querySelector(".marquesina")),
      destacado: document.querySelector("#inicio-destacado")?.textContent.trim() ?? null,
      secciones: textos,
      vuelve: document.querySelectorAll(".vuelve > li").length,
      top: document.querySelectorAll(".podio-tarjeta, .fila-top").length
    };
  })()`);
  const apariencia = await invocar("apariencia");
  if (!datos.saludo?.includes(apariencia.nombreUsuario)) {
    throw new Error(`El saludo no lleva el nombre: ${datos.saludo}`);
  }
  if (!datos.retomar || !datos.marquesina || !datos.destacado) {
    throw new Error("Inicio no muestra Retomar y el álbum destacado");
  }
  for (const esperada of ["Vuelve a tu música", "Tu top 10"]) {
    if (!datos.secciones.some((seccion) => seccion.includes(esperada))) {
      throw new Error(`Falta la sección ${esperada}: ${datos.secciones.join(", ")}`);
    }
  }
  salida("inicio", { apariencia, dom: datos });
}

async function escenarioTemas() {
  await ir("/ajustes", ".ajustes");
  await clicTexto(".pestana-seccion", "Apariencia");
  await esperaHasta(`document.querySelectorAll(".temas .tema").length === 63`, Boolean, 15000);
  await inspector.instalarCapturaDeErrores();
  const aplicados = await inspector.evaluar(`(async () => {
    const botones = [...document.querySelectorAll(".temas .tema")];
    const resultados = [];
    for (const boton of botones) {
      const maqueta = boton.querySelector(".maqueta-tema");
      const esperado = getComputedStyle(maqueta).getPropertyValue("--fondo").trim().toLowerCase();
      boton.click();
      const limite = performance.now() + 4000;
      let real = "";
      while (performance.now() < limite) {
        real = getComputedStyle(document.documentElement)
          .getPropertyValue("--m3c-surface").trim().toLowerCase();
        if (real === esperado) break;
        await new Promise((r) => setTimeout(r, 20));
      }
      resultados.push({
        nombre: boton.textContent.trim(),
        esperado,
        real,
        aplicado: real === esperado
      });
    }
    return resultados;
  })()`);
  const fallidos = aplicados.filter((tema) => !tema.aplicado);
  if (fallidos.length > 0) {
    throw new Error(`Temas que no se aplicaron: ${JSON.stringify(fallidos.slice(0, 5))}`);
  }

  await clicTexto(".temas .tema", "Sangre de Dragón");
  await esperaHasta(
    `getComputedStyle(document.documentElement).getPropertyValue("--m3c-surface").trim() === "#0e0000"`
  );
  await clicContiene(".tipografia", "Fira Sans");
  await esperaHasta(
    `getComputedStyle(document.documentElement).getPropertyValue("--ns-font-ui").includes("Fira Sans")`
  );
  await clicContiene(".escalas button", "125");
  await esperaHasta(`document.documentElement.style.fontSize === "125%"`);
  const inmediato = await inspector.evaluar(`({
    tema: getComputedStyle(document.documentElement).getPropertyValue("--m3c-surface").trim(),
    tipografia: getComputedStyle(document.documentElement).getPropertyValue("--ns-font-ui").trim(),
    escala: document.documentElement.style.fontSize
  })`);
  await esperar(300);
  const errores = await inspector.errores();
  if (errores.length > 0) throw new Error(`Errores de consola: ${errores.join(" | ")}`);
  salida("temas", {
    temasAplicados: aplicados.length,
    inmediato,
    erroresConsola: errores.length
  });
}

async function escenarioPrepararArranque() {
  await ir("/ajustes", ".ajustes");
  await clicTexto(".pestana-seccion", "Apariencia");
  await esperaHasta(`document.querySelectorAll(".temas .tema").length === 63`, Boolean, 15000);
  await clicTexto(".temas .tema", "Sangre de Dragón");
  await esperaHasta(
    `getComputedStyle(document.documentElement).getPropertyValue("--m3c-surface").trim() === "#0e0000"`
  );
  await clicContiene(".tipografia", "Fira Sans");
  await esperaHasta(
    `getComputedStyle(document.documentElement).getPropertyValue("--ns-font-ui").includes("Fira Sans")`
  );
  await clicContiene(".escalas button", "100");
  await esperaHasta(`document.documentElement.style.fontSize === "100%"`);
  await esperar(300);
  salida("preparar_arranque", {
    tema: await inspector.evaluar(
      `getComputedStyle(document.documentElement).getPropertyValue("--m3c-surface").trim()`
    ),
    tipografia: await inspector.evaluar(
      `getComputedStyle(document.documentElement).getPropertyValue("--ns-font-ui").trim()`
    )
  });
}

async function escenarioVerificarArranque() {
  const datos = await esperaHasta(`(() => {
    const raiz = getComputedStyle(document.documentElement);
    return {
      tema: raiz.getPropertyValue("--m3c-surface").trim(),
      tipografia: raiz.getPropertyValue("--ns-font-ui").trim(),
      esquema: document.documentElement.dataset.esquema,
      saludo: document.querySelector(".saludo h1")?.textContent.trim() ?? null
    };
  })()`, (valor) => valor?.tema === "#0e0000" && valor?.tipografia.includes("Fira Sans"), 15000);
  salida("arranque", datos);
}

async function escenarioBiblioteca() {
  await ir("/biblioteca?vista=pistas", ".vista");
  await esperaHasta(`document.querySelectorAll(".pistas, .rejilla, .lista").length > 0`, Boolean, 12000);
  const campo = 'input[aria-label="Buscar por pista, artista, álbum o letra"]';
  await escribir(campo, "Taylor");
  await esperar(650);
  const busqueda = await inspector.evaluar(`({
    texto: document.querySelector(${JSON.stringify(campo)})?.value,
    cuenta: document.querySelector(".cuenta")?.textContent.trim(),
    titulos: [...document.querySelectorAll(".fila .titulo, .tarjeta .nombre")]
      .slice(0, 8).map((n) => n.textContent.trim())
  })`);
  if (busqueda.titulos.length === 0) throw new Error("La búsqueda no dejó resultados en el DOM");

  await escribir(campo, "");
  await esperar(450);
  await clicTexto(".ficha", "Favoritas");
  await esperar(500);
  const filtro = await inspector.evaluar(`({
    activa: document.querySelector(".ficha[aria-pressed='true']")?.textContent.trim(),
    filas: [...document.querySelectorAll(".fila")].length,
    favoritas: [...document.querySelectorAll(".fila button.favorita")]
      .every((n) => n.getAttribute("aria-pressed") === "true")
  })`);
  if (filtro.activa !== "Favoritas" || filtro.filas === 0 || !filtro.favoritas) {
    throw new Error(`Filtro de favoritas incoherente: ${JSON.stringify(filtro)}`);
  }
  await clicTexto(".ficha", "Favoritas");
  await esperar(400);

  const orden = await inspector.evaluar(`(async () => {
    const selector = [...document.querySelectorAll(".control-orden .menu-selector")]
      .find((n) => n.querySelector(".rotulo")?.textContent.trim() === "Orden");
    selector.querySelector(".gatillo").click();
    await new Promise((r) => setTimeout(r, 80));
    const opcion = [...document.querySelectorAll(".capa-popover:popover-open .opcion")]
      .find((n) => n.textContent.trim() === "Título Z-A");
    opcion.click();
    await new Promise((r) => setTimeout(r, 550));
    return [...document.querySelectorAll(".fila .titulo, .tarjeta .nombre")]
      .slice(0, 20).map((n) => n.textContent.trim());
  })()`);
  const ordenada = orden.every(
    (titulo, indice) => indice === 0 || orden[indice - 1].localeCompare(titulo, "es") >= 0
  );
  if (!ordenada) throw new Error(`La lista no quedó en Título Z-A: ${JSON.stringify(orden.slice(0, 8))}`);

  await ir("/biblioteca?vista=albumes", ".vista");
  await esperaHasta(`document.querySelector("a.tarjeta") !== null`, Boolean, 12000);
  const album = await inspector.evaluar(`(() => {
    const enlace = document.querySelector("a.tarjeta");
    const nombre = enlace.querySelector(".nombre")?.textContent.trim();
    enlace.click();
    return nombre;
  })()`);
  await esperaHasta(`location.pathname.includes("/biblioteca/album") && Boolean(document.querySelector("h1"))`);
  const albumDom = await inspector.evaluar(`({
    url: location.href,
    titulo: document.querySelector("h1")?.textContent.trim(),
    pistas: document.querySelectorAll(".pistas li").length
  })`);
  if (!albumDom.titulo || albumDom.pistas === 0) throw new Error("El álbum no abrió con sus pistas");

  await ir("/biblioteca?vista=artistas", ".vista");
  await esperaHasta(`document.querySelector("a.tarjeta") !== null`, Boolean, 12000);
  const artista = await inspector.evaluar(`(() => {
    const enlace = document.querySelector("a.tarjeta");
    const nombre = enlace.querySelector(".nombre")?.textContent.trim();
    enlace.click();
    return nombre;
  })()`);
  await esperaHasta(`location.pathname.includes("/biblioteca/artista") && Boolean(document.querySelector("h1"))`);
  const artistaDom = await inspector.evaluar(`({
    url: location.href,
    titulo: document.querySelector("h1")?.textContent.trim()
  })`);
  if (!artistaDom.titulo) throw new Error("El artista no abrió");

  await ir("/biblioteca?vista=pistas", ".vista");
  await esperaHasta(`document.querySelector(".lista, .rejilla") !== null`, Boolean, 12000);
  await inspector.evaluar(`(() => {
    document.querySelector("button[aria-label='Lista']")?.click();
    return true;
  })()`);
  await esperaHasta(`document.querySelector(".lista[role='list']") !== null`, Boolean, 10000);
  const cuadros = await inspector.evaluar(`(async () => {
    const lista = document.querySelector(".lista[role='list']");
    const intervalos = [];
    let anterior = performance.now();
    let subiendo = false;
    const hasta = anterior + 2800;
    await new Promise((resolve) => {
      const paso = (ahora) => {
        intervalos.push(ahora - anterior);
        anterior = ahora;
        const maximo = lista.scrollHeight - lista.clientHeight;
        lista.scrollTop = subiendo
          ? Math.max(0, lista.scrollTop - 260)
          : Math.min(maximo, lista.scrollTop + 260);
        if (lista.scrollTop <= 0 || lista.scrollTop >= maximo) subiendo = !subiendo;
        if (ahora < hasta) requestAnimationFrame(paso);
        else resolve();
      };
      requestAnimationFrame(paso);
    });
    lista.scrollTop = Math.min(lista.scrollHeight - lista.clientHeight, lista.clientHeight * 2);
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    await new Promise((r) => setTimeout(r, 300));
    const limiteCarga = performance.now() + 3000;
    while (performance.now() < limiteCarga) {
      const visibles = [...document.querySelectorAll(".fila img, .rejilla img")]
        .filter((img) => {
          const r = img.getBoundingClientRect();
          return r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth;
        });
      if (visibles.every((img) => img.complete)) break;
      await new Promise((r) => setTimeout(r, 50));
    }
    const imagenes = [...document.querySelectorAll(".fila img, .rejilla img")]
      .filter((img) => {
        const r = img.getBoundingClientRect();
        return r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth;
      });
    const largos = intervalos.filter((ms) => ms > 50);
    let racha = 0;
    let rachaMaxima = 0;
    for (const ms of intervalos) {
      racha = ms > 50 ? racha + 1 : 0;
      rachaMaxima = Math.max(rachaMaxima, racha);
    }
    return {
      fotogramas: intervalos.length,
      maxMs: Math.max(...intervalos),
      p95Ms: [...intervalos].sort((a, b) => a - b)[Math.floor(intervalos.length * 0.95)],
      mayores50: largos.length,
      rachaMayor50: rachaMaxima,
      imagenesVisibles: imagenes.length,
      portadasCargadas: imagenes.filter((img) => img.complete && img.naturalWidth > 0).length,
      portadasFallidas: imagenes
        .filter((img) => !img.complete || img.naturalWidth === 0)
        .map((img) => img.currentSrc || img.src)
    };
  })()`);
  if (cuadros.rachaMayor50 >= 2) {
    throw new Error(`Fotogramas largos sostenidos: ${JSON.stringify(cuadros)}`);
  }
  if (cuadros.imagenesVisibles > 0 && cuadros.portadasCargadas !== cuadros.imagenesVisibles) {
    throw new Error(`Portadas sin cargar al parar: ${JSON.stringify(cuadros)}`);
  }

  salida("biblioteca", {
    busqueda,
    filtro,
    ordenTituloDesc: ordenada,
    album: { nombre: album, ...albumDom },
    artista: { nombre: artista, ...artistaDom },
    cuadros
  });
}

async function menuDe(selectorDisparador, texto) {
  await inspector.evaluar(`(() => {
    const boton = document.querySelector(${JSON.stringify(selectorDisparador)});
    if (!boton) throw new Error("No existe el menú " + ${JSON.stringify(selectorDisparador)});
    boton.click();
    return true;
  })()`);
  await esperaHasta(`document.querySelector(".menu:popover-open") !== null`);
  await inspector.evaluar(`(() => {
    const opcion = [...document.querySelectorAll(".menu:popover-open .opcion")]
      .find((n) => n.textContent.trim() === ${JSON.stringify(texto)});
    if (!opcion) throw new Error("No existe la acción " + ${JSON.stringify(texto)});
    opcion.click();
    return true;
  })()`);
}

async function escenarioPlaylists() {
  const cliente = await abrirMovil();
  const inicial = await manifest(cliente);
  const inicioVersion = inicial.sync_version_actual;
  const pistas = filas(`
    SELECT p.id, p.titulo
    FROM pistas p
    LEFT JOIN albumes a ON a.id = p.album_id
    WHERE p.estado = 'biblioteca' AND p.favorita = 0
      AND (p.portada_id IS NOT NULL OR a.portada_id IS NOT NULL)
    ORDER BY p.id LIMIT 2;
  `).map(([id, titulo]) => ({ id: Number(id), titulo }));
  if (pistas.length < 2) throw new Error("No hay dos pistas con portada para la playlist QA");

  await ir("/playlists", ".vista");
  await esperaHasta(`document.querySelector(".vista .cabecera") !== null`, Boolean, 12000);
  await inspector.evaluar(`(() => {
    const boton = [...document.querySelectorAll(".acciones .boton")]
      .find((n) => n.textContent.includes("Nueva playlist"));
    boton.click();
    return true;
  })()`);
  await esperaHasta(`document.querySelector("dialog[open] input[maxlength='120']") !== null`);
  await escribir("dialog[open] input[maxlength='120']", "QA IA");
  await inspector.evaluar(`(() => {
    document.querySelector("dialog[open] button[type='submit']").click();
    return true;
  })()`);
  await esperaHasta(`location.pathname === "/playlists/ver" && Boolean(document.querySelector("h1"))`, Boolean, 10000);
  const playlistId = Number(new URL(await inspector.evaluar("location.href")).searchParams.get("id"));

  await clicTexto("button.pildora", "Añadir canciones");
  await esperaHasta(`document.querySelector(".anadir input[type='search']") !== null`);
  for (const pista of pistas) {
    await escribir(".anadir input[type='search']", pista.titulo);
    await esperaHasta(`document.querySelector(".resultados .mini:not(:disabled)") !== null`, Boolean, 5000);
    await inspector.evaluar(`(() => {
      document.querySelector(".resultados .mini:not(:disabled)").click();
      return true;
    })()`);
    await esperar(500);
  }
  await esperaHasta(`document.querySelectorAll(".pistas > li").length === 2`, Boolean, 8000);
  let ordenFilas = await inspector.evaluar(
    `[...document.querySelectorAll(".pistas > li .datos .titulo")].map((n) => n.textContent.trim())`
  );

  await menuDe(".pistas > li:nth-child(2) .acciones .disparador", "Subir");
  await esperaHasta(
    `document.querySelectorAll(".pistas > li .datos .titulo")[0]?.textContent.trim() === ${JSON.stringify(pistas[1].titulo)}`
  );
  ordenFilas = await inspector.evaluar(
    `[...document.querySelectorAll(".pistas > li .datos .titulo")].map((n) => n.textContent.trim())`
  );
  const trasOrden = await manifest(cliente, inicioVersion);
  const playlistOrdenada = trasOrden.playlists.find((p) => p.id === playlistId);
  if (!playlistOrdenada || playlistOrdenada.pista_ids.join(",") !== pistas.slice().reverse().map((p) => p.id).join(",")) {
    throw new Error(`El manifest no recibió el orden: ${JSON.stringify(playlistOrdenada)}`);
  }

  await menuDe(".acciones .disparador", "Renombrar");
  await esperaHasta(`document.querySelector("dialog[open] input[maxlength='120']") !== null`);
  await escribir("dialog[open] input[maxlength='120']", "QA IA renombrada");
  await inspector.evaluar(`(() => {
    document.querySelector("dialog[open] button[type='submit']").click();
    return true;
  })()`);
  await esperaHasta(`document.querySelector("h1")?.textContent.trim() === "QA IA renombrada"`, Boolean, 8000);

  await inspector.evaluar(`(() => {
    const fila = document.querySelector(".pistas > li");
    const favorita = fila.querySelector("button.favorita");
    if (favorita.getAttribute("aria-pressed") !== "true") favorita.click();
    return true;
  })()`);
  await esperaHasta(
    `document.querySelector(".pistas > li button.favorita")?.getAttribute("aria-pressed") === "true"`
  );
  const favoritaId = Number(
    await inspector.evaluar(`(() => {
      const fila = document.querySelector(".pistas > li");
      const boton = fila.querySelector("button.favorita");
      return boton.closest(".fila").querySelector(".datos .titulo").textContent.trim() ===
        ${JSON.stringify(pistas[1].titulo)} ? ${pistas[1].id} : ${pistas[0].id};
    })()`)
  );
  const trasRenombrar = await manifest(cliente, trasOrden.sync_version_actual);
  const renombrada = trasRenombrar.playlists.find((p) => p.id === playlistId);
  const favorita = trasRenombrar.pistas.find((p) => p.id === favoritaId);
  const meGusta = trasRenombrar.playlists.find((p) => p.es_favoritos);
  if (!renombrada || renombrada.nombre !== "QA IA renombrada") {
    throw new Error(`El manifest no recibió el nombre: ${JSON.stringify(renombrada)}`);
  }
  if (!favorita?.favorita || !meGusta?.pista_ids.includes(favoritaId)) {
    throw new Error(`El manifest no recibió Me gusta: ${JSON.stringify({ favorita, meGusta })}`);
  }

  await menuDe(".pistas > li .acciones .disparador", "Quitar de la playlist");
  await esperaHasta(`document.querySelectorAll(".pistas > li").length === 1`, Boolean, 8000);
  const trasQuitar = await manifest(cliente, trasRenombrar.sync_version_actual);
  const quitada = trasQuitar.playlists.find((p) => p.id === playlistId);
  if (!quitada || quitada.pista_ids.length !== 1) {
    throw new Error(`El manifest no recibió la pista quitada: ${JSON.stringify(quitada)}`);
  }

  await ir("/playlists", ".vista");
  await esperaHasta(
    `[...document.querySelectorAll(".rejilla .tarjeta .nombre")].some((n) => n.textContent.trim() === "QA IA renombrada")`,
    Boolean,
    10000
  );
  const mosaico = await inspector.evaluar(`(() => {
    const tarjeta = [...document.querySelectorAll(".rejilla .tarjeta")]
      .find((n) => n.querySelector(".nombre")?.textContent.trim() === "QA IA renombrada");
    return {
      imagenes: tarjeta.querySelectorAll(".mosaico img").length,
      cargadas: [...tarjeta.querySelectorAll(".mosaico img")]
        .filter((img) => img.complete && img.naturalWidth > 0).length
    };
  })()`);
  if (mosaico.imagenes === 0 || mosaico.cargadas !== mosaico.imagenes) {
    throw new Error(`El mosaico no está completo: ${JSON.stringify(mosaico)}`);
  }

  const categoria = await inspector.evaluar(`(async () => {
    const selector = [...document.querySelectorAll(".menu-selector")]
      .find((n) => n.querySelector(".rotulo")?.textContent.trim() === "Categoría");
    selector.querySelector(".gatillo").click();
    await new Promise((r) => setTimeout(r, 80));
    [...document.querySelectorAll(".capa-popover:popover-open .opcion")]
      .find((n) => n.textContent.trim() === "Creadas por mí").click();
    await new Promise((r) => setTimeout(r, 450));
    return [...document.querySelectorAll(".rejilla .tarjeta .nombre")].map((n) => n.textContent.trim());
  })()`);
  if (!categoria.includes("QA IA renombrada")) {
    throw new Error(`La categoría Creadas por mí no contiene la playlist: ${JSON.stringify(categoria)}`);
  }
  const ordenLista = await inspector.evaluar(`(async () => {
    const selector = [...document.querySelectorAll(".menu-selector")]
      .find((n) => n.querySelector(".rotulo")?.textContent.trim() === "Orden");
    selector.querySelector(".gatillo").click();
    await new Promise((r) => setTimeout(r, 80));
    [...document.querySelectorAll(".capa-popover:popover-open .opcion")]
      .find((n) => n.textContent.trim() === "A → Z").click();
    await new Promise((r) => setTimeout(r, 1200));
    return {
      seleccionado: selector.querySelector(".texto-seleccion").textContent.trim(),
      elementos: [...document.querySelectorAll(".rejilla .tarjeta")].map((tarjeta) => ({
        nombre: tarjeta.querySelector(".nombre").textContent.trim(),
        anclada: Boolean(tarjeta.querySelector(".ancla"))
      }))
    };
  })()`);
  if (ordenLista.seleccionado !== "A → Z") {
    throw new Error(`No se seleccionó el orden A → Z: ${JSON.stringify(ordenLista)}`);
  }
  const grupos = [true, false].map((anclada) =>
    ordenLista.elementos
      .filter((elemento) => elemento.anclada === anclada && elemento.nombre !== "Me gusta")
      .map((elemento) => elemento.nombre)
  );
  const listaOrdenada = grupos.every((grupo) =>
    grupo.every(
      (nombre, indice) => indice === 0 || grupo[indice - 1].localeCompare(nombre, "es") <= 0
    )
  );
  if (!listaOrdenada) throw new Error(`Las playlists no quedaron A → Z: ${JSON.stringify(ordenLista)}`);

  await ir(`/playlists/ver?id=${playlistId}`, ".detalle");
  await esperaHasta(`document.querySelector("h1")?.textContent.trim() === "QA IA renombrada"`);
  await menuDe(".acciones .disparador", "Borrar");
  await esperaHasta(`document.querySelector("dialog[open] .confirmar") !== null`);
  await inspector.evaluar(`(() => {
    document.querySelector("dialog[open] .confirmar").click();
    return true;
  })()`);
  await esperaHasta(`location.pathname === "/playlists"`, Boolean, 8000);
  const trasBorrar = await manifest(cliente, trasQuitar.sync_version_actual);
  const tumba = trasBorrar.tombstones.find(
    (t) => t.entidad === "playlist" && t.entidad_id === playlistId
  );
  if (!tumba) throw new Error(`El manifest no recibió la playlist borrada: ${JSON.stringify(trasBorrar.tombstones)}`);

  salida("playlists", {
    playlistId,
    pistas,
    ordenInicial: ordenFilas,
    ordenPersistido: playlistOrdenada.pista_ids,
    nombreRecibido: renombrada.nombre,
    favoritaRecibida: favorita.favorita,
    meGusta: meGusta.pista_ids,
    pistasTrasQuitar: quitada.pista_ids,
    mosaico,
    categoria: categoria.length,
    ordenListaAZ: listaOrdenada,
    tombstone: tumba
  });
}

async function escenarioReproduccion() {
  const pista = filas(`
    SELECT p.id, p.titulo, l.sincronizadas
    FROM pistas p JOIN letras l ON l.pista_id = p.id
    JOIN albumes a ON a.id = p.album_id
    WHERE p.estado = 'biblioteca' AND l.sincronizadas IS NOT NULL
      AND length(l.sincronizadas) > 100
      AND coalesce(p.portada_id, a.portada_id) IS NOT NULL
    ORDER BY p.id LIMIT 1;
  `)[0];
  if (!pista) throw new Error("No hay una pista con portada y letra sincronizada");
  const pistaId = Number(pista[0]);
  const tituloPista = pista[1];
  const letra = await invocar("letra_de_pista", { pistaId });
  const lineas = letra.sincronizada;
  if (lineas.length < 10) throw new Error("La pista elegida no tiene letras suficientes");
  const ambiente = await invocar("ambiente_de_pista", { pistaId });
  await invocar("reproductor_orden", {
    orden: { tipo: "reproducirPistas", ids: [pistaId], desde: 0 }
  });
  await esperaHasta(
    `(async () => (await window.__TAURI_INTERNALS__.invoke("reproductor_estado"))?.pistaId === ${pistaId})()`
  );
  await ir(`/reproduciendo?id=${pistaId}`, ".vista");
  await esperaHasta(`document.querySelector("h1")?.textContent.trim() === ${JSON.stringify(tituloPista)}`, Boolean, 12000);
  await esperaHasta(
    `Boolean(document.querySelector(".vista")?.style.getPropertyValue("--m3c-primary"))`,
    Boolean,
    8000
  );
  const color = await inspector.evaluar(`(() => {
    const vista = document.querySelector(".vista");
    return {
      inlinePrimary: vista.style.getPropertyValue("--m3c-primary").trim(),
      inlinePrimaryContainer: vista.style.getPropertyValue("--m3c-primary-container").trim(),
      computedPrimary: getComputedStyle(vista).getPropertyValue("--m3c-primary").trim(),
      rootPrimary: getComputedStyle(document.documentElement).getPropertyValue("--m3c-primary").trim()
    };
  })()`);
  if (!color.inlinePrimary || color.inlinePrimary === color.rootPrimary) {
    throw new Error(`La vista no tomó una paleta propia de la portada: ${JSON.stringify(color)}`);
  }

  await clicContiene(".conmutador-modo", "Ver letras");
  await esperaHasta(`document.querySelectorAll(".lista-letras .linea").length === ${lineas.length}`, Boolean, 8000);
  const tramo = lineas
    .slice(0, -1)
    .map((linea, i) => ({ i, ms: lineas[i + 1].ms - linea.ms }))
    .filter((x) => x.ms > 0 && x.ms <= 4000)
    .sort((a, b) => a.ms - b.ms)[0];
  if (!tramo) throw new Error("No hay dos líneas próximas para comprobar el avance");
  const indice = tramo.i;
  await inspector.evaluar(`(() => {
    document.querySelectorAll(".lista-letras .linea")[${indice}].click();
    return true;
  })()`);
  await esperaHasta(
    `document.querySelectorAll(".lista-letras .linea")[${indice}]?.classList.contains("activa")`,
    Boolean,
    5000
  );
  const estadoLinea = await invocar("reproductor_estado");
  const esperadoSeg = lineas[indice].ms / 1000;
  if (Math.abs(estadoLinea.posicionSeg - esperadoSeg) > 0.15) {
    throw new Error(
      `La línea lleva a ${estadoLinea.posicionSeg.toFixed(3)} s y debía ir a ${esperadoSeg.toFixed(3)} s`
    );
  }
  await esperaHasta(
    `document.querySelectorAll(".lista-letras .linea")[${indice + 1}]?.classList.contains("activa")`,
    Boolean,
    tramo.ms + 2500
  );
  const posterior = Math.min(indice + 2, lineas.length - 1);
  await invocar("reproductor_orden", {
    orden: { tipo: "buscar", segundos: lineas[posterior].ms / 1000 }
  });
  await esperaHasta(
    `document.querySelectorAll(".lista-letras .linea")[${posterior}]?.classList.contains("activa")`,
    Boolean,
    5000
  );

  const colaOriginal = [pistaId, 2, 3];
  await invocar("reproductor_orden", {
    orden: { tipo: "reproducirPistas", ids: colaOriginal, desde: 0 }
  });
  await tecla("q", { ctrlKey: true });
  await esperaHasta(`document.querySelector(".panel[aria-label]") !== null`, Boolean, 5000);
  const colaAntes = await invocar("reproductor_estado");
  await inspector.evaluar(`(() => {
    const fila = document.querySelector(".panel li.fila");
    const boton = fila.querySelector("button");
    boton.focus();
    fila.dispatchEvent(new KeyboardEvent("keydown", {
      key: "ArrowDown", altKey: true, bubbles: true, cancelable: true
    }));
    return true;
  })()`);
  await esperaHasta(
    `(async () => JSON.stringify((await window.__TAURI_INTERNALS__.invoke("reproductor_estado")).cola) === JSON.stringify([2, ${pistaId}, 3]))()`,
    Boolean,
    5000
  );
  const colaDespues = await invocar("reproductor_estado");
  salida("reproduccion", {
    pista: pistaId,
    titulo: tituloPista,
    ambiente,
    color,
    letra: { lineas: lineas.length, indice, posterior, posicionSeg: estadoLinea.posicionSeg },
    colaAntes: colaAntes.cola,
    colaDespues: colaDespues.cola
  });
}

const MPRIS = "org.mpris.MediaPlayer2.nbsound";
const MPRIS_RUTA = "/org/mpris/MediaPlayer2";
const MPRIS_JUGADOR = "org.mpris.MediaPlayer2.Player";

function busctl(...argumentos) {
  return execFileSync("busctl", ["--user", ...argumentos], { encoding: "utf8" }).trim();
}

function propiedadMpris(nombre) {
  return busctl("get-property", MPRIS, MPRIS_RUTA, MPRIS_JUGADOR, nombre);
}

function metodoMpris(nombre, firma = "", ...argumentos) {
  return busctl(
    "call",
    MPRIS,
    MPRIS_RUTA,
    MPRIS_JUGADOR,
    nombre,
    ...(firma ? [firma, ...argumentos] : [])
  );
}

async function escenarioMpris() {
  const pistas = filas(`
    SELECT p.id, p.titulo, p.artista_nombre, p.album_titulo, p.duracion_seg
    FROM pistas p
    WHERE p.estado = 'biblioteca' AND p.album_id IS NOT NULL
    ORDER BY p.id LIMIT 3;
  `).map(([id, titulo, artista, album, duracion]) => ({
    id: Number(id),
    titulo,
    artista,
    album,
    duracion: Number(duracion)
  }));
  if (pistas.length < 3) throw new Error("No hay tres pistas para MPRIS");
  await invocar("reproductor_orden", { orden: { tipo: "aleatorio", activo: false } });
  await invocar("reproductor_orden", { orden: { tipo: "repeticion", modo: "ninguno" } });
  await invocar("reproductor_orden", {
    orden: { tipo: "reproducirPistas", ids: pistas.map((p) => p.id), desde: 0 }
  });
  await esperar(250);
  const inicial = await invocar("reproductor_estado");
  await invocar("reproductor_orden", {
    orden: { tipo: "reproducirIndice", indice: 0 }
  });
  await esperar(500);
  const reparado = await invocar("reproductor_estado");
  if (reparado.pistaId !== pistas[0].id) {
    throw new Error(
      `No arrancó la pista ${pistas[0].id}: inicial=${JSON.stringify(inicial)} reparado=${JSON.stringify(reparado)}`
    );
  }
  metodoMpris("Pause");
  await esperar(150);
  metodoMpris("Play");
  await esperar(150);

  const metadataCruda = propiedadMpris("Metadata");
  const lectura = (patron) => metadataCruda.match(patron)?.[1] ?? null;
  const metadata = {
    titulo: lectura(/xesam:title" s "([^"]*)"/),
    artista: lectura(/xesam:artist" as 1 "([^"]*)"/),
    album: lectura(/xesam:album" s "([^"]*)"/),
    artUrl: lectura(/mpris:artUrl" s "([^"]*)"/),
    length: Number(lectura(/mpris:length" x ([0-9]+)/)),
    trackId: lectura(/mpris:trackid" o "\/org\/nbsound\/pista\/([0-9]+)"/)
  };
  if (
    metadata.titulo !== pistas[0].titulo ||
    metadata.artista !== pistas[0].artista ||
    metadata.album !== pistas[0].album
  ) {
    throw new Error(`Metadata MPRIS incorrecta: ${JSON.stringify(metadata)}`);
  }
  if (Math.abs(metadata.length - pistas[0].duracion * 1e6) > 2000) {
    throw new Error(`Duración MPRIS ${metadata.length} no coincide con la base`);
  }
  if (!metadata.artUrl?.startsWith("file://")) throw new Error("MPRIS no publica la portada");
  const rutaPortada = decodeURIComponent(metadata.artUrl.slice("file://".length));
  if (!existsSync(rutaPortada)) throw new Error(`La portada MPRIS no existe: ${rutaPortada}`);

  metodoMpris("SetPosition", "ox", `/org/nbsound/pista/${pistas[0].id}`, "42000000");
  await esperar(150);
  const posicion = Number(propiedadMpris("Position").split(" ").at(-1));
  if (Math.abs(posicion - 42_000_000) > 200_000) {
    throw new Error(`SetPosition quedó en ${posicion} µs`);
  }

  metodoMpris("PlayPause");
  await esperaHasta(`(async () => (await window.__TAURI_INTERNALS__.invoke("reproductor_estado"))?.estado === "pausado")()`);
  const posicionAntesSeek = Number(propiedadMpris("Position").split(" ").at(-1));
  metodoMpris("Seek", "x", "3000000");
  await esperar(150);
  const posicionDespuesSeek = Number(propiedadMpris("Position").split(" ").at(-1));
  const avanceSeekSeg = (posicionDespuesSeek - posicionAntesSeek) / 1e6;
  if (Math.abs(avanceSeekSeg - 3) > 0.5) {
    throw new Error(`Seek avanzó ${avanceSeekSeg.toFixed(3)} s en vez de 3 s`);
  }
  metodoMpris("PlayPause");
  await esperaHasta(`(async () => (await window.__TAURI_INTERNALS__.invoke("reproductor_estado"))?.estado === "reproduciendo")()`);

  const antesSiguiente = await invocar("reproductor_estado");
  metodoMpris("Next");
  await esperaHasta(`(async () => (await window.__TAURI_INTERNALS__.invoke("reproductor_estado"))?.pistaId === ${pistas[1].id})()`);
  await esperar(600);
  const despuesSiguiente = await invocar("reproductor_estado");
  if (despuesSiguiente.pistaId !== pistas[1].id) {
    throw new Error(
      `Next se saltó una pista: ${JSON.stringify({ antesSiguiente, despuesSiguiente })}`
    );
  }
  metodoMpris("Previous");
  await esperaHasta(
    `(async () => (await window.__TAURI_INTERNALS__.invoke("reproductor_estado"))?.pistaId === ${pistas[0].id})()`,
    Boolean,
    5000
  ).catch((error) => {
    throw new Error(
      `${error.message}; antes=${JSON.stringify(antesSiguiente)} siguiente=${JSON.stringify(despuesSiguiente)}`
    );
  });

  await tecla("s");
  await esperaHasta(
    `(async () => (await window.__TAURI_INTERNALS__.invoke("reproductor_estado"))?.aleatorio === true)()`
  );
  await esperar(120);
  const shuffleMpris = propiedadMpris("Shuffle");
  if (!shuffleMpris.includes("true")) throw new Error(`MPRIS no refleja aleatorio: ${shuffleMpris}`);
  busctl(
    "set-property",
    MPRIS,
    MPRIS_RUTA,
    MPRIS_JUGADOR,
    "Shuffle",
    "b",
    "false"
  );
  await esperaHasta(
    `(async () => (await window.__TAURI_INTERNALS__.invoke("reproductor_estado"))?.aleatorio === false)()`
  );

  await tecla("r");
  await esperaHasta(
    `(async () => (await window.__TAURI_INTERNALS__.invoke("reproductor_estado"))?.repeticion === "todo")()`
  );
  await esperar(100);
  const loopMpris = propiedadMpris("LoopStatus");
  if (!loopMpris.includes("Playlist")) throw new Error(`MPRIS no refleja repetición: ${loopMpris}`);
  busctl(
    "set-property",
    MPRIS,
    MPRIS_RUTA,
    MPRIS_JUGADOR,
    "LoopStatus",
    "s",
    "Track"
  );
  await esperaHasta(
    `(async () => (await window.__TAURI_INTERNALS__.invoke("reproductor_estado"))?.repeticion === "uno")()`
  );
  const estado = await invocar("reproductor_estado");
  salida("mpris", {
    metadata,
    posicionMicros: posicion,
    seekSeg: avanceSeekSeg,
    playPause: estado.estado,
    nextPrevious: [pistas[1].id, pistas[0].id],
    shuffleMpris,
    aleatorioFinal: estado.aleatorio,
    loopMpris,
    repeticionFinal: estado.repeticion
  });
}

async function escenarioSonoridad() {
  const ids = filas(`
    SELECT id FROM pistas
    WHERE estado = 'biblioteca' AND ruta LIKE 'qa/flac/%'
    ORDER BY id;
  `).map(([id]) => Number(id));
  if (ids.length < 2) throw new Error("No están las pistas FLAC sintéticas");
  const pendientesAntes = Number(
    sql(`
      SELECT count(*) FROM pistas p LEFT JOIN sonoridad s ON s.pista_id = p.id
      WHERE p.estado = 'biblioteca' AND s.pista_id IS NULL;
    `)
  );
  await invocar("reproductor_orden", {
    orden: { tipo: "reproducirPistas", ids, desde: 0 }
  });
  await asegurarFlujoNulo();
  await esperaHasta(
    `(async () => {
      const estado = await window.__TAURI_INTERNALS__.invoke("reproductor_estado");
      return estado?.estado === "reproduciendo" &&
        estado.pistaId === ${ids[0]} &&
        JSON.stringify(estado.cola) === JSON.stringify(${JSON.stringify(ids)});
    })()`
  );
  const tid = hilo("sonoridad");
  if (!tid) throw new Error("No se encontró el hilo sonoridad");
  const ruta = `${process.env.NB_QA_INFORMES}/sonoridad-continua.wav`;
  const grabacion = await iniciarGrabacion(ruta);
  const inicioTicks = ticksHilo(tid);
  const inicio = process.hrtime.bigint();
  await esperar(4000);
  const finTicks = ticksHilo(tid);
  const fin = process.hrtime.bigint();
  await grabacion.detener();
  const transcurrido = Number(fin - inicio) / 1e9;
  const ticksPorSegundo = Number(execFileSync("getconf", ["CLK_TCK"], { encoding: "utf8" }).trim());
  const cpuPorcentaje = ((finTicks - inicioTicks) / ticksPorSegundo / transcurrido) * 100;
  const salidaAnalizador = ejecutarAnalizador("una_reproduccion_continua_no_tiene_huecos", {
    NB_QA_WAV: ruta
  });
  const pendientesDespues = Number(
    sql(`
      SELECT count(*) FROM pistas p LEFT JOIN sonoridad s ON s.pista_id = p.id
      WHERE p.estado = 'biblioteca' AND s.pista_id IS NULL;
    `)
  );
  if (cpuPorcentaje >= 100) {
    throw new Error(`El hilo sonoridad usó ${cpuPorcentaje.toFixed(2)} % de un núcleo`);
  }
  if (pendientesDespues >= pendientesAntes) {
    throw new Error(
      `El hilo sonoridad no avanzó: ${pendientesAntes} -> ${pendientesDespues}`
    );
  }
  salida("sonoridad", {
    hilo: tid,
    ventanaSeg: transcurrido,
    cpuPorcentaje,
    pendientesAntes,
    pendientesDespues,
    analizador: salidaAnalizador
      .split("\n")
      .filter((linea) => linea.includes("INFORME_QA"))
      .join("\n")
  });
}

async function escenarioNormalizacionSiguiente() {
  const ids = filas(`
    SELECT id, ruta FROM pistas
    WHERE ruta IN ('qa/senales/alta.flac', 'qa/senales/baja.flac')
    ORDER BY CASE ruta WHEN 'qa/senales/alta.flac' THEN 0 ELSE 1 END;
  `).map(([id]) => Number(id));
  if (ids.length !== 2) throw new Error("Faltan las pistas alta y baja");
  const [alta, baja] = ids;
  await invocar("reproductor_orden", {
    orden: { tipo: "reproducirPistas", ids: [alta, baja], desde: 0 }
  });
  await invocar("reproductor_orden", { orden: { tipo: "normalizar", activo: false } });
  await invocar("reproductor_orden", { orden: { tipo: "volumen", valor: 1 } });
  await asegurarFlujoNulo();
  await esperaHasta(
    `(async () => (await window.__TAURI_INTERNALS__.invoke("reproductor_estado"))?.pistaId === ${alta})()`
  );
  await invocar("reproductor_orden", { orden: { tipo: "buscar", segundos: 0.5 } });
  const antes = `${process.env.NB_QA_INFORMES}/normalizacion-antes.wav`;
  let grabacion = await iniciarGrabacion(antes);
  await esperar(1600);
  await grabacion.detener();

  await ir("/ajustes", ".ajustes");
  await clicTexto(".pestana-seccion", "Reproducción");
  await esperaHasta(`document.querySelector("#reproduccion input[role='switch']") !== null`);
  await inspector.evaluar(`(() => {
    const interruptor = document.querySelector("#reproduccion input[role='switch']");
    interruptor.click();
    return true;
  })()`);
  await esperaHasta(
    `(async () => (await window.__TAURI_INTERNALS__.invoke("reproductor_estado"))?.normalizar === true)()`
  );
  const estadoActual = await invocar("reproductor_estado");
  if (estadoActual.pistaId !== alta) {
    throw new Error("La pista actual cambió antes de comprobar la normalización");
  }
  const despues = `${process.env.NB_QA_INFORMES}/normalizacion-despues.wav`;
  grabacion = await iniciarGrabacion(despues);
  await esperar(1600);
  await grabacion.detener();

  await invocar("reproductor_orden", { orden: { tipo: "buscar", segundos: 7.2 } });
  await esperaHasta(
    `(async () => (await window.__TAURI_INTERNALS__.invoke("reproductor_estado"))?.pistaId === ${baja})()`,
    Boolean,
    8000
  );
  const siguiente = `${process.env.NB_QA_INFORMES}/normalizacion-siguiente.wav`;
  grabacion = await iniciarGrabacion(siguiente);
  await esperar(2200);
  await grabacion.detener();
  const salidaAnalizador = ejecutarAnalizador(
    "la_normalizacion_entra_desde_la_siguiente_pista",
    {
      NB_QA_ANTES_WAV: antes,
      NB_QA_DESPUES_WAV: despues,
      NB_QA_SIGUIENTE_WAV: siguiente
    }
  );
  salida("normalizacion_siguiente", {
    alta,
    baja,
    analizador: salidaAnalizador
      .split("\n")
      .filter((linea) => linea.includes("INFORME_QA"))
      .join("\n")
  });
}

async function estadoReproductor() {
  return invocar("reproductor_estado");
}

async function escenarioAtajos() {
  const audibles = filas(`
    SELECT p.id FROM pistas p JOIN stems s ON s.pista_id = p.id
    WHERE p.estado = 'biblioteca' AND s.estado = 'lista'
    ORDER BY p.id LIMIT 3;
  `).map(([id]) => Number(id));
  if (audibles.length < 3) throw new Error("No hay tres pistas con instrumental");
  await invocar("reproductor_orden", { orden: { tipo: "aleatorio", activo: false } });
  await invocar("reproductor_orden", { orden: { tipo: "repeticion", modo: "ninguno" } });
  await invocar("reproductor_orden", {
    orden: { tipo: "reproducirPistas", ids: audibles, desde: 0 }
  });
  await invocar("reproductor_orden", { orden: { tipo: "volumen", valor: 0.8 } });
  await asegurarFlujoNulo();
  await esperaHasta(
    `(async () => {
      const estado = await window.__TAURI_INTERNALS__.invoke("reproductor_estado");
      return estado?.estado === "reproduciendo" &&
        estado.pistaId === ${audibles[0]} &&
        JSON.stringify(estado.cola) === JSON.stringify(${JSON.stringify(audibles)});
    })()`
  );
  await inspector.evaluar(`document.activeElement?.blur?.()`);

  const inicial = await estadoReproductor();
  await tecla(" ");
  await esperaHasta(
    `(async () => (await window.__TAURI_INTERNALS__.invoke("reproductor_estado"))?.estado === "pausado")()`
  );
  await tecla(" ");
  await esperaHasta(
    `(async () => (await window.__TAURI_INTERNALS__.invoke("reproductor_estado"))?.estado === "reproduciendo")()`
  );

  const posicionAntes = (await estadoReproductor()).posicionSeg;
  await tecla("ArrowRight");
  await esperar(250);
  const posicionDerecha = (await estadoReproductor()).posicionSeg;
  await tecla("ArrowLeft");
  await esperar(250);
  const posicionIzquierda = (await estadoReproductor()).posicionSeg;
  if (posicionDerecha - posicionAntes < 8) throw new Error("Flecha derecha no avanzó");
  if (posicionIzquierda >= posicionDerecha) throw new Error("Flecha izquierda no retrocedió");

  await tecla("ArrowDown");
  await esperaHasta(
    `(async () => (await window.__TAURI_INTERNALS__.invoke("reproductor_estado"))?.pistaId === ${audibles[1]})()`
  );
  await esperar(500);
  const trasSiguiente = await estadoReproductor();
  if (trasSiguiente.pistaId !== audibles[1]) {
    throw new Error(`La flecha abajo se saltó una pista: ${JSON.stringify(trasSiguiente)}`);
  }
  await tecla("ArrowUp");
  await esperaHasta(
    `(async () => (await window.__TAURI_INTERNALS__.invoke("reproductor_estado"))?.pistaId === ${audibles[0]})()`
  );

  await tecla("s");
  await esperaHasta(
    `(async () => (await window.__TAURI_INTERNALS__.invoke("reproductor_estado"))?.aleatorio === true)()`
  );
  await tecla("r");
  await esperaHasta(
    `(async () => (await window.__TAURI_INTERNALS__.invoke("reproductor_estado"))?.repeticion === "todo")()`
  );

  const volumenAntes = (await estadoReproductor()).volumen;
  await tecla("+");
  await esperaHasta(
    `(async () => (await window.__TAURI_INTERNALS__.invoke("reproductor_estado"))?.volumen > ${volumenAntes} + 0.049)()`
  );
  await tecla("-");
  await esperaHasta(
    `(async () => Math.abs((await window.__TAURI_INTERNALS__.invoke("reproductor_estado"))?.volumen - ${volumenAntes}) < 0.0001)()`
  );

  await tecla("l");
  await esperaHasta(`location.pathname === "/reproduciendo" && location.search.includes("letras")`);
  await tecla("f");
  await esperaHasta(`location.pathname === "/reproduciendo" && !location.search.includes("letras")`);
  const antesKaraoke = await estadoReproductor();
  await tecla("k");
  await esperaHasta(
    `(async () => (await window.__TAURI_INTERNALS__.invoke("reproductor_estado"))?.karaokeActivo !== ${antesKaraoke.karaokeActivo})()`
  );

  const ventanasAntes = contarVentanas();
  await tecla("m", { ctrlKey: true });
  await esperaHasta(
    `true`,
    () => {
      const cantidad = contarVentanas();
      return cantidad > ventanasAntes;
    },
    6000
  );
  await invocar("dejar_minirreproductor", { volver: true });

  await ir("/ajustes", ".ajustes");
  await esperaHasta(`document.querySelector('.superior input[type="search"]') !== null`);
  const antesCampo = await estadoReproductor();
  const enfocado = await inspector.evaluar(`(() => {
    const campo = document.querySelector('.superior input[type="search"]');
    campo.focus();
    return document.activeElement === campo;
  })()`);
  if (!enfocado) throw new Error("No se pudo enfocar el campo de búsqueda");
  await tecla(" ", {}, '.superior input[type="search"]');
  await esperar(200);
  const despuesCampo = await estadoReproductor();
  if (despuesCampo.estado !== antesCampo.estado) {
    throw new Error("Un atajo actuó con el foco dentro del campo de búsqueda");
  }
  await inspector.evaluar(`document.activeElement?.blur?.()`);

  await tecla("q", { ctrlKey: true });
  await esperaHasta(`document.querySelector(".panel[aria-label]") !== null`, Boolean, 5000);
  const final = await estadoReproductor();
  salida("atajos", {
    pistaInicial: inicial.pistaId,
    pausaReanudacion: [inicial.estado, final.estado],
    posiciones: [posicionAntes, posicionDerecha, posicionIzquierda],
    siguienteAnterior: [audibles[1], audibles[0]],
    aleatorio: final.aleatorio,
    repeticion: final.repeticion,
    volumen: final.volumen,
    karaoke: [antesKaraoke.karaokeActivo, final.karaokeActivo],
    ventanasMini: [ventanasAntes, ventanasAntes + 1],
    focoEnCampoNoActuo: true,
    colaAbierta: true
  });
}

async function escenarioPerfil() {
  await ir("/tu-musica", ".perfil");
  await esperaHasta(`document.querySelector(".identidad h1") !== null`, Boolean, 12000);
  await esperaHasta(`document.querySelector(".dos .tarjeta") !== null`, Boolean, 12000);
  await esperaHasta(
    `document.querySelector(".dos .tarjeta")?.textContent.trim().length > 0`,
    Boolean,
    12000
  );
  const perfil = await invocar("perfil");
  const directo = filas(`
    SELECT
      (SELECT count(*) FROM historial),
      (SELECT count(DISTINCT pista_id) FROM historial),
      (SELECT count(DISTINCT p.artista_id) FROM historial h JOIN pistas p ON p.id=h.pista_id),
      (SELECT count(DISTINCT p.album_id) FROM historial h JOIN pistas p ON p.id=h.pista_id),
      (SELECT total(coalesce(h.escuchado_seg,p.duracion_seg,0)) FROM historial h LEFT JOIN pistas p ON p.id=h.pista_id),
      (SELECT strftime('%H', reproducida_en, 'localtime') FROM historial
        GROUP BY 1 ORDER BY count(*) DESC, 1 LIMIT 1),
      (SELECT count(*) FROM historial WHERE strftime('%Y-%m', reproducida_en, 'localtime') =
        strftime('%Y-%m', 'now', 'localtime')),
      (SELECT id FROM pistas WHERE estado='biblioteca' AND reproducciones > 0
        ORDER BY reproducciones DESC, titulo COLLATE NOCASE, id LIMIT 1);
  `)[0].map(Number);
  const diasActivos = Number(
    sql(`
      SELECT count(*) FROM (
        SELECT CAST(strftime('%d', reproducida_en, 'localtime') AS INTEGER) AS dia,
               count(*) AS n
        FROM historial
        WHERE strftime('%Y-%m', reproducida_en, 'localtime') =
              strftime('%Y-%m', 'now', 'localtime')
        GROUP BY dia
      );
    `)
  );
  const hora = directo[5];
  const horaEsperada = new Date(2000, 0, 1, hora).toLocaleTimeString("es", {
    hour: "numeric",
    minute: "2-digit"
  });
  const dom = await inspector.evaluar(`(() => ({
    nombre: document.querySelector(".identidad h1")?.textContent.trim(),
    resumen: document.querySelector(".identidad p")?.textContent.trim(),
    fichas: [...document.querySelectorAll(".identidad .fichas .ficha")].map((n) => n.textContent.trim()),
    actividad: [...document.querySelectorAll(".cifras strong")].map((n) => n.textContent.trim()),
    animo: [...document.querySelectorAll(".dos .tarjeta")][0]?.textContent.trim(),
    dias: document.querySelectorAll(".calendario .dia").length,
    topCanciones: [...document.querySelectorAll(".top .fila .texto strong, .top .fila strong")]
      .slice(0, 5).map((n) => n.textContent.trim()),
    tituloTop: document.querySelector(".titulo-top")?.textContent.trim()
  }))()`);
  if (perfil.reproducciones !== directo[0] || perfil.pistasDistintas !== directo[1]) {
    throw new Error(`Perfil del puente no coincide con SQLite: ${JSON.stringify({ perfil, directo })}`);
  }
  if (!dom.fichas.some((ficha) => ficha.includes(horaEsperada))) {
    throw new Error(`La hora pico no está en hora local: ${JSON.stringify(dom.fichas)}`);
  }
  if (!dom.fichas.some((ficha) => /\d+ días activos/.test(ficha)) || diasActivos === 0) {
    throw new Error(`Días activos incoherentes: ${JSON.stringify({ dom, diasActivos })}`);
  }
  if (!dom.animo?.toLowerCase().includes("mood del día")) {
    throw new Error(`No aparece el ánimo del día: ${JSON.stringify(dom.animo)}`);
  }
  if (dom.topCanciones.length === 0 || !dom.tituloTop?.includes("canciones")) {
    throw new Error("No aparecen los tops de canciones");
  }
  const pistaTop = filas(`SELECT titulo FROM pistas WHERE id = ${directo[7]};`)[0]?.[0];
  if (pistaTop && !dom.topCanciones.includes(pistaTop)) {
    throw new Error(`El top no coincide con SQLite: ${JSON.stringify(dom.topCanciones)}`);
  }
  salida("perfil", {
    directo: {
      reproducciones: directo[0],
      pistasDistintas: directo[1],
      artistasDistintos: directo[2],
      albumesDistintos: directo[3],
      segundos: directo[4],
      horaPico: hora,
      horaLocal: horaEsperada,
      escuchasDelMes: directo[6],
      diasActivos,
      pistaTop
    },
    dom
  });
}

async function main() {
  if (!process.env.NB_QA_DB) throw new Error("falta NB_QA_DB");
  switch (ESCENARIO) {
    case "inicio":
      await escenarioInicio();
      break;
    case "temas":
      await escenarioTemas();
      break;
    case "preparar-arranque":
      await escenarioPrepararArranque();
      break;
    case "verificar-arranque":
      await escenarioVerificarArranque();
      break;
    case "biblioteca":
      await escenarioBiblioteca();
      break;
    case "playlists":
      await escenarioPlaylists();
      break;
    case "reproduccion":
      await escenarioReproduccion();
      break;
    case "mpris":
      await escenarioMpris();
      break;
    case "sonoridad":
      await escenarioSonoridad();
      break;
    case "normalizacion":
      await escenarioNormalizacionSiguiente();
      break;
    case "atajos":
      await escenarioAtajos();
      break;
    case "perfil":
      await escenarioPerfil();
      break;
    default:
      throw new Error(`escenario desconocido: ${ESCENARIO}`);
  }
}

try {
  await main();
} finally {
  inspector.cerrar();
}
