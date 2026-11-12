# ADR-014: renovación privada del enlace de Launcher

**Fecha:** 2026-11-12
**Estado:** Decisión de implementación bajo la continuación y publicación autorizadas por
Nathan desde NB Launcher; implementado y comprobado en Linux. Amplía ADR-013 sin modificar
dominio ni móvil. Publicación y otras plataformas se registran en la validación de 2.1.3.

## Contexto

El host y el puerto de Sound caducan de forma independiente tras 15 minutos. La conexión
autorizada pierde disponibilidad aunque la persona siga usando ambas aplicaciones.

## Alternativas

- Quitar la caducidad permite usar credenciales hasta cerrar el proceso: rechazado.
- Permitir renovar con la credencial de un cliente amplía su autoridad: rechazado.
- Reiniciar Sound para renovar interrumpe su funcionamiento: rechazado.
- Renovar solo el host mantiene la caducidad del propietario: insuficiente.

## Decisión

Incorporar una exportación nueva y sellada de `nb-protocol`/`nb-capability`, generada desde
su fuente canónica de Launcher. El `hello` 2 anuncia soporte de renovación por la tubería
privada heredada del supervisor; el `hello` 1 continúa operativo para clientes anteriores.
El registro y los permisos por operación siguen en Launcher.

Tras el bootstrap se aceptan frames `{"method":"renew"}` solo por stdin privado. Cada
frame completo válido extiende la vigencia 900 segundos. EOF, control inválido o falta de
renovación cierran el enlace y sus sesiones sin terminar Sound. Un frame incompleto no
extiende el plazo. Ningún cliente del puerto puede renovar ni ampliar permisos.

No cambia la frecuencia, su revisión, la persistencia, las copias, el motor de audio ni
el contrato móvil. No se añade dependencia de ejecución. `tokio/test-util` se utiliza
únicamente en las pruebas de la biblioteca para verificar los límites de tiempo.

## Consecuencias y validación

Launcher puede mantener un enlace consentido sin reiniciar Sound. Una suspensión que
agote la vigencia exige una nueva conexión; la autorización no sobrevive al supervisor.
No se implementa adhesión a una instancia abierta por separado ni NB Mesh.

El bundle no se edita a mano. Pasarán verificación de integridad, guardianes, frontend,
fmt, Clippy, pruebas Rust y contrato móvil antes de publicar. La comprobación de un
enlace real superior a 15 minutos se registra aparte de las pruebas con reloj controlado.
