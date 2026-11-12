# Fase 9: integración con la suite

Alcance aprobado por Nathan mediante [ADR-013](../adr/decisions/ADR-013-launcher-frecuencia.md).
La aplicación conserva su dominio. Esta fase no cambia NB Sound Mobile. Nathan autorizó
posteriormente las releases de esta integración desde el contrato de NB Launcher.

| Iteración | Estado y criterio |
|---|---|
| F9.1.1 Frecuencia de copia compartida | Parcial: recorrido real Linux y verificación completa correctos. Propietario, V12, puente revisionado, observación bidireccional y reapertura comprobados. Registro, permisos por recurso y consentimiento ya implementados en la primera UI de Launcher y comprobados en Linux; falta ejecutar ese recorrido en Windows/macOS. |
| F9.1.2 Renovación privada | Implementada y comprobada en Linux: enlace real de 961 segundos sin sondeo del frontend, lectura/escritura posterior y revocación. Compatible con negociación 1. Publicada en 2.1.3; recorrido de UI en otras plataformas pendiente. Ver ADR-014. |
| F9.1.3 Instalación administrada | Validada en Linux bajo ADR-015 con el tar firmado 2.1.3 publicado: apertura, recursos, exclusión por uso, actualizador delegado y ajuste conservado tras reinstalar. Otros formatos/plataformas pendientes. |

## Propiedad y persistencia

`frecuencia_compartida.rs` lee preferencia y secuencia coherentemente. `compare_and_set`
valida con `FRECUENCIAS` y confirma ambas en una sola transacción inmediata. La interfaz
nativa y el enlace externo comparten una instancia del recurso. Solo se notifica después
del commit; un conflicto devuelve el estado confirmado y no repite una edición antigua.

V12 añade `revision_de_recursos`, sin mover `copia_cada_dias`. Conserva la lectura heredada
de `1.0` y usa `instalacion.id_instalacion`. La época se genera en memoria después de una
restauración pendiente; una reapertura invalida revisiones anteriores.

**Compatibilidad:** los binarios anteriores rechazan V12. La copia previa `.v11.respaldo`
permite recuperar la base anterior; no hay downgrade automático del archivo migrado.
El formato ZIP, el planificador de copias y el contrato móvil siguen siendo de Sound.

## Enlace de desarrollo

Sin `--nb-launcher`, Sound no inicia este enlace. Con el indicador, espera un bootstrap
framed en stdin privado durante cinco segundos. El supervisor conoce el endpoint y verifica
UID/SID y PID antes de enviar la credencial; stdout sigue dedicado a registros.
La credencial solo da acceso al recurso de frecuencia, no a otras operaciones de Sound.
EOF del supervisor o 15 minutos sin renovación cierran el enlace sin terminar la aplicación.
El protocolo 2 acepta renovación framed exclusivamente por la tubería heredada, según
[ADR-014](../adr/decisions/ADR-014-renovacion-launcher.md). El protocolo 1 sigue disponible.

Este puerto no es Mesh ni el catálogo general del host. El consentimiento y los permisos
por operación se aplican en Launcher: su primera UI ya registra este propietario y filtra
las capacidades del consumidor. El enlace de Sound no se habilita por defecto.

## Exportación y comprobaciones

`src-tauri/vendor/nb-shared` es una exportación sellada Apache 2.0 de Launcher. Incluye
licencia, fuentes, manifiesto y rustfmt propio. No editarla manualmente ni depender de
carpetas externas al clon. `node scripts/check-shared.mjs` comprueba el sello y forma parte
de `pnpm guardianes`. Las dependencias se resuelven en el Cargo.lock de Sound.

El cambio del bundle se revisa y se regenera desde la fuente canónica. La comprobación de
hash detecta deriva; no es una firma ni demuestra procedencia por sí sola.

## Validación registrada

En Linux pasaron `pnpm verify` (38 pruebas frontend y guardianes), fmt, Clippy de todos
los targets/features y `cargo test`: 645 correctas, 24 omitidas. Incluye las respuestas
doradas del contrato móvil. Las omitidas necesitan corpus o escenarios QA específicos.
Las nuevas pruebas cubren conflicto/no-op, entrada inválida, rollback, notificación nativa,
migración V11 con respaldo, identidad, frecuencia heredada, ZIP V11 restaurado y reapertura.

El recorrido real con `nbctl sound-check --ui`, Vite y KWin virtual comprobó diario→semanal
sin recarga, mensual desde la ventana y notificación de vuelta, respuesta perdida tras
escritura y consulta posterior sin reenvío, rechazo no autorizado, enlace cerrado con
comandos nativos operativos y persistencia al reabrir. No se usó la biblioteca real.
La prueba selecciona desde teclado el mismo selector accesible que usa la persona.

El selector admite presentación controlada por el propietario: no adelanta el valor visible
antes de confirmar. La interfaz descarta respuestas antiguas y una indisponibilidad invalida
consultas pendientes. La exportación conserva su sello después de formatear el proyecto.

Recorrido reproducible desde Launcher: `nbctl sound-check <binario-de-Sound>`, con opción
`--ui` para inspector WebKit de desarrollo. Usa exclusivamente datos temporales y arranca
el binario real. No se usa este inspector en producto. Windows/macOS necesitan ejecución
nativa antes de declarar soporte verificado de esta integración.

## Distribución y cierre de esta entrega

La continuación 2.1.3 y sus comprobaciones se registran en
[validación de Launcher](../engineering/validacion-launcher-2.1.3.md). El candidato 2.1.2
no se publicó por un fallo de medición de rendimiento en CI. No se atribuye el
contrato administrado nuevo a los artefactos de 2.1.1.

Publicada [NB Sound 2.1.1](https://github.com/Nate-1296/NB-SOUND/releases/tag/v2.1.1).
La CI de aplicación y la generación de instaladores pasaron en Linux, Windows y macOS.
El manifiesto y las firmas se comprobaron; el paquete Linux distribuido también pasó
las pruebas de enlace, conflicto, entrada inválida, autonomía y persistencia con datos
aislados. El flujo completo con la UI de Launcher continúa validado en Linux; esa
validación no se extiende automáticamente a las otras plataformas.

Las compilaciones, dependencias, datos y procesos temporales creados por estas pruebas
se retiraron después de validar. Los directorios personales y la instalación existente
no se sustituyeron. La release 2.1.1 corresponde al cambio de aplicación; esta anotación
posterior solo actualiza su evidencia de distribución y el estado del proyecto.
