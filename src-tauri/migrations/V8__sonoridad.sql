-- V8: la sonoridad de cada pista, medida con EBU R128 para la normalización
-- (F2.1.4). La V1 nunca la llegó a medir.
--
-- No va en `rasgos`: esa tabla es la salida de un analizador con su versión, y la
-- sonoridad la mide la V2 sola, para todas las pistas, en cuanto entran. Una pista
-- sin rasgos tiene que poder tener su sonoridad.

CREATE TABLE sonoridad (
    pista_id        INTEGER PRIMARY KEY REFERENCES pistas (id) ON DELETE CASCADE,
    -- El archivo medido: si cambia, la medida caduca.
    sha256          TEXT    CHECK (sha256 IS NULL OR length(sha256) = 64),
    -- Sin medida posible (silencio, archivo ilegible): se apunta para no volver a
    -- intentarlo en cada arranque, con los tres valores a NULL.
    lufs            REAL,
    pico_verdadero  REAL,
    rango           REAL    CHECK (rango IS NULL OR rango >= 0),
    medida_en       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT, WITHOUT ROWID;

-- El manifiesto móvil envía también `verificada` (F3.1.4, enmienda de ADR-007):
-- importar desde Por revisar y verificar después es un cambio que el teléfono
-- tiene que descargar. El disparador de V5 se rehace con esa columna.
DROP TRIGGER pistas_sync_al_cambiar;

CREATE TRIGGER pistas_sync_al_cambiar AFTER UPDATE OF
    titulo, artista_nombre, album_titulo, album_id, artista_id, numero, duracion_seg,
    anio, genero, isrc, mbid_grabacion, favorita, favorita_actualizada_en, sha256, estado,
    verificada
ON pistas
WHEN (SELECT pausada FROM sincronizacion) = 0
BEGIN
    UPDATE sincronizacion SET version = version + 1;
    UPDATE pistas SET sync_version = (SELECT version FROM sincronizacion) WHERE id = NEW.id;
END;
