# ADR-017: autorización persistente local de Launcher

**Fecha:** 2026-11-13
**Estado:** implementación bajo la elección expresa de Nathan de recordar autorizaciones
con revocación persistente y su instrucción de continuar la integración. No se declara
operativa hasta completar sus pruebas reales. Amplía ADR-013/014; no modifica Mobile.

## Contexto y alternativas

El bootstrap heredado solo enlaza un Sound iniciado por Launcher. Una instancia abierta
por separado necesita comprobar identidad, pedir consentimiento y mantener concesiones.
El nombre, la ruta o el PID de un proceso no demuestran continuidad entre sesiones.

- Pedir permiso en cada sesión: Nathan eligió autorización persistente.
- Reutilizar la clave editorial de releases en clientes: rechazado; su autoridad es distinta.
- Guardar la clave privada en un archivo si falla el llavero: rechazado.
- Guardar concesiones en la base de biblioteca respaldada: rechazado; restaurar una copia
  antigua podría recuperar permisos revocados.
- Acceder a la base desde Launcher: rechazado; Sound conserva su autoridad.

## Decisión

Launcher mantiene una identidad Ed25519 por instalación en el llavero del SO. Sound usa
el núcleo Apache 2.0 compartido y sellado para comprobar desafíos de un solo uso, ligados
al recurso, operaciones y PID comprobados por el transporte local. Ed25519 proviene de
`ed25519-dalek` 2.2, dependencia de la feature `attachment`; no se implementa criptografía
propia. La identidad cliente es independiente de Mobile y de la clave editorial.
Los fixtures usan `zeroize` 1.9.1 (ya resuelto por el llavero) solo en desarrollo para
implementar el contrato del almacén simulado. `windows-sys` existente habilita su API
de archivos para rechazar redirecciones del registro local.

Sound conserva un registro SQLite propio `autorizaciones-launcher.sqlite3`, fuera de la
base de biblioteca y de su ZIP de respaldo. Contiene solo claves públicas, ámbitos,
revisiones y revocaciones; ninguna credencial de sesión. La instalación propietaria y
la clave completa de recurso forman parte del ámbito. Todas sus escrituras usan
`BEGIN IMMEDIATE` por la puerta existente de datos. Una biblioteca restaurada no reemplaza
este registro. Si falta, la política vuelve a denegar; no importa concesiones de una copia.

El primer consentimiento se solicita en Sound después de comprobar posesión, con espera
acotada y una solicitud visible pendiente. Aceptar compara la revisión observada al abrir
la solicitud con la actual en una misma transacción; una revocación mientras el diálogo
estaba abierto impide que una respuesta antigua vuelva a autorizar. Denegar no guarda
permisos. Una concesión recordada solo sirve para los ámbitos que todavía permite.
La identidad y el canal privado los mantiene `nb-service`, el proceso de fondo de Launcher
que consulta el puerto. El trabajo administrativo es asíncrono y cancelable. La interfaz de
Launcher no recibe la clave privada ni confirma estado antes del propietario. La respuesta
del puente de Sound al aceptar espera el commit de la concesión.

Revocar conserva una tumba y avisa a todas las sesiones activas de esa concesión después
del commit. Estas cierran puerto, observaciones y renovaciones. Una escritura admitida
antes de revocar puede terminar; la UI reconcilia respuestas perdidas. Cerrar Launcher
termina sus sesiones y conserva la concesión recordada. Sound mantiene audio y uso autónomo.

La instancia única se adquiere antes de restaurar o abrir la biblioteca; una segunda
apertura solicita activación, sin abrir otra autoridad. El anuncio local solo contiene
aplicación, PID, protocolo y endpoint, nunca rutas o datos de biblioteca. Se distingue
descubrimiento de autorización. En Wayland se solicita foco sin prometer forzarlo.
El arranque carga el diálogo de consentimiento únicamente cuando existe una solicitud;
mantiene el presupuesto de JavaScript inicial. La implementación de adhesión/activación
se habilita en Linux. Windows/macOS conservan el enlace heredado y requieren su recorrido
nativo antes de anunciar la adhesión. Al actualizar desde 2.1.3 hay que cerrar el binario
anterior: ese binario publicado todavía no participa del nuevo bloqueo de instancia.

## Riesgos y aceptación

El llavero y los permisos locales no aíslan a un atacante del mismo usuario ni al
administrador. Una pérdida/cambio de clave no rota identidad silenciosamente. Un fallo
del enlace queda localizado y no impide el reproductor. La implementación se habilita
por plataforma según evidencia; una compilación cruzada no acredita ejecución nativa.

Se prueban consentimiento/rechazo, continuidad entre reinicios, clave distinta/perdida,
desafío repetido/vencido, ampliación de ámbitos, revocación durante consentimiento y con
sesiones activas, persistencia, restauración sin recuperar concesiones, fallo de almacenamiento,
instancia única y autonomía. Fixtures y ensayos de biblioteca no sustituyen las dos apps reales.
Antes de publicar pasan guardianes, frontend, fmt, Clippy, Rust, contrato móvil y paquetes.
