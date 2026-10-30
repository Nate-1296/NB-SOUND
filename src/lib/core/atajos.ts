/**
 * Los atajos de teclado de la V1 (`Principal.qml`), dentro de la ventana.
 *
 * Las teclas multimedia no van aquí: llegan a todo el sistema por MPRIS y SMTC
 * (F2.1.5). Ningún atajo de una sola tecla actúa mientras se escribe en un campo.
 */

export type AccionDeAtajo =
  | 'pausarReanudar'
  | 'retroceder'
  | 'avanzar'
  | 'anterior'
  | 'siguiente'
  | 'aleatorio'
  | 'repeticion'
  | 'letras'
  | 'cola'
  | 'mini'
  | 'ampliada'
  | 'karaoke'
  | 'subirVolumen'
  | 'bajarVolumen';

export interface Tecla {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
  /** El foco está en un campo de texto. */
  escribiendo: boolean;
}

const SIMPLES: Readonly<Record<string, AccionDeAtajo>> = {
  ' ': 'pausarReanudar',
  ArrowLeft: 'retroceder',
  ArrowRight: 'avanzar',
  ArrowUp: 'anterior',
  ArrowDown: 'siguiente',
  s: 'aleatorio',
  r: 'repeticion',
  l: 'letras',
  f: 'ampliada',
  k: 'karaoke',
  '+': 'subirVolumen',
  '=': 'subirVolumen',
  '-': 'bajarVolumen'
};

const CON_CONTROL: Readonly<Record<string, AccionDeAtajo>> = {
  q: 'cola',
  m: 'mini'
};

/** La acción de una pulsación, o `null` si no es un atajo. */
export function accionDeTecla(t: Tecla): AccionDeAtajo | null {
  if (t.altKey) return null;
  const tecla = t.key.length === 1 ? t.key.toLowerCase() : t.key;
  if (t.ctrlKey || t.metaKey) return CON_CONTROL[tecla] ?? null;
  if (t.escribiendo) return null;
  return SIMPLES[tecla] ?? null;
}

/** Si el elemento con el foco recibe texto. */
export function esCampoDeTexto(el: Element | null): boolean {
  if (!el) return false;
  if (el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement) return true;
  if (el instanceof HTMLInputElement) {
    // Un deslizador también usa las flechas: no se le quitan.
    return !['checkbox', 'radio', 'button', 'submit'].includes(el.type);
  }
  return (el as HTMLElement).isContentEditable === true;
}
