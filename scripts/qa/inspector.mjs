/**
 * Cliente mínimo del inspector remoto de WebKit para las pruebas finales.
 *
 * WebKit multiplexa la página detrás de `Target.sendMessageToTarget`; no expone
 * los comandos del DOM directamente en la conexión del inspector. Este cliente
 * mantiene esa diferencia encapsulada.
 */

const PUERTO = Number(process.env.NB_QA_INSPECTOR_PORT ?? 9333);
const ESPERA_MS = 20_000;

function esperar(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function obtenerSocket() {
  const limite = Date.now() + ESPERA_MS;
  while (Date.now() < limite) {
    try {
      const respuesta = await fetch(`http://127.0.0.1:${PUERTO}/`);
      const html = await respuesta.text();
      const coincidencia = html.match(/\/socket\/[^'"]+/);
      if (coincidencia) return coincidencia[0];
    } catch {
      // El inspector todavía no está escuchando.
    }
    await esperar(100);
  }
  throw new Error(`el inspector no apareció en 127.0.0.1:${PUERTO}`);
}

export class Inspector {
  #ws;
  #target;
  #siguiente = 1000;
  #pendientes = new Map();
  #erroresConsola = [];

  static async conectar() {
    const inspector = new Inspector();
    await inspector.#abrir();
    return inspector;
  }

  async #abrir() {
    const socket = await obtenerSocket();
    this.#ws = new WebSocket(`ws://127.0.0.1:${PUERTO}${socket}`);
    this.#ws.onmessage = (evento) => this.#recibir(JSON.parse(String(evento.data)));
    await new Promise((resolve, reject) => {
      const limite = setTimeout(
        () => reject(new Error('WebSocket del inspector sin respuesta')),
        ESPERA_MS
      );
      this.#ws.onerror = () => {
        clearTimeout(limite);
        reject(new Error('no se pudo abrir el WebSocket del inspector'));
      };
      this.#ws.onopen = () => {
        clearTimeout(limite);
        resolve();
      };
    });
    await new Promise((resolve, reject) => {
      const limite = setTimeout(
        () => reject(new Error('el inspector no anunció ninguna página')),
        ESPERA_MS
      );
      const original = this.#ws.onmessage;
      this.#ws.onmessage = (evento) => {
        const mensaje = JSON.parse(String(evento.data));
        original(evento);
        if (mensaje.method === 'Target.targetCreated') {
          this.#target = mensaje.params.targetInfo.targetId;
          clearTimeout(limite);
          this.#ws.onmessage = original;
          resolve();
        }
      };
    });
    await this.#enviar('Runtime.enable');
    await this.#enviar('Console.enable');
  }

  #recibir(mensaje) {
    if (mensaje.method === 'Target.dispatchMessageFromTarget') {
      const interno = JSON.parse(mensaje.params.message);
      if (
        interno.method === 'Console.messageAdded' &&
        ['error', 'assert'].includes(interno.params?.message?.level)
      ) {
        this.#erroresConsola.push(interno.params.message.text ?? '');
      }
      const pendiente = this.#pendientes.get(interno.id);
      if (pendiente) {
        this.#pendientes.delete(interno.id);
        if (interno.error) pendiente.reject(new Error(interno.error.message));
        else pendiente.resolve(interno.result);
      }
    }
  }

  async #enviar(metodo, params = {}) {
    if (!this.#target) throw new Error('el inspector no tiene una página asociada');
    const id = this.#siguiente++;
    const interno = JSON.stringify({ id, method: metodo, params });
    const respuesta = await new Promise((resolve, reject) => {
      const limite = setTimeout(() => {
        this.#pendientes.delete(id);
        reject(new Error(`${metodo} no respondió`));
      }, ESPERA_MS);
      this.#pendientes.set(id, {
        resolve: (valor) => {
          clearTimeout(limite);
          resolve(valor);
        },
        reject: (error) => {
          clearTimeout(limite);
          reject(error);
        }
      });
      this.#ws.send(
        JSON.stringify({
          id,
          method: 'Target.sendMessageToTarget',
          params: { targetId: this.#target, message: interno }
        })
      );
    });
    return respuesta;
  }

  async evaluar(expresion) {
    const evaluado = await this.#enviar('Runtime.evaluate', {
      expression: `Promise.resolve(${expresion})`,
      returnByValue: false,
      doNotPauseOnExceptionsAndMuteConsole: true
    });
    if (evaluado.wasThrown || evaluado.result?.subtype === 'error') {
      throw new Error(evaluado.result?.description ?? 'Runtime.evaluate lanzó una excepción');
    }
    let objeto = evaluado.result;
    if (objeto?.className === 'Promise') {
      let resuelto;
      try {
        resuelto = await this.#enviar('Runtime.awaitPromise', {
          promiseObjectId: objeto.objectId,
          returnByValue: true,
          generatePreview: false
        });
      } catch (error) {
        throw new Error(`${error.message} al evaluar ${expresion.slice(0, 160)}`);
      }
      if (resuelto.wasThrown) {
        throw new Error(resuelto.result?.description ?? 'la promesa evaluada fue rechazada');
      }
      objeto = resuelto.result;
    }
    return objeto?.value;
  }

  async evaluarDirecto(expresion) {
    const evaluado = await this.#enviar('Runtime.evaluate', {
      expression: expresion,
      returnByValue: true,
      doNotPauseOnExceptionsAndMuteConsole: true
    });
    if (evaluado.wasThrown || evaluado.result?.subtype === 'error') {
      throw new Error(evaluado.result?.description ?? 'Runtime.evaluate lanzó una excepción');
    }
    return evaluado.result?.value;
  }

  async instalarCapturaDeErrores() {
    this.#erroresConsola = [];
    await this.#enviar('Console.clearMessages');
    await this.evaluar(`(() => {
      if (window.__nbQaErrores) return true;
      window.__nbQaErrores = [];
      const guardar = (texto) => window.__nbQaErrores.push(String(texto));
      const original = console.error;
      console.error = (...argumentos) => {
        guardar(argumentos.map((x) => {
          if (x instanceof Error) return x.stack || x.message;
          try { return JSON.stringify(x); } catch { return String(x); }
        }).join(" "));
        original.apply(console, argumentos);
      };
      addEventListener("error", (evento) => {
        const objetivo = evento.target;
        guardar(JSON.stringify({
          mensaje: evento.error?.stack || evento.message || "error de recurso",
          recurso: objetivo?.currentSrc || objetivo?.src || objetivo?.href || null,
          etiqueta: objetivo?.tagName || null
        }));
      }, true);
      addEventListener("unhandledrejection", (evento) =>
        guardar(evento.reason?.stack || String(evento.reason))
      );
      return true;
    })()`);
  }

  async errores() {
    const delRuntime = await this.evaluar(`window.__nbQaErrores ? [...window.__nbQaErrores] : []`);
    return [...this.#erroresConsola, ...(delRuntime ?? [])];
  }

  cerrar() {
    this.#ws?.close();
  }
}

export { esperar };
