/**
 * Formatos de tiempo de la V1, con sus pruebas traducidas en `formato.test.ts`.
 */

/** `1d 1h 1m 1s`, omitiendo las unidades a cero (`formatear_duracion_detallada`). */
export function duracionDetallada(segundos: number | null | undefined): string {
  const total = Math.max(0, Math.floor(segundos ?? 0));
  const partes: string[] = [];
  const d = Math.floor(total / 86_400);
  const h = Math.floor((total % 86_400) / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (d) partes.push(`${d}d`);
  if (h) partes.push(`${h}h`);
  if (m) partes.push(`${m}m`);
  if (s) partes.push(`${s}s`);
  return partes.length ? partes.join(' ') : '0s';
}

/** `1h 0m 0s`: desde la primera unidad, todas (`formatear_duracion_larga`, la de la cola). */
export function duracionLarga(segundos: number | null | undefined): string {
  const total = Math.max(0, Math.floor(segundos ?? 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h) return `${h}h ${m}m ${s}s`;
  if (m) return `${m}m ${s}s`;
  return `${s}s`;
}
