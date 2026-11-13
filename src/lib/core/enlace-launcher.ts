/** Control de consentimiento de la capa global diferida, sin bloquear la carcasa. */
import { alCambiarEnlaceLauncher, estadoEnlaceLauncher } from './ipc/launcher.ts';

export async function iniciarSolicitudLauncher(mostrar: () => void): Promise<() => void> {
  let activo = true;
  let mostrado = false;
  const comprobar = async () => {
    if (!activo || mostrado) return;
    const estado = await estadoEnlaceLauncher();
    if (activo && estado.pendiente && !mostrado) {
      mostrado = true;
      mostrar();
    }
  };
  const soltar = await alCambiarEnlaceLauncher(() => {
    void comprobar().catch(() => {});
  });
  void comprobar().catch(() => {});
  return () => {
    activo = false;
    soltar();
  };
}
