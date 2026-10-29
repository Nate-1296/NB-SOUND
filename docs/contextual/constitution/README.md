# Constitución

> **Estado:** Vigente desde el 2026-10-29. Modificable únicamente mediante ADR aceptado.

La filosofía marca una dirección; **la Constitución dicta leyes**. Ningún cambio se integra en `main` si rompe una
de estas reglas. Cada regla dice qué la hace cumplir: una regla sin mecanismo es una intención, y las intenciones
fueron exactamente lo que dejó a la V1 como está.

---

## 1. Si hay que salir de la aplicación para instalar algo, la aplicación está mal hecha

La V1 se diseñó para **usar el entorno al que llegaba**: VLC del sistema, el Python del sistema, `pip` para torch y
Essentia, una vista entera para diagnosticar qué faltaba. NB Books lo resume en su plan como el modo de fallo que
hundió a la aplicación anterior del mismo autor. No se repite.

* Todo lo que la aplicación necesita para reproducir, catalogar, sincronizar y editar **viaja dentro del
  instalador**: motor de audio, decodificadores, `ffmpeg`, la huella acústica y el runtime de inferencia.
* Lo que es grande y opcional (modelos de karaoke y de análisis, aceleración por GPU) es un **agregado**: se
  instala **con un clic desde Ajustes**, se verifica por hash, se puede quitar, y nunca pide una terminal, un
  gestor de paquetes ni un intérprete del sistema ([ADR-006](../../adr/decisions/ADR-006-agregados.md)).
* Ninguna pantalla le explica al usuario qué le falta a su sistema. Si algo falta, es un defecto del empaquetado.

**Mecanismo:** la puerta de empaquetado de cada fase instala en una máquina limpia sin nada más
([plan](../../plan/README.md), sección 5.1), y `check-plataforma` rechaza código que busque binarios en el `PATH`.

## 2. Un solo producto, sin modos

No existe un "modo pro" ni un "modo simple". La aplicación es sencilla por defecto y profunda bajo demanda
(revelación progresiva). Lo que solo entiende quien programa —causas internas de rechazo, colas, rutas auxiliares,
versiones de librerías— **no se muestra**: se registra.

**Mecanismo:** [ADR-007](../../adr/decisions/ADR-007-arquitectura-de-informacion.md) fija los destinos; un
destino nuevo exige un ADR que lo enmiende.

## 3. Lo del usuario es intocable

* La biblioteca, las playlists, el historial, los favoritos, los dispositivos emparejados y los stems ya
  separados **sobreviven a la migración desde la V1** sin pérdida.
* La V2 **nunca escribe** en la base de datos de la V1 ni en la carpeta de música salvo por una acción explícita
  del usuario (organizar, reetiquetar).
* Desinstalar no se lleva la biblioteca.

**Mecanismo:** el importador abre la base V1 en solo lectura y tiene prueba de conservación fila a fila
([ADR-004](../../adr/decisions/ADR-004-datos.md)).

## 4. NB Sound Mobile no se toca

NB Sound Mobile está terminado. La V2 de escritorio es **compatible byte a byte** con su contrato
(`NB_Sound_Mobile/docs/pc-contract.md`, protocolo `1`): mismas rutas, mismos campos, mismo certificado y la misma
huella, los mismos `device_token`, los mismos identificadores de pista. Solo se admiten cambios **aditivos**, que el
cliente ya ignora por diseño.

Modificar la app móvil solo se justifica si mantener el contrato dejara al escritorio peor de lo que podría ser, y
entonces exige un ADR que lo demuestre.

**Mecanismo:** las respuestas doradas grabadas a la V1 se reproducen contra el servidor de la V2 en cada
verificación ([ADR-005](../../adr/decisions/ADR-005-contrato-movil.md)).

## 5. Nada sale del dispositivo sin consentimiento

AcoustID, MusicBrainz, Shazam, iTunes, LRCLIB, Cover Art Archive y el desempate por IA son salidas de red. Cada una
pasa por una única puerta que comprueba el interruptor general y el consentimiento por servicio y propósito. Los
registros no contienen rutas, títulos, artistas ni claves.

**Mecanismo:** `check-network` rechaza el cliente HTTP fuera de `net.rs`; `check-registro` rechaza campos de
registro sin redactar ([ADR-009](../../adr/decisions/ADR-009-configuracion-y-red.md)).

## 6. Un fallo local tiene consecuencias locales

Si falla el karaoke, la música sigue sonando. Si falla la identificación, la pista entra igual y queda marcada
para revisar. Si falla el servidor móvil, el escritorio no se entera. Ningún trabajo pesado comparte hilo con el
audio ni con la ventana.

**Mecanismo:** el audio corre en su propio hilo de tiempo real; ningún comando del puente es síncrono
(`check-comandos`); prueba de carga del motor con todos los núcleos ocupados ([ADR-003](../../adr/decisions/ADR-003-motor-de-audio.md)).

## 7. Un ecosistema, no dos aplicaciones parecidas

NB Sound y NB Books comparten pila, estructura de carpetas, contrato de errores, sistema de diseño, guardianes y
forma de trabajar. Quien sepa moverse en uno se mueve en el otro sin leer nada.

**Mecanismo:** [ADR-001](../../adr/decisions/ADR-001-pila-tecnologica.md); los guardianes se portan de NB Books
con su origen citado.

## 8. La documentación es parte del producto

`docs/` es la fuente única de verdad. Si el código y `docs/` discrepan, hay un defecto. Un cambio con impacto
arquitectónico o de uso no está terminado hasta que su documento lo refleja, en el mismo commit.

**Mecanismo:** `check-docs` comprueba enlaces y etiquetas de estado.
