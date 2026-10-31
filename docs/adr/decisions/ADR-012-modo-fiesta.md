# ADR-012: Modelo de confianza y aislamiento del modo fiesta

**Fecha:** 2026-10-31
**Estado:** Propuesto

## Contexto

La iteración F8.5 ([`docs/plan/fase-8-nuevas.md`](../../plan/fase-8-nuevas.md)) propone el **Modo fiesta**: los
invitados presentes en la misma red local escanean un código QR desde el navegador de su teléfono, buscan canciones en
el catálogo del anfitrión y sugieren qué debería sonar a continuación.

A diferencia de NB Sound Mobile ([ADR-005](./ADR-005-contrato-movil.md)), donde el teléfono pertenece al propio usuario,
se empareja una vez mediante TLS con huella fijada (`fingerprint` SHA-256) y tiene permiso para descargar archivos de
audio, sincronizar toda la biblioteca y controlar el reproductor (pausa, volumen, salto, borrado de sesiones), en el
Modo fiesta los clientes son **desconocidos en una red Wi-Fi compartida**:

1. **Los navegadores móviles rechazan certificados autofirmados para páginas web interactivas:** mientras que la app
   nativa de Android verifica el certificado autofirmado por su huella del QR, Safari en iOS y Chrome en Android
   muestran una advertencia de seguridad severa al abrir una URL `https://192.168.x.x:...` con un certificado
   autofirmado no instalado en el almacén del sistema. Para que cualquier invitado entre escaneando un QR sin instalar
   nada, la página del Modo fiesta debe servirse por HTTP en un puerto efímero separado del servidor móvil TLS.
2. **Cualquier dispositivo en la misma subred puede alcanzar el puerto mientras dura la fiesta:** tanto invitados con el
   QR como otros equipos conectados al mismo punto de acceso Wi-Fi.
3. **Riesgos principales:**
   * Acceso no autorizado a los endpoints de sincronización, descarga de archivos de audio o control remoto de NB Sound
     Mobile.
   * Inundación de sugerencias (*spam* de cola), agotamiento de memoria o consultas de búsqueda costosas desde un
     cliente malicioso o bromista.
   * Suplantación de otros invitados o alteración de lo que ya está sonando (saltar la canción en curso, cambiar el
     volumen o vaciar la cola).
   * Exposición accidental de rutas del sistema de archivos, datos personales del historial o claves del anfitrión.
   * Persistencia del servidor abierto cuando la fiesta ya ha terminado.

Por ello, el plan exige un ADR del modelo de confianza aprobado por Nathan antes de escribir una sola línea de código de
F8.5.

## Alternativas consideradas

### Alternativa A: Reutilizar el servidor de NB Sound Mobile (`movil/mod.rs`) con un rol de invitado

Añadir un tipo de token "invitado" al mismo servidor HTTPS que escucha en el puerto `8731..8799` para NB Sound Mobile.

* **Rechazada.** Obliga a los navegadores de los invitados a atravesar la pantalla de bloqueo por certificado TLS
  autofirmado en una IP privada (especialmente intrusiva en iOS/Safari), y mezcla en el mismo router de `axum` las
  rutas de control total y descarga de audio del propietario con las rutas abiertas a desconocidos. Un descuido en un
  *middleware* expondría toda la biblioteca o el control del reproductor.

### Alternativa B: Encolar directamente en la cola de reproducción todo lo que pida cualquier invitado con el QR

El invitado escanea el QR, pulsa una canción y esta entra directamente como "Reproducir a continuación" sin límites por
invitado ni moderación opcional.

* **Rechazada.** Un solo invitado que pulse veinte canciones seguidas secuestra la sesión entera; no hay defensa frente
  a bromas ni forma de distinguir una cola moderada por el anfitrión de una cola automática acotada.

### Alternativa C: Servidor HTTP efímero aislado, con token de sesión de 128 bits, tres únicas rutas de solo lectura/sugerencia, cuotas por cliente y aprobación del anfitrión

Levantar un listener HTTP independiente y efímero únicamente mientras el Modo fiesta esté activo, con un conjunto mínimo
de rutas sin acceso a archivos de audio ni a órdenes de reproducción, protegido por un secreto de sesión en el QR y
cuotas estrictas en memoria.

* **Aceptada.** Separa físicamente la superficie de ataque de los invitados respecto de NB Sound Mobile, funciona en
  cualquier navegador móvil sin instalar certificados ni aplicaciones, e impide por construcción que un invitado
  descargue música, altere el volumen, salte pistas o inunde la cola.

## Decisión

1. **Proceso y puerto separados del servidor móvil:**
   * El Modo fiesta corre en su propio listener `axum` sobre HTTP en un puerto alto efímero distinto del rango de NB
     Sound Mobile (`8731..8799`), y **solo escucha mientras hay una sesión de fiesta activa**. Apagar el Modo fiesta o
     cerrar la aplicación cierra el socket y descarta todo su estado en memoria.
   * Nunca coexiste en el mismo `Router` que `movil::ServidorMovil`.

2. **Autenticación por secreto efímero de sesión + identificador de invitado:**
   * Al iniciar una fiesta se genera con `rand::rngs::OsRng` un token de sesión de 128 bits codificado en URL-safe
     base64 (`22` caracteres), incluido en la URL del QR (`http://<ip-lan>:<puerto>/f/<token_sesion>`).
   * Al abrir la URL, el servidor valida `<token_sesion>` en tiempo constante, entrega la mini-interfaz web estática (un
     único documento HTML+CSS+JS embebido en el binario, sin CDN ni peticiones externas) y emite una cookie `HttpOnly;
     SameSite=Strict` con un identificador aleatorio de invitado.
   * Regenerar el QR o cerrar la fiesta invalida en el acto el `<token_sesion>` anterior y todas las cookies emitidas.

3. **Superficie de red mínima (cuatro rutas, cero archivos de audio):**
   * `GET /f/{token}`: sirve la página web estática de invitado (con `Content-Security-Policy: default-src 'self'`).
   * `GET /api/estado`: devuelve únicamente qué suena ahora (`titulo`, `artista`, `album`, `portadaId`) y la lista de
     sugerencias pendientes/aceptadas de la fiesta. No expone rutas de disco, historial personal, estadísticas de
     escucha ni dispositivos emparejados.
   * `GET /api/buscar?q=<texto>`: busca en el catálogo con FTS5 (`biblioteca::pistas`, máximo 25 resultados, solo
     `id`, `titulo`, `artista`, `album`, `duracionSeg` y miniatura de 64 px).
   * `POST /api/sugerir`: recibe `{ pistaId, aliasOpcional }` (cuerpo máximo de 512 bytes) y registra una sugerencia.
   * `GET /api/portada/{pista_id}`: sirve únicamente la miniatura de 64 px en caché de pistas presentes en la
     biblioteca. Prohibido servir audio (`/api/ tracks/.../download` no existe en este servidor) ni portadas originales.

4. **Límites de abuso y cuotas en memoria:**
   * Máximo de **3 sugerencias pendientes por invitado** (identificado por cookie + IP de origen) y una ventana mínima de
     **10 segundos** entre envíos del mismo invitado/IP.
   * Tope global de **50 sugerencias pendientes** en la sesión de fiesta y **30 peticiones HTTP por minuto por IP**.
   * Ninguna sugerencia escribe en SQLite: la bandeja de sugerencias vive exclusivamente en memoria mientras dura la
     fiesta, evitando escrituras de desconocidos en `nb_sound.sqlite3`.

5. **Control del anfitrión (moderada por defecto, automática opcional):**
   * Por defecto, las sugerencias entran en una bandeja en la vista del anfitrión, quien puede **Aceptar** (la envía a
     `Orden::Agregar { justo_despues: false }`) o **Descartar**, o bloquear a un invitado revoltoso con un clic.
   * El anfitrión puede activar un interruptor explícito **"Aceptar sugerencias automáticamente"** si confía en los
     asistentes; incluso con él activo, las sugerencias solo se añaden al final de la cola (nunca interrumpen la pista
     que suena, ni cambian el volumen, ni tocan el modo DJ).

## Consecuencias

- **Positivas:**
  * Los invitados entran desde cualquier teléfono (iOS o Android) escaneando el QR sin instalar aplicaciones ni aceptar
    advertencias de certificados autofirmados.
  * Un invitado nunca puede descargar archivos de música del anfitrión, leer su historial ni tomar el control del
    reproductor.
  * `nb_sound.sqlite3` no recibe ni una sola escritura procedente de la red durante la fiesta.
  * El contrato de NB Sound Mobile ([ADR-005](./ADR-005-contrato-movil.md)) permanece intacto.
- **Negativas:**
  * El tráfico entre el navegador del invitado y el portátil va por HTTP dentro de la LAN (necesario porque los
    navegadores bloquean HTTPS con certificado autofirmado en IPs locales); por ello por ese canal solo viajan títulos
    públicos de la búsqueda y el `pistaId` sugerido, nunca credenciales del usuario ni archivos de audio.
- **Riesgos y cómo se vigilan:**
  * *Riesgo:* que un invitado comparta la URL del QR o borre sus cookies para esquivar el límite de 3 sugerencias.
    *Mitigación:* la cuota se aplica tanto por cookie como por dirección IP de origen, el anfitrión tiene el modo
    moderado por defecto y un botón para rotar el token del QR en el acto.
  * *Riesgo:* que el servidor quede encendido por olvido al terminar la reunión. *Mitigación:* indicador permanente en
    la barra superior mientras el Modo fiesta está activo y apagado automático tras 2 horas sin sugerencias ni
    reproducción.
