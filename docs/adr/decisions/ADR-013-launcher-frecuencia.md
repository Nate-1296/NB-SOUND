# ADR-013: frecuencia de respaldo como capacidad compartida

**Fecha:** 2026-11-11
**Estado:** Aceptado por Nathan el 2026-11-11 para implementar la propuesta revisada desde NB Launcher.

## Contexto

Launcher debe consultar y cambiar la frecuencia de respaldo conservando a Sound como único
propietario. Hoy `copia_frecuencia` llama a `copia_seguridad::fijar_frecuencia`, que valida
0/1/7/30 y escribe mediante un helper que abre su propia transacción. La interfaz consulta
al montarse y después de sus acciones; no se suscribe a cambios externos.

La base está en esquema V11. La migración V1 ya crea `instalacion.id_instalacion`, un
identificador persistente de 32 caracteres hexadecimales. No se necesita inventar otra
identidad de instalación. El contrato móvil está congelado y no requiere cambios.

Las bibliotecas Apache 2.0 `nb-protocol` y `nb-capability` de Launcher tienen contrato de
revisión/observación y pruebas SQLite. Una dependencia a la carpeta vecina de Launcher
rompería la compilación de Sound desde un clon independiente.

## Alternativas consideradas

1. **Leer/escribir la base desde Launcher:** rechazado; duplica reglas y elude al propietario.
2. **Copiar la lógica de frecuencia al hub:** rechazado; crea dos implementaciones del dominio.
3. **Envolver el helper actual en otra transacción:** rechazado; abre otra conexión/escritura
   y no puede confirmar preferencia y revisión como una sola operación.
4. **Dependencias a una carpeta vecina:** rechazado para el proyecto integrado; no existen
   en un clon limpio ni en su CI.
5. **Publicar ahora crates o un repositorio remoto:** diferido; requiere infraestructura y
   publicación que no son necesarias para validar esta primera integración.
6. **Exportación inmutable y reproducible de bibliotecas compartidas:** elegida para esta
   etapa. Una sola fuente canónica, dependencias fijadas por contenido, actualización
   explícita y clon de Sound autosuficiente. No son copias editables de código de producto.

## Decisión

### Propiedad y persistencia

Sound conserva validador, preferencias, ejecución automática, carpeta, retención y formato
de respaldo. La capacidad expone únicamente la frecuencia. Los demás campos de `EstadoCopia`
no forman parte de su revisión ni se envían al hub como efecto de consultar esa frecuencia.

Se añade V12, la siguiente migración libre al aceptar esta decisión:

```sql
CREATE TABLE revision_de_recursos (
    recurso TEXT PRIMARY KEY,
    secuencia INTEGER NOT NULL CHECK (secuencia BETWEEN 0 AND 9007199254740991)
) STRICT;

INSERT INTO revision_de_recursos (recurso, secuencia) VALUES ('copia_frecuencia', 0);
```

La preferencia `copia_cada_dias` no se mueve ni se duplica. Una escritura compara la
secuencia, valida usando la lógica de Sound y confirma preferencia/contador en una misma
`BEGIN IMMEDIATE`. La lectura obtiene ambos de una instantánea coherente. No se usa
`actualizada_en` como reloj de revisión. Se preserva la lectura heredada de `1.0`.

La época de autoridad vive en memoria y se genera al abrir la app, después de aplicar
una restauración pendiente. No se guarda ni se recupera desde el respaldo.

### Biblioteca compartida y compilación independiente

Incorporar una exportación sellada en `src-tauri/vendor/nb-shared`, generada desde Launcher,
con fuente, manifiesto de hashes, licencia y verificador autosuficiente. Las dependencias
de Sound apuntan dentro de ese directorio, nunca fuera del repositorio. Su Cargo.lock
fija la resolución de dependencias. Los archivos exportados no se editan a mano.

El origen canónico sigue siendo Launcher. `shared-export.mjs --check` compara la exportación
con ese origen durante su preparación; el verificador incluido comprueba el inventario y
hashes sin necesitar Launcher en la CI de Sound. El hash no es una firma ni reemplaza la
revisión de procedencia. Las actualizaciones cambian explícitamente el identificador del
bundle y pasan la verificación de ambos proyectos.

Estas bibliotecas Apache se incorporan en Sound bajo las obligaciones de distribución de
su GPL, manteniendo las licencias/avisos correspondientes. Sound no cambia de licencia.

### API nativa, actualización y enlace con Launcher

Compartir una instancia del recurso entre el comando Tauri y el adaptador externo. La
interfaz envía la revisión que está mostrando y recibe aplicado/sin cambios/conflicto.
Ante conflicto adopta el estado confirmado y explica que cambió desde otro control.
No reintenta silenciosamente una edición antigua.

Generar los DTO/bindings del puente según las reglas actuales de Sound y publicar cambios
después del commit. La pantalla abierta escucha las notificaciones y reconcilia al
reconectar. Estado de respaldo y selección de carpeta mantienen sus flujos actuales.

El registro externo requiere autorización para esta capacidad concreta. Identidad de app
declarada, ID de instalación y revisión no acreditan permiso. No se habilita acceso a
otras preferencias, archivos, reproducción ni restauración por conceder frecuencia.

El arranque independiente sigue sin necesitar Launcher. La pérdida del host solo detiene
el enlace. El enlace debe iniciarse explícitamente y recibir credenciales por un canal
privado, sin secretos en argv, entorno, disco ni logs. El stdout de depuración de Sound
ya contiene registros: no puede reutilizarse como stream de respuestas del protocolo.
El adaptador y su negociación se deben verificar antes de habilitarlo por defecto.

## Consecuencias e impacto

- **Positivas:** una sola lógica, cambios bidireccionales, conflictos explícitos, historial
  de decisiones y clon independiente de Sound.
- **Negativas:** nueva migración, metadatos de revisión y actualización coordinada del
  puente/interfaz; exportación fijada que debe actualizarse explícitamente.
- **Compatibilidad:** no se cambia el contrato móvil ni el formato ZIP. Una copia antigua
  debe migrar mediante el mecanismo existente. Como con cualquier migración, el binario
  anterior rechazará una base V12; no se promete downgrade del archivo sin restaurar la
  copia previa de migración. Este impacto debe figurar en la documentación de Sound.
- **Riesgos vigilados:** actualización sin revisión, notificación antes de persistir,
  dependencia a checkout externo, deriva del bundle, logs mezclados con IPC y uso de datos
  reales durante verificación. Se prueban expresamente.

## Criterios para dar por terminada la integración

1. Migración V11→V12 conserva preferencias/datos y respaldo previo; copia anterior restaurada
   migra correctamente. Todas las pruebas usan rutas temporales.
2. El propietario real de Sound confirma preferencia/revisión juntos y rechaza valores fuera
   de 0/1/7/30. Dos cambios desde la misma revisión no se sobrescriben.
3. Cambio nativo y cambio del hub usan la misma instancia, validador y publicación.
4. La ventana abierta refleja el cambio sin recarga; reconectar recupera estado confirmado.
5. Timeout tras commit no causa reenvío ciego y una reapertura invalida revisiones anteriores.
6. Sound funciona sin Launcher y conserva respaldos, audio y móvil al perder el enlace.
7. Clon independiente compila y verifica el bundle sin carpetas vecinas.
8. Pasan `pnpm verify`, fmt, Clippy y pruebas Rust requeridos por Sound. La prueba real entre
   procesos y la verificación de ventana se registran aparte de las pruebas de simulación.

No se publica una versión ni se modifica Sound Mobile como parte de esta aprobación.
