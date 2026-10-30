#!/usr/bin/env python3
"""F0.4.7: mide el desplazamiento de la lista en WebKitGTK, el motor de Tauri.

Basado en `NB_Books/scripts/medir-en-webkitgtk.py`. Uso:

    pnpm exec vite build --config scripts/prototipos/lista/vite.config.js
    pnpm exec vite preview --config scripts/prototipos/lista/vite.config.js --port 4175 &
    python3 scripts/prototipos/lista/medir.py "http://localhost:4175/?total=100000"

Desplaza la lista durante 8 s a 3.000 px por segundo (unas 54 filas por segundo,
un arrastre rápido de la barra) y cuenta los fotogramas: cuántos tardan más de
16,7 ms y más de 50 ms, y cuántos nodos tiene el documento.
"""

import json
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import GLib, Gtk, WebKit2  # noqa: E402

URL = sys.argv[1]
GUION = r"""
new Promise((resolver) => {
  const lista = document.querySelector('.lista');
  const tiempos = [];
  let anterior = performance.now();
  const inicio = anterior;
  const paso = (ahora) => {
    tiempos.push(ahora - anterior);
    anterior = ahora;
    lista.scrollTop = ((ahora - inicio) / 1000) * 3000;
    if (ahora - inicio < 8000) requestAnimationFrame(paso);
    else {
      tiempos.shift();
      tiempos.sort((a, b) => a - b);
      resolver(JSON.stringify({
        fotogramas: tiempos.length,
        mediana_ms: +tiempos[tiempos.length >> 1].toFixed(1),
        p95_ms: +tiempos[Math.floor(tiempos.length * 0.95)].toFixed(1),
        largos_16: tiempos.filter((t) => t > 16.7 * 1.5).length,
        largos_50: tiempos.filter((t) => t > 50).length,
        nodos: document.getElementsByTagName('*').length,
        filas_llegadas: lista.scrollTop
      }));
    }
  };
  requestAnimationFrame(paso);
})
"""

ventana = Gtk.Window()
ventana.set_default_size(1280, 800)
vista = WebKit2.WebView(web_context=WebKit2.WebContext.new_ephemeral())
ventana.add(vista)
ventana.show_all()
estado = {"listo": False}


def evaluar(codigo, al_terminar):
    def cb(fuente, resultado, _):
        try:
            v = fuente.evaluate_javascript_finish(resultado)
            al_terminar(v.to_string() if v else None)
        except Exception as e:  # noqa: BLE001
            al_terminar(f"ERROR {e}")

    vista.evaluate_javascript(codigo, -1, None, None, None, cb, None)


def al_cargar(_v, evento):
    if evento != WebKit2.LoadEvent.FINISHED or estado["listo"]:
        return
    estado["listo"] = True

    def arrancar():
        evaluar(f"window.__r=null; ({GUION}).then(v => window.__r = v); 'ok'", lambda _: None)
        GLib.timeout_add(500, sondear)
        return False

    def sondear():
        def visto(v):
            if v and v != "null":
                print(json.dumps(json.loads(v), ensure_ascii=False))
                Gtk.main_quit()
            else:
                GLib.timeout_add(500, sondear)

        evaluar("window.__r", visto)
        return False

    GLib.timeout_add(2500, arrancar)


vista.connect("load-changed", al_cargar)
vista.load_uri(URL)
GLib.timeout_add(60_000, lambda: (print("TIMEOUT"), Gtk.main_quit(), False)[2])
Gtk.main()
