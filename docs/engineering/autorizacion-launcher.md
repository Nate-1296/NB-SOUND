# Autorización persistente de Launcher

Fecha: 2026-11-13. Estado: publicada en 2.1.4 e instalada en Linux; recorrido real y
verificación local/CI completos. [Informe final](validacion-launcher-2.1.4.md).
[Decisión ADR-017](../adr/decisions/ADR-017-autorizacion-persistente-launcher.md).

## Flujo y autoridad

Sound mantiene un bloqueo de su perfil antes de restaurar/abrir la base. El enlace nuevo
publica únicamente un anuncio operativo privado y comprueba UID/PID y desafío criptográfico.
La identidad cliente pertenece a `nb-service`; sus firmas incluyen recurso, permisos y
participantes. Activar la ventana y autorizar el recurso son operaciones diferentes.

La solicitud aparece en Sound después de verificar posesión. Espera hasta 45 segundos y
desaparece al cancelar/cerrar Launcher. El foco inicial está en Cancelar. Aceptar deshabilita
acciones mientras confirma persistencia; el puente espera el commit. No se envían claves
privadas al webview. Un fallo al guardar no se presenta como autorización guardada.

En Ajustes → Privacidad se consulta el número confirmado de autorizaciones recordadas y
se revocan. La revocación general incrementa una generación y cierra las sesiones después
del commit; una respuesta de un diálogo anterior no puede recuperar el permiso. Permitir
solicitudes de nuevo conserva revisiones y exige consentimiento nuevo; no recupera permisos.

El bootstrap heredado solo se admite mientras el perfil no tenga ninguna decisión
persistente de autorización. La primera concesión o revocación lo cierra y bloquea
en las aperturas siguientes, incluso tras restaurar otra instalación de biblioteca.
Permitir solicitudes nuevas no elimina ese bloqueo: exige el canal autenticado. Una
escritura ya admitida antes del commit puede terminar; cada operación posterior
comprueba la política revocable. Un fallo al abrir el registro no habilita el enlace
heredado. Los clientes antiguos necesitan actualizarse después de esa primera decisión.
La adhesión nueva está habilitada en Linux; no se atribuye ejecución nativa a
Windows/macOS. Un binario 2.1.3 anterior no respeta el bloqueo nuevo: cerrarlo antes de
actualizar. La instalación administrada conserva su exclusión de binarios en uso.

## Almacenamiento y respaldo

`autorizaciones-launcher.sqlite3` vive en los datos propios, separado de la biblioteca y
excluido del ZIP. Esquema local inicial 1, sin cambiar el V12 de la biblioteca. Guarda
instalación/recurso, claves públicas, ámbitos, revisiones, generación y tumbas. No contiene
credenciales de sesión. Escrituras inmediatas, permisos de archivo privados y un bloqueo
exclusivo independiente impiden dos autoridades del registro. No se reemplazan inodes de bloqueo.

Restaurar biblioteca no cambia el registro de confianza. Otro perfil restaurado sin él
vuelve a pedir permiso. Los anuncios no contienen rutas personales; sus perfiles son opacos.
Un fallo del enlace no sustituye el reproductor ni afecta al protocolo móvil.

## Evidencia local y pendiente

Con Rust/Cargo 1.99.1, revisión Arch `-4` aislada tras una actualización del sistema,
pasaron once pruebas de `autorizacion_launcher`: denegar/aceptar, continuidad, separación
de ámbito/instalación, revocación activa y persistente, diálogo antiguo, nueva solicitud,
exclusión, error de escritura, rechazo de enlaces y bloqueo heredado persistente.
Otra prueba comprueba que la primera decisión cierre un puerto heredado activo sin
cambiar el valor ni la revisión del recurso. Pasó también `autorizacion_respaldo`
con el código real de backup: revocar, restaurar, comprobar frecuencia restaurada y permiso
revocado; restaurar en otro perfil requiere consentimiento. Son fixtures, no apps registradas.

Se generan los nuevos bindings con ts-rs. Frontend y guardianes se ejecutan antes de dar
por terminado el candidato; se mantiene el presupuesto inicial de 250 KB. El recorrido de dos procesos y sus ventanas pasó: rechazo, consentimiento, cambios
bidireccionales, reconexión recordada, reinicio de Launcher con el llavero real, revocación
activa y tras reiniciar Sound, permiso nuevo, cancelación, segunda apertura y arranque
desde Launcher. Se retiraron las identidades QA propias sin leer secretos.
La publicación e instalación siguen pendientes. No se publica
un candidato fallido ni se cambian móvil, claves editoriales o reglas del respaldo.

## Cierre local del candidato

`pnpm verify` terminó con `VITEST_MAX_WORKERS=1`: lint, tipos sin errores/advertencias,
38 pruebas, todos los guardianes y búsqueda aislada de 100.000 pistas bajo 30 ms.
La primera ejecución paralela tuvo tres timeouts de creación de workers; no se
amplió el límite de rendimiento ni se reintentó una medición fallida.
`cargo fmt --all -- --check`, Clippy de todos los targets/features y `cargo test`
comprobaron el código de la iteración: 667 pruebas Rust y 25 omitidas. El arranque
carga 249,8 KB de 250; 38 importaciones diferidas, 625 KB totales. La versión 2.1.4
identifica el candidato siguiente; la CI y los paquetes no se dan por comprobados
por las validaciones locales de esta misma implementación.

## Ajuste de plataforma antes de publicar

La CI inicial `43516498573` del commit `f7fb051` pasó frontend, dependencias y
licencias. Clippy de macOS y Windows rechazó un campo de confirmación usado solo
por la adhesión Linux. Se acota esa resolución y su receptor a Linux; las otras
plataformas devuelven indisponibilidad sin simular consentimiento. También se
limita el bloqueo nuevo de instancia a Linux, donde existe activación: las otras
plataformas conservan el arranque anterior. Dos pruebas nativas de regresión
comprueban esas condiciones fuera de Linux. La ejecución de esas pruebas y la
CI corregida siguen pendientes. No se etiquetó ni publicó ese checkpoint inicial.

## Cierre publicado

La corrección `fbaede2` pasó la CI `43518196348` en los tres sistemas. La etiqueta
`v2.1.4` corresponde a ese código. Publicación `43518959506` y catálogo editorial
`43523206333` terminaron correctamente. Se verificaron siete firmas y el recorrido
de los paquetes Linux antes de publicar e instalar; los archivos instalados coinciden
con el tar firmado. El estado anterior en este documento es el registro histórico de
la validación. [Resultados, limpieza y límites](validacion-launcher-2.1.4.md).
