# Validación de la integración Launcher en 2.1.2

Fecha: 2026-11-12. Estado: fuente verificada en Linux; paquete firmado y publicación pendientes.

## Comprobado localmente

- `pnpm verify`: formato, tipos sin errores/advertencias, 38 pruebas frontend y guardianes
  correctos, incluidos contrato móvil, red, privacidad, puente, binarios y empaquetado web.
- `cargo fmt --all -- --check`, Clippy de todos los targets/features con `-D warnings` y
  pruebas Rust: 647 correctas y 24 omitidas por requisitos de corpus o escenarios QA.
- `pnpm tauri build --debug --no-bundle --ci`: binario nativo con frontend integrado.
- La exportación compartida coincide con la fuente canónica de Launcher:
  `dacf15206e9a6497f88609b97457740ddab72e2b3431a8d030915c6d044f56ae`.
- Recorrido real Launcher, host y Sound con datos temporales y KWin aislado: autorización,
  cambios en ambos sentidos, conflicto/validación de dominio cubiertos por pruebas y
  desconexión que conserva Sound y rechaza nuevas consultas del Launcher.
- Conexión mantenida 961 segundos desde el inicio del recorrido autorizado. Se deshabilitó
  el sondeo del frontend durante la espera; el supervisor Rust mantuvo ambos extremos.
  Después se confirmaron lecturas y cambios semanal/mensual y se revocó el acceso.
- El ensayo del módulo de instalación verifica marca/estructura, recursos relativos,
  exclusión entre proceso y gestor y rechazo de una marca inválida o ausente en un árbol
  administrado. Una pérdida de marca durante el arranque no habilita el actualizador propio.

No se modificó una biblioteca personal ni NB Sound Mobile. Los escenarios omitidos siguen
sin ejecutarse; esta iteración no los presenta como aprobados. La muestra de propagación
de 17 ms entre los dos DOM corresponde a desarrollo y no es un presupuesto de producción.

## Pendiente antes de publicar

CI y generación de artefactos firmados, verificación del tar de distribución y prueba de
instalación administrada real: apertura, bloqueo por uso, recurso local y rechazo del
actualizador independiente con `INSTALLATION_MANAGED`. Los resultados se registrarán aquí.
La ejecución de la UI Windows/macOS sigue pendiente y no se deduce de compilar sus paquetes.
