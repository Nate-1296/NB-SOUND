# ADR-009: Configuración mínima, secretos en el llavero y una sola puerta de red

**Fecha:** 2026-10-29
**Estado:** Aceptado

## Contexto

La V1 se configura con más de 100 variables en `.env` (`SECOND_STAGE_MIN_GAP`, `AUDIO_INTELLIGENCE_BACKGROUND_BATCH_SIZE`,
`NB_SOUND_PROGRESS_MODE`…) y guarda en el mismo archivo, en texto plano, las claves de AcoustID, Anthropic, OpenAI
y TheAudioDB. Sale a la red desde nueve clientes distintos en `external/` y `core/`.

## Decisión

1. **Tres clases de valor:**
   * **Constantes de producto** (umbrales de puntuación, tamaños de lote, reintentos, tiempos de espera): constantes
     en Rust con su motivo en un comentario. No son configurables.
   * **Preferencias del usuario**: solo las que aparecen en Ajustes ([ADR-007](./ADR-007-arquitectura-de-informacion.md)),
     guardadas en la base como en el ADR-010 de NB Books.
   * **Secretos**: en el llavero del sistema operativo con `keyring` 4, como `secrets.rs` en NB Books. Nunca en
     archivos, registros ni respuestas del puente.
2. **Claves de la aplicación**: la clave de cliente de AcoustID es de la aplicación, no del usuario, y viaja en el
   binario, como hace MusicBrainz Picard. La de TheAudioDB igual. El usuario solo escribe una clave si quiere el
   desempate por IA con su propia cuenta.
3. **Una sola puerta de red** (`net.rs`): toda salida declara servicio y propósito; la puerta comprueba el
   interruptor general y el del servicio. Servicios: AcoustID, MusicBrainz, Cover Art Archive, Shazam, iTunes, LRCLIB,
   lyrics.ovh, Deezer, Wikipedia, TheAudioDB, el proveedor de IA y la descarga de agregados.
4. **Shazam** usa una API no oficial (como `shazamio` en la V1). En Ajustes se presenta con esa advertencia y se
   puede desactivar; la identificación funciona sin él con AcoustID.
5. **Desempate por IA**: opcional y desactivado por defecto. Solo se envían los metadatos de los candidatos, nunca
   audio. Modelo por defecto `claude-haiku-5-5`; el proveedor y el modelo se pueden cambiar.
6. El `.env` de la V1 no se lee. El importador migra sus rutas y sus claves al llavero una vez, con aviso.

## Consecuencias

- **Positivas:** ninguna clave en texto plano; un solo sitio que auditar para la privacidad.
- **Negativas:** desaparece el ajuste fino por variables. Si una constante resulta mal elegida, se cambia en el
  código con su prueba.
- **Riesgos:** que Shazam cambie su API. Afecta a una de varias fuentes, no al producto.
