#!/usr/bin/env node

import { execFileSync } from 'node:child_process';
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  renameSync,
  rmSync,
  statSync,
  unlinkSync,
  writeFileSync
} from 'node:fs';
import { request as httpsRequest, Agent as HttpsAgent } from 'node:https';

import { Inspector, esperar } from './inspector.mjs';

const inspector = await Inspector.conectar();
const DB = process.env.NB_QA_DB;
const CERT_PATH = process.env.NB_QA_CERT_PATH ?? '';
const agente = new HttpsAgent({ keepAlive: true, maxSockets: 1 });
let baseMovil = '';
let tokenMovil = '';
const ARCHIVOS_LOTE = 120;

async function seleccionarCarpeta(carpeta) {
  mkdirSync(carpeta, { recursive: true });
  for (let i = 0; i < 120; i += 1) {
    if (await inspector.evaluar(`Boolean(document.querySelector(".carcasa"))`)) break;
    await esperar(100);
  }
  await esperar(500);
  return invocar('qa_importar_carpeta', { ruta: carpeta });
}

async function invocar(comando, argumentos = {}) {
  return inspector.evaluar(
    `window.__TAURI_INTERNALS__.invoke(${JSON.stringify(comando)}, ${JSON.stringify(argumentos)})`
  );
}

function sql(consulta) {
  return execFileSync('sqlite3', ['-readonly', '-separator', '\t', DB, consulta], {
    encoding: 'utf8'
  }).trim();
}

function sqlEscritura(consulta) {
  return execFileSync('sqlite3', [DB, consulta], { encoding: 'utf8' }).trim();
}

function filas(consulta) {
  const texto = sql(consulta);
  return texto ? texto.split('\n').map((linea) => linea.split('\t')) : [];
}

function peticionesRed() {
  const archivos = readdirSync(process.env.NB_QA_REGISTROS)
    .filter((n) => n.startsWith('nb-sound.log.'))
    .sort();
  const texto = archivos
    .map((n) => readFileSync(`${process.env.NB_QA_REGISTROS}/${n}`, 'utf8'))
    .join('\n');
  const servicios = {};
  for (const linea of texto.split('\n')) {
    if (!linea.includes('petición de red autorizada')) continue;
    const servicio = linea.match(/servicio=([A-Za-z]+)/)?.[1] ?? 'desconocido';
    servicios[servicio] = (servicios[servicio] ?? 0) + 1;
  }
  return servicios;
}

async function esperarImportacion(limite = 120000) {
  const hasta = Date.now() + limite;
  let ultimo = null;
  while (Date.now() < hasta) {
    ultimo = await invocar('importacion_progreso');
    if (!ultimo.activa && ultimo.hechos > 0) return ultimo;
    await esperar(100);
  }
  throw new Error(`La importación no terminó: ${JSON.stringify(ultimo)}`);
}

async function tarjetaImportacion(limite = 10000) {
  return esperarHasta(
    `[...document.querySelectorAll("[role=status]")].map((n) => ({
      texto: n.textContent.trim(),
      progreso: n.querySelector("progress")
        ? {
            max: Number(n.querySelector("progress").max),
            valor: Number(n.querySelector("progress").value)
          }
        : null
    }))`,
    (tarjetas) =>
      Array.isArray(tarjetas) &&
      tarjetas.some((t) => t.texto.includes('Catalogando') || /^\d+ añadidas?/.test(t.texto)),
    limite
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
  throw new Error(`No se cumplió: ${expresion}. Último: ${JSON.stringify(ultimo)}`);
}

async function ir(ruta, selector) {
  await inspector.evaluarDirecto(
    `(() => { location.href = ${JSON.stringify(`tauri://localhost${ruta}`)}; return true; })()`
  );
  await esperarHasta(
    `document.readyState === "complete" && Boolean(document.querySelector(${JSON.stringify(selector)}))`,
    Boolean,
    15000
  );
  await esperar(150);
}

function politica(general, servicios) {
  return invocar('cambiar_politica_red', { politica: { general, servicios } });
}

function idsAntes() {
  return Number(sql('SELECT coalesce(max(id), 0) FROM pistas;'));
}

function nuevasDesde(id) {
  return filas(
    `SELECT id, titulo, artista_nombre, album_titulo, verificada, fuentes_etiquetado, ruta
     FROM pistas WHERE id > ${id} ORDER BY id;`
  );
}

async function esperarNuevas(antes, cantidad, limite = 30000) {
  const hasta = Date.now() + limite;
  let nuevas = [];
  while (Date.now() < hasta) {
    nuevas = nuevasDesde(antes);
    if (nuevas.length >= cantidad) return nuevas;
    await esperar(100);
  }
  throw new Error(`No aparecieron ${cantidad} pistas nuevas; llegaron ${nuevas.length}`);
}

function ultimaImportacion() {
  return Number(sql('SELECT coalesce(max(id), 0) FROM importaciones;'));
}

async function esperarImportacionTerminada(despuesDe, limite = 30000) {
  const hasta = Date.now() + limite;
  let fila = [];
  while (Date.now() < hasta) {
    [fila = []] = filas(`
      SELECT id, estado, descubiertos, aceptados, por_revisar, errores
        FROM importaciones WHERE id = (SELECT max(id) FROM importaciones);
    `);
    if (Number(fila[0]) > despuesDe && fila[1] !== 'en_curso') return fila;
    await esperar(100);
  }
  throw new Error(`La importación posterior a ${despuesDe} no terminó: ${JSON.stringify(fila)}`);
}

function medicionesConexiones(pid, duracionMs) {
  return new Promise((resolve) => {
    // Un socket que ya estaba abierto al empezar es de la conexión reutilizable de
    // una petición anterior, no una salida nueva: solo cuentan los que aparecen.
    const externas = [];
    let previas = null;
    const inicio = Date.now();
    const paso = () => {
      const vistas = [];
      let texto = '';
      try {
        texto = execFileSync('ss', ['-Htnp', 'state', 'established'], {
          encoding: 'utf8'
        });
      } catch {
        texto = '';
      }
      for (const linea of texto.split('\n')) {
        if (!linea.includes(`pid=${pid}`)) continue;
        const extremo = linea
          .replace(/\s+users:.*$/, '')
          .trim()
          .split(/\s+/)
          .at(-1);
        const limpio = extremo?.replace(/^\[|\]$/g, '') ?? '';
        const host = limpio.slice(0, limpio.lastIndexOf(':'));
        const local =
          host === '127.0.0.1' ||
          host === '::1' ||
          /^10\./.test(host) ||
          /^192\.168\./.test(host) ||
          /^172\.(?:1[6-9]|2\d|3[01])\./.test(host);
        if (host && !local)
          vistas.push(
            // Local y remoto, sin las colas: Recv-Q y Send-Q cambian en el mismo socket.
            linea
              .replace(/\s+users:.*$/, '')
              .trim()
              .split(/\s+/)
              .slice(-2)
              .join(' ')
          );
      }
      if (previas === null) previas = new Set(vistas);
      else for (const v of vistas) if (!previas.has(v)) externas.push(v.split(/\s+/).at(-1));
      if (Date.now() - inicio < duracionMs) setTimeout(paso, 30);
      else resolve([...new Set(externas)]);
    };
    paso();
  });
}

function peticionMovil({ ruta, metodo = 'GET', cuerpo, autenticar = true }) {
  return new Promise((resolve, reject) => {
    const datos = cuerpo === undefined ? null : JSON.stringify(cuerpo);
    const url = new URL(ruta, baseMovil);
    const solicitud = httpsRequest(
      {
        hostname: url.hostname,
        port: url.port,
        path: url.pathname + url.search,
        method: metodo,
        agent: agente,
        ca: readFileSync(CERT_PATH, 'utf8'),
        rejectUnauthorized: true,
        servername: 'nbsound.local',
        checkServerIdentity: (_host, certificado) => {
          const esperada = execFileSync(
            'openssl',
            ['x509', '-in', CERT_PATH, '-noout', '-fingerprint', '-sha256'],
            { encoding: 'utf8' }
          )
            .split('=')
            .at(-1)
            .replaceAll(':', '')
            .trim()
            .toUpperCase();
          const real = certificado.fingerprint256.replaceAll(':', '').toUpperCase();
          return real === esperada ? undefined : new Error('huella TLS distinta');
        },
        headers: {
          ...(autenticar && tokenMovil ? { Authorization: `Bearer ${tokenMovil}` } : {}),
          ...(datos
            ? {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(datos)
              }
            : {})
        }
      },
      (respuesta) => {
        const partes = [];
        respuesta.on('data', (p) => partes.push(p));
        respuesta.on('end', () => {
          const bytes = Buffer.concat(partes);
          let json = null;
          try {
            json = JSON.parse(bytes.toString('utf8'));
          } catch {}
          resolve({ estado: respuesta.statusCode, cabeceras: respuesta.headers, bytes, json });
        });
      }
    );
    solicitud.on('error', reject);
    if (datos) solicitud.write(datos);
    solicitud.end();
  });
}

async function abrirMovil() {
  const emparejar = await invocar('movil_emparejar');
  const estado = await invocar('movil_estado');
  baseMovil = `https://${estado.direccion}`;
  const pareja = await peticionMovil({
    ruta: '/api/v1/pair',
    metodo: 'POST',
    autenticar: false,
    cuerpo: {
      codigo: emparejar.codigo,
      nombre_dispositivo: 'QA Fase 4',
      plataforma: 'android'
    }
  });
  if (pareja.estado !== 200) throw new Error(`pair respondió ${pareja.estado}`);
  tokenMovil = pareja.json.device_token;
}

async function manifestMovil(since = 0) {
  const respuesta = await peticionMovil({ ruta: `/api/v1/manifest?since=${since}&limit=10000` });
  if (respuesta.estado !== 200) throw new Error(`manifest respondió ${respuesta.estado}`);
  return respuesta.json;
}

async function escenarioRed() {
  const carpeta = `${process.env.NB_QA_FASE4_FUENTES}/red-real`;
  const pendientesAntes = Number(
    sql('SELECT count(*) FROM por_revisar WHERE resuelto_en IS NULL;')
  );
  const pistasAntes = idsAntes();
  const seleccionados = await seleccionarCarpeta(carpeta);
  if (seleccionados !== 1) throw new Error(`El puente seleccionó ${seleccionados} rutas`);
  const hasta = Date.now() + 60000;
  let progreso = null;
  while (Date.now() < hasta) {
    progreso = await invocar('importacion_progreso');
    const pendientes = Number(sql('SELECT count(*) FROM por_revisar WHERE resuelto_en IS NULL;'));
    const pistas = idsAntes();
    if (!progreso.activa && (pendientes > pendientesAntes || pistas > pistasAntes)) {
      break;
    }
    await esperar(100);
  }
  const pistas = filas(
    'SELECT id, titulo, artista_nombre, album_titulo, fuentes_etiquetado, verificada FROM pistas ORDER BY id DESC LIMIT 5;'
  );
  const pendientes = filas(
    'SELECT causa, metadatos FROM por_revisar WHERE resuelto_en IS NULL ORDER BY id DESC LIMIT 5;'
  );
  const servicios = peticionesRed();
  console.log(
    'QA_CATALOGO_RED',
    JSON.stringify({
      progreso,
      pistas,
      pendientes,
      peticionesRed: servicios,
      totalPeticiones: Object.values(servicios).reduce((a, b) => a + b, 0)
    })
  );
}

async function escenarioSinRed() {
  await politica(false, []);
  const politicaActual = await invocar('politica_red');
  if (politicaActual.general || politicaActual.servicios.length !== 0) {
    throw new Error(`La política no quedó apagada: ${JSON.stringify(politicaActual)}`);
  }
  await esperar(5000);
  const autorizacionesAntes = peticionesRed();
  const antes = idsAntes();
  const muestreo = medicionesConexiones(Number(process.env.NB_QA_APP_PID), 8000);
  const seleccionados = await seleccionarCarpeta(`${process.env.NB_QA_FASE4_FUENTES}/sin-red`);
  if (seleccionados !== 1) throw new Error('No se seleccionó la carpeta sin red');
  let nuevas = [];
  try {
    nuevas = await esperarNuevas(antes, 1, 10000);
  } catch {
    nuevas = filas(
      `SELECT id, titulo, artista_nombre, album_titulo, verificada, fuentes_etiquetado, ruta
       FROM pistas WHERE titulo='QA Sin Red';`
    );
  }
  const externas = await muestreo;
  const autorizacionesDespues = peticionesRed();
  if (externas.length > 0) throw new Error(`Salieron conexiones externas: ${externas}`);
  if (JSON.stringify(autorizacionesAntes) !== JSON.stringify(autorizacionesDespues)) {
    throw new Error(
      `La red apagada autorizó peticiones: ${JSON.stringify({
        autorizacionesAntes,
        autorizacionesDespues
      })}`
    );
  }
  if (nuevas.length !== 1 || nuevas[0][4] !== '0') {
    throw new Error(`La importación sin red no quedó sin verificar: ${JSON.stringify(nuevas)}`);
  }
  console.log(
    'QA_CATALOGO_SIN_RED',
    JSON.stringify({
      nuevas,
      externas,
      autorizacionesAntes,
      autorizacionesDespues
    })
  );
}

async function escenarioImportarLote() {
  await politica(false, []);
  await ir('/', '.carcasa');
  const seleccionados = await seleccionarCarpeta(`${process.env.NB_QA_FASE4_FUENTES}/lote`);
  if (seleccionados !== ARCHIVOS_LOTE) {
    throw new Error(`El lote trajo ${seleccionados} archivos`);
  }
  const progreso = await esperarHasta(
    `window.__TAURI_INTERNALS__.invoke("importacion_progreso")`,
    (p) => p?.activa && p.hechos > 0 && p.hechos < p.total,
    30000
  );
  const tarjetas = await tarjetaImportacion();
  console.log('QA_CATALOGO_LOTE_INICIADO', JSON.stringify({ progreso, tarjetas }));
}

async function escenarioVerificarLote() {
  const hasta = Date.now() + 180000;
  let progreso = null;
  let qa = [];
  let pendientesLote = [];
  while (Date.now() < hasta) {
    progreso = await invocar('importacion_progreso');
    qa = filas("SELECT id FROM pistas WHERE titulo LIKE 'QA Lote %';");
    pendientesLote = filas(`
      SELECT id FROM por_revisar
       WHERE resuelto_en IS NULL
         AND (
           json_extract(metadatos, '$.nombre_original') LIKE 'nbqa-lote-%'
           OR json_extract(metadatos, '$.nombre_original') LIKE '00_qa_lote_%'
         );
    `);
    const enCurso = Number(sql('SELECT count(*) FROM pendientes_importacion;'));
    if (
      !progreso.activa &&
      enCurso === 0 &&
      qa.length >= ARCHIVOS_LOTE &&
      pendientesLote.length === 0
    ) {
      break;
    }
    await esperar(100);
  }
  const tarjetas = await tarjetaImportacion(1000).catch(() => []);
  const duplicadas = filas(`
    SELECT sha256, count(*) FROM pistas
     WHERE sha256 IN (
       SELECT sha256 FROM pistas
        WHERE titulo LIKE 'QA Lote %' AND sha256 IS NOT NULL
     )
     GROUP BY sha256 HAVING count(*) > 1;
  `);
  if (qa.length !== ARCHIVOS_LOTE || duplicadas.length !== 0 || pendientesLote.length !== 0) {
    throw new Error(
      `Lote incoherente: pistas=${qa.length}, duplicadas=${JSON.stringify(
        duplicadas
      )}, pendientes=${pendientesLote.length}`
    );
  }
  console.log(
    'QA_CATALOGO_LOTE_REANUDADO',
    JSON.stringify({
      progreso,
      pistas: qa.length,
      duplicadas,
      pendientes: pendientesLote.length,
      tarjetas
    })
  );
}

function insertarPendiente(ruta, causa, metadatos) {
  const json = JSON.stringify(metadatos).replaceAll("'", "''");
  const rutaSql = ruta.replaceAll("'", "''");
  return sqlEscritura(
    `INSERT INTO por_revisar (ruta, causa, metadatos) VALUES ('${rutaSql}', '${causa}', '${json}'); SELECT last_insert_rowid();`
  );
}

async function escenarioRevisar() {
  const porRevisar = `${process.env.NB_QA_ROOT}/datos/por-revisar`;
  mkdirSync(porRevisar, { recursive: true });
  for (const [ruta] of filas(
    `SELECT ruta FROM por_revisar
      WHERE ruta LIKE '${porRevisar}/%'
        AND json_extract(metadatos, '$.nombre_original') LIKE 'nbqa-%';`
  )) {
    if (ruta.startsWith(`${porRevisar}/`)) {
      rmSync(ruta, { force: true });
    }
  }
  sqlEscritura(
    `DELETE FROM por_revisar
      WHERE ruta LIKE '${porRevisar}/%'
        AND json_extract(metadatos, '$.nombre_original') LIKE 'nbqa-%';`
  );
  const fuente = `${process.env.NB_QA_FASE4_FUENTES}/revisar`;
  const preparar = (nombre) => {
    const destino = `${porRevisar}/${nombre}`;
    copyFileSync(`${fuente}/${nombre}`, destino);
    return destino;
  };
  const talCual = preparar('nbqa-tal-cual.mp3');
  const reintentar = preparar('nbqa-reintentar.mp3');
  const descartar = preparar('nbqa-descartar.mp3');
  const sinConfirmar = preparar('nbqa-sin-confirmar.mp3');
  const fallida = preparar('nbqa-fallida.mp3');
  const danada = preparar('nbqa-danada.mp3');
  const duplicado = preparar('nbqa-duplicado.mp3');

  const idTalCual = Number(
    insertarPendiente(talCual, 'sin_candidatos', {
      nombre_original: 'nbqa-tal-cual.mp3',
      etiquetas: { titulo: 'QA Tal Cual', artista: 'QA Fase 4' },
      duracion_seg: 16
    })
  );
  const idReintentar = Number(
    insertarPendiente(reintentar, 'sin_candidatos', {
      nombre_original: 'nbqa-reintentar.mp3',
      etiquetas: { titulo: 'QA Reintentar' },
      duracion_seg: 16
    })
  );
  const idDescartar = Number(
    insertarPendiente(descartar, 'sin_candidatos', {
      nombre_original: 'nbqa-descartar.mp3',
      etiquetas: { titulo: 'QA Descartar' },
      duracion_seg: 16
    })
  );
  insertarPendiente(sinConfirmar, 'candidatos_ambiguos', {
    nombre_original: 'nbqa-sin-confirmar.mp3',
    etiquetas: { titulo: 'QA Sin Confirmar', artista: 'QA' },
    duracion_seg: 16
  });
  insertarPendiente(fallida, 'escritura_fallida', {
    nombre_original: 'nbqa-fallida.mp3',
    etiquetas: { titulo: 'QA Fallida', artista: 'QA' },
    duracion_seg: 16
  });
  insertarPendiente(danada, 'audio_ilegible', {
    nombre_original: 'nbqa-danada.mp3',
    etiquetas: { titulo: 'QA Dañada' },
    duracion_seg: 0
  });
  const pistaExistente = Number(
    sql("SELECT id FROM pistas WHERE estado = 'biblioteca' ORDER BY id LIMIT 1;")
  );
  insertarPendiente(duplicado, 'duplicado', {
    nombre_original: 'nbqa-duplicado.mp3',
    etiquetas: { titulo: 'QA Duplicada' },
    duracion_seg: 16,
    duplicado: { pista_id: pistaExistente, tipo: 'exacto' }
  });

  await ir('/por-revisar', '.grupo');
  const textos = await inspector.evaluar(
    `[...document.querySelectorAll(".grupo .titulo-grupo, .grupo h2, .grupo h3")].map((n) => n.textContent.trim())`
  );
  for (const esperado of [
    '¿Es la versión correcta?',
    'Sin confirmar',
    'No las encontramos',
    'Ya las tienes',
    'No se pudieron guardar',
    'Archivos dañados'
  ]) {
    if (!textos.some((t) => t.includes(esperado))) {
      throw new Error(`Falta el motivo ${esperado}: ${JSON.stringify(textos)}`);
    }
  }

  await politica(true, []);
  const pendientes = await invocar('por_revisar_listar');
  const candidato = pendientes.find((p) => p.candidatos.length === 3);
  if (!candidato) throw new Error('No está el pendiente con candidatos de AcoustID');
  const elegida = await invocar('por_revisar_importar', { id: candidato.id, candidato: 0 });
  await invocar('por_revisar_importar', { id: idTalCual, candidato: null });

  const antesReintento = await invocar('por_revisar_contar');
  await invocar('por_revisar_reintentar', { id: idReintentar });
  await esperarImportacion(30000);
  const despuesReintento = await invocar('por_revisar_contar');
  if (despuesReintento !== antesReintento) {
    throw new Error(
      `Buscar de nuevo no dejó el mismo pendiente: ${antesReintento} -> ${despuesReintento}`
    );
  }

  await invocar('por_revisar_descartar', { ids: [idDescartar] });
  const papelera = `${process.env.HOME}/.local/share/Trash`;
  const nombrePapelera = readdirSync(`${papelera}/files`).find(
    (nombre) => nombre === 'nbqa-descartar.mp3'
  );
  if (!nombrePapelera) throw new Error('El archivo descartado no está en la papelera');
  const informes = readdirSync(`${papelera}/info`).filter(
    (nombre) =>
      nombre === 'nbqa-descartar.mp3.trashinfo' ||
      (nombre.startsWith('nbqa-descartar.mp3.') && nombre.endsWith('.trashinfo'))
  );
  if (informes.length !== 1) {
    throw new Error(`La entrada de papelera no tiene un único informe: ${informes}`);
  }
  const archivoPapelera = `${papelera}/files/${nombrePapelera}`;
  const informePapelera = `${papelera}/info/${informes[0]}`;
  if (!readFileSync(informePapelera, 'utf8').includes(descartar)) {
    throw new Error('El informe de papelera no corresponde al archivo descartado');
  }
  renameSync(archivoPapelera, descartar);
  unlinkSync(informePapelera);
  if (!existsSync(descartar)) throw new Error('El archivo no se restauró a su sitio');
  unlinkSync(descartar);
  await invocar('por_revisar_descartar', { ids: [idDescartar] }).catch(() => {});

  console.log(
    'QA_CATALOGO_REVISAR',
    JSON.stringify({
      motivos: textos,
      candidato: { id: candidato.id, pista: elegida },
      talCual: idTalCual,
      reintento: [antesReintento, despuesReintento],
      papelera: archivoPapelera,
      restaurado: true
    })
  );
}

async function escenarioPrivacidadServicio() {
  await ir('/', '.carcasa');
  const [pista] = filas(`
    SELECT p.id
      FROM pistas p
      JOIN albumes a ON a.id = p.album_id
     WHERE p.estado = 'biblioteca'
       AND p.verificada = 1
       AND a.portada_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM letras l WHERE l.pista_id = p.id)
     ORDER BY p.id
     LIMIT 1;
  `);
  if (!pista) throw new Error('No hay una pista verificada para probar el corte por servicio');
  await politica(true, ['musicBrainz']);
  const antes = peticionesRed();
  const resultado = await invocar('completar_datos', { pista: Number(pista[0]) });
  const despues = peticionesRed();
  if ((despues.Lrclib ?? 0) !== (antes.Lrclib ?? 0)) {
    throw new Error(`LRCLIB siguió saliendo tras apagarlo: ${JSON.stringify({ antes, despues })}`);
  }
  await politica(true, ['acoustId', 'musicBrainz', 'coverArtArchive', 'lrclib']);
  console.log(
    'QA_CATALOGO_PRIVACIDAD_SERVICIO',
    JSON.stringify({ pista: Number(pista[0]), resultado, antes, despues })
  );
}

async function escenarioCompletarEditar() {
  await ir('/', '.carcasa');
  await politica(false, []);
  const antes = idsAntes();
  const importacionAntes = ultimaImportacion();
  await seleccionarCarpeta(`${process.env.NB_QA_FASE4_FUENTES}/completar`);
  await esperarImportacionTerminada(importacionAntes);
  const nuevas = nuevasDesde(antes);
  if (nuevas.length !== 1)
    throw new Error(`No entró la pista para completar: ${JSON.stringify(nuevas)}`);
  const pista = Number(nuevas[0][0]);
  const archivo = `${process.env.NB_QA_ROOT}/biblioteca/${nuevas[0][6]}`;
  if (
    statSync(archivo).ino ===
    statSync(`${process.env.NB_QA_FASE4_FUENTES}/completar/nbqa-completar.mp3`).ino
  ) {
    throw new Error('La pista importada es un enlace duro a la fuente');
  }

  await abrirMovil();
  const manifiestoAntes = await manifestMovil();
  const antesPista = manifiestoAntes.pistas.find((p) => p.id === pista);
  const [antesDatos] = filas(
    `SELECT coalesce(p.portada_id, 0), (SELECT count(*) FROM letras l WHERE l.pista_id=p.id)
       FROM pistas p WHERE p.id=${pista};`
  );
  if (Number(antesDatos[0]) !== 0 || antesDatos[1] !== '0') {
    throw new Error(`La pista ya tenía datos antes de completarla: ${JSON.stringify(antesDatos)}`);
  }
  const conDatos = `${archivo}.con-datos.mp3`;
  execFileSync('ffmpeg', [
    '-hide_banner',
    '-loglevel',
    'error',
    '-y',
    '-i',
    archivo,
    '-i',
    `${process.env.NB_QA_ROOT}/fase4/portada-qa.jpg`,
    '-map',
    '0:a',
    '-map',
    '1:v',
    '-c:a',
    'copy',
    '-c:v',
    'mjpeg',
    '-disposition:v',
    'attached_pic',
    '-metadata',
    'lyrics=Primera línea de la copia\nSegunda línea de la copia',
    '-id3v2_version',
    '3',
    conDatos
  ]);
  renameSync(conDatos, archivo);
  await politica(false, []);
  const completado = await invocar('completar_datos', { pista });
  if (!completado.portada || !completado.letra) {
    throw new Error(`Completar datos no añadió todo: ${JSON.stringify(completado)}`);
  }
  const manifiestoCompleto = await manifestMovil(manifiestoAntes.sync_version_actual);
  const albumCompleto = manifiestoCompleto.albums.find((a) => a.id === antesPista.album_id);
  if (!albumCompleto) throw new Error('El manifest no recibió el álbum con su portada');
  if (!antesPista.cover_url || !antesPista.lyrics_url) {
    throw new Error(`La pista no expuso sus recursos: ${JSON.stringify(antesPista)}`);
  }
  const portada = await peticionMovil({ ruta: antesPista.cover_url });
  const letra = await peticionMovil({ ruta: antesPista.lyrics_url });
  if (portada.estado !== 200 || letra.estado !== 200) {
    throw new Error(`El cliente no pudo bajar los datos nuevos: ${portada.estado}/${letra.estado}`);
  }

  const [albumAntes] = filas(
    `SELECT a.id, a.portada_id FROM albumes a JOIN pistas p ON p.album_id=a.id WHERE p.id=${pista};`
  );
  const datosAntes = await invocar('datos_pista', { pista });
  await invocar('editar_pista', {
    pista,
    datos: {
      titulo: 'QA Editado',
      artista: datosAntes.artista,
      album: datosAntes.album,
      numero: 7,
      anio: 2026,
      genero: 'QA'
    }
  });
  const versionAntesAlbum = manifiestoCompleto.sync_version_actual;
  const album = await invocar('editar_album', {
    album: Number(albumAntes[0]),
    datos: { titulo: 'QA Álbum Renombrado', artista: datosAntes.artista, anio: 2026 }
  });
  if (album !== Number(albumAntes[0])) throw new Error('Renombrar el álbum cambió su id');
  const [portadaDespues] = filas(`SELECT portada_id FROM albumes WHERE id=${album};`);
  if (portadaDespues[0] !== albumAntes[1]) throw new Error('Renombrar perdió la portada');

  const manifiestoEditado = await manifestMovil(versionAntesAlbum);
  const editada = manifiestoEditado.pistas.find((p) => p.id === pista);
  if (
    editada?.titulo !== 'QA Editado' ||
    editada?.artista_nombre !== datosAntes.artista ||
    editada?.album_titulo !== 'QA Álbum Renombrado'
  ) {
    throw new Error(`El móvil no recibió la edición: ${JSON.stringify(editada)}`);
  }

  const etiquetas = execFileSync(
    'cargo',
    [
      'test',
      '--manifest-path',
      `${process.env.NB_QA_RAIZ}/src-tauri/Cargo.toml`,
      '--test',
      'qa_fase4',
      'lee_las_etiquetas_del_archivo_editado',
      '--',
      '--ignored',
      '--nocapture',
      '--test-threads=1'
    ],
    {
      cwd: `${process.env.NB_QA_RAIZ}/src-tauri`,
      encoding: 'utf8',
      env: { ...process.env, NB_QA_ARCHIVO: archivo }
    }
  );

  const reimportar = `${process.env.NB_QA_FASE4_FUENTES}/reimportar`;
  rmSync(reimportar, { recursive: true, force: true });
  mkdirSync(reimportar, { recursive: true });
  execFileSync('ffmpeg', [
    '-hide_banner',
    '-loglevel',
    'error',
    '-y',
    '-i',
    archivo,
    '-map',
    '0:a',
    '-map_metadata',
    '0',
    '-af',
    'apad=pad_dur=1',
    '-c:a',
    'libmp3lame',
    '-q:a',
    '4',
    `${reimportar}/nbqa-reimportar.mp3`
  ]);
  const antesReimportar = idsAntes();
  const importacionReimportar = ultimaImportacion();
  await seleccionarCarpeta(reimportar);
  await esperarImportacionTerminada(importacionReimportar);
  const reimportadas = nuevasDesde(antesReimportar);
  if (reimportadas.length !== 1 || reimportadas[0][1] !== 'QA Editado') {
    throw new Error(`Reimportar perdió los datos editados: ${JSON.stringify(reimportadas)}`);
  }
  const informeEtiquetas = JSON.parse(
    etiquetas
      .split('\n')
      .find((linea) => linea.includes('INFORME_QA'))
      .replace(/^.*INFORME_QA /, '')
  );
  if (
    informeEtiquetas.datos.titulo !== 'QA Editado' ||
    informeEtiquetas.datos.album !== 'QA Álbum Renombrado' ||
    Number(informeEtiquetas.datos.numero) !== 7 ||
    !informeEtiquetas.datos.isrc
  ) {
    throw new Error(`El archivo no recibió la edición: ${etiquetas}`);
  }

  console.log(
    'QA_CATALOGO_EDITAR',
    JSON.stringify({
      pista,
      archivo,
      completado,
      manifiestoAntes: antesPista,
      manifiestoCompleto: albumCompleto,
      portada: portada.estado,
      letra: letra.estado,
      album: { antes: albumAntes, despues: [album, portadaDespues[0]] },
      editada,
      etiquetas: informeEtiquetas,
      reimportadas,
      origenNoEnlazado: true
    })
  );
}

async function escenarioEstadoCopia() {
  const filasCopia = Object.fromEntries(
    [
      ['pistas', 'SELECT count(*) FROM pistas'],
      ['albumes', 'SELECT count(*) FROM albumes'],
      ['artistas', 'SELECT count(*) FROM artistas'],
      ['playlists', 'SELECT count(*) FROM playlists'],
      ['historial', 'SELECT count(*) FROM historial'],
      ['correcciones', 'SELECT count(*) FROM correcciones_catalogo'],
      ['por_revisar', 'SELECT count(*) FROM por_revisar']
    ].map(([nombre, consulta]) => [nombre, Number(sql(consulta))])
  );
  writeFileSync(
    `${process.env.NB_QA_INFORMES}/fase4-sumas-antes.json`,
    `${JSON.stringify(filasCopia, null, 2)}\n`
  );
  console.log('QA_CATALOGO_ESTADO_COPIA', JSON.stringify({ filas: filasCopia }));
}

async function escenarioVerificarCopia() {
  const antes = JSON.parse(
    readFileSync(`${process.env.NB_QA_INFORMES}/fase4-sumas-antes.json`, 'utf8')
  );
  const despues = Object.fromEntries(
    [
      ['pistas', 'SELECT count(*) FROM pistas'],
      ['albumes', 'SELECT count(*) FROM albumes'],
      ['artistas', 'SELECT count(*) FROM artistas'],
      ['playlists', 'SELECT count(*) FROM playlists'],
      ['historial', 'SELECT count(*) FROM historial'],
      ['correcciones', 'SELECT count(*) FROM correcciones_catalogo'],
      ['por_revisar', 'SELECT count(*) FROM por_revisar']
    ].map(([nombre, consulta]) => [nombre, Number(sql(consulta))])
  );
  if (JSON.stringify(antes) !== JSON.stringify(despues)) {
    throw new Error(`Las sumas restauradas no coinciden: ${JSON.stringify({ antes, despues })}`);
  }
  const cambio = filas("SELECT id FROM playlists WHERE nombre='QA Cambio Antes De Restaurar';");
  if (cambio.length !== 0)
    throw new Error('La restauración conservó el cambio posterior a la copia');
  console.log(
    'QA_CATALOGO_COPIA_RESTAURADA',
    JSON.stringify({ antes, despues, cambioAusente: true })
  );
}

try {
  const escenario = process.argv[2] ?? 'probe';
  if (escenario === 'red') await escenarioRed();
  else if (escenario === 'probe-red') {
    console.log(
      'RESULTADO_SELECTOR',
      JSON.stringify(await seleccionarCarpeta(`${process.env.NB_QA_FASE4_FUENTES}/red-real`))
    );
  } else if (escenario === 'sin-red') await escenarioSinRed();
  else if (escenario === 'importar-lote') await escenarioImportarLote();
  else if (escenario === 'verificar-lote') await escenarioVerificarLote();
  else if (escenario === 'revisar') await escenarioRevisar();
  else if (escenario === 'privacidad-servicio') await escenarioPrivacidadServicio();
  else if (escenario === 'completar-editar') await escenarioCompletarEditar();
  else if (escenario === 'estado-copia') await escenarioEstadoCopia();
  else if (escenario === 'verificar-copia') await escenarioVerificarCopia();
  else {
    const seleccionados = await seleccionarCarpeta(process.env.NB_QA_FASE4_FUENTES);
    console.log('RESULTADO_SELECTOR', JSON.stringify(seleccionados));
  }
} finally {
  agente.destroy();
  inspector.cerrar();
}
