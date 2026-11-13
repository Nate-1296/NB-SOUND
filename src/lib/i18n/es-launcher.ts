/** Textos del consentimiento y los permisos locales, cargados bajo demanda. */
export const esLauncher = {
  titulo: 'Acceso de NB Launcher',
  descripcion: 'Autorizaciones recordadas para la frecuencia de tus copias de seguridad.',
  solicitud: 'Permitir acceso desde Launcher',
  alcance: (cambiar: boolean, observar: boolean) =>
    `La solicitud local permite consultar la frecuencia${cambiar ? ', cambiarla' : ''}${observar ? ' y recibir sus cambios' : ''}. Sound recordará este permiso en este equipo. Puedes revocarlo en Ajustes → Privacidad.`,
  permitir: 'Permitir y recordar',
  recordadas: (n: number) =>
    n === 1 ? '1 autorización recordada' : `${n} autorizaciones recordadas`,
  ninguna: 'No hay autorizaciones recordadas.',
  revocadas: 'Hay autorizaciones revocadas. Esas identidades no pueden volver a conectarse.',
  revocar: 'Revocar autorizaciones recordadas',
  efectoRevocar: 'Las sesiones abiertas con estas autorizaciones se cerrarán.',
  permitirSolicitudes: 'Permitir solicitudes de nuevo',
  efectoPermitir: 'Volverá a pedir tu confirmación; esto no concede acceso.',
  noDisponible: 'No se pueden solicitar nuevas autorizaciones en esta sesión.',
  fallo: 'No se pudo confirmar el permiso de Launcher.',
  trabajando: 'Guardando…'
} as const;
export type TextosLauncher = typeof esLauncher;
