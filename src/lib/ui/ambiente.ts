/**
 * El color de la portada en la cabecera de un álbum, un artista o una playlist:
 * `use:ambiente={pistaId}` aplica a ese elemento la paleta de Material sacada de
 * la portada de la pista, como la vista de reproducción, y sus `--m3c-*` tiñen
 * solo lo que hay dentro. Respeta "Color por portada" de Ajustes; sin portada,
 * el tono sale de una semilla estable de la pista y no cambia entre visitas.
 */
import { aparienciaActual } from '#lib/core/apariencia.svelte.ts';
import { ambienteDePista } from '#lib/core/ipc/index.ts';

import { aplicarApariencia, semillaDesdeHsl } from './tema.ts';

export function ambiente(nodo: HTMLElement, pistaId: number | null) {
  let vigente = 0;

  function aplicar(id: number | null) {
    const turno = ++vigente;
    if (id === null || !aparienciaActual.actual.colorPorPortada) return;
    void ambienteDePista(id)
      .then((a) => {
        if (turno !== vigente) return;
        const oscuro = document.documentElement.dataset.esquema !== 'claro';
        return aplicarApariencia(
          nodo,
          {
            tema: oscuro ? 'oscuro' : 'claro',
            contraste: 'normal',
            semilla: semillaDesdeHsl(a.h, a.s, a.l)
          },
          oscuro
        );
      })
      .catch(() => {
        // Sin color, la cabecera se queda con el del tema.
      });
  }

  aplicar(pistaId);
  return {
    update: aplicar,
    destroy() {
      vigente += 1;
    }
  };
}
