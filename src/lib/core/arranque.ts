/**
 * Muestra la ventana aunque la apariencia guardada no llegue.
 *
 * La ventana nace oculta para no enseñar el tema de fábrica. Esa espera no puede
 * dejar la aplicación abierta sin interfaz: un rechazo usa la apariencia de la
 * caché y el vencimiento hace lo mismo cuando la lectura se queda colgada.
 */
export const ESPERA_APARIENCIA_MS = 1500;

export async function mostrarVentanaTrasApariencia(
  apariencia: Promise<void>,
  mostrar: () => Promise<void>,
  esperaMs = ESPERA_APARIENCIA_MS
): Promise<void> {
  let temporizador: ReturnType<typeof setTimeout> | undefined;
  const vencimiento = new Promise<void>((resolve) => {
    temporizador = setTimeout(resolve, esperaMs);
  });

  try {
    await Promise.race([apariencia.catch(() => undefined), vencimiento]);
  } finally {
    if (temporizador !== undefined) clearTimeout(temporizador);
    await mostrar();
  }
}
