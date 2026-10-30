-- V4: el análisis de audio, resumido (F1.1.4).
--
-- La regla de ADR-004: lo derivado nunca pesa más que lo que describe. La V1
-- guardaba 1,1 MB por pista de salidas crudas en JSON; aquí el presupuesto es de
-- menos de 16 KB por pista, y lo vigila una prueba (`pruebas_esquema.rs`). Las
-- restricciones de tamaño de abajo son la otra mitad: hacen imposible que una
-- columna crezca sin que alguien cambie esta migración.
--
-- Todo es recalculable desde el audio. Por eso cada tabla guarda la `version` del
-- analizador y el `sha256` del archivo analizado: si cambia cualquiera de los dos,
-- la fila está caducada.

-- Rasgos de señal (el analizador ligero, que la V1 aplicaba a toda la biblioteca).
CREATE TABLE rasgos (
    pista_id          INTEGER PRIMARY KEY REFERENCES pistas (id) ON DELETE CASCADE,
    version           TEXT    NOT NULL,
    sha256            TEXT    CHECK (sha256 IS NULL OR length(sha256) = 64),
    bpm               REAL    CHECK (bpm > 0),
    pulsos            INTEGER CHECK (pulsos >= 0),
    ataques_por_seg   REAL    CHECK (ataques_por_seg >= 0),
    -- Tonalidad y modo como los escribe la V1 (`G#`, `minor`).
    tonalidad         TEXT    CHECK (tonalidad IN
                          ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')),
    modo              TEXT    CHECK (modo IN ('major', 'minor')),
    rms_media         REAL,
    rms_desviacion    REAL,
    sonoridad_aprox   REAL,
    centroide         REAL,
    ancho_banda       REAL,
    caida_espectral   REAL,
    cruces_por_cero   REAL,
    brillo            REAL,
    oscuridad         REAL,
    -- Las aproximaciones por regla que alimentan las listas por ánimo y el DJ.
    bailabilidad      REAL,
    energia           REAL,
    valencia          REAL,
    activacion        REAL,
    agresividad       REAL,
    calma             REAL,
    melancolia        REAL,
    para_concentrarse REAL,
    para_entrenar     REAL,
    para_fiesta       REAL,
    para_la_noche     REAL,
    -- Sonoridad medida con EBU R128 (`ebur128`), para la normalización (F2.1.4).
    -- La V1 nunca la llegó a medir.
    lufs              REAL,
    pico_verdadero    REAL,
    rango_sonoridad   REAL    CHECK (rango_sonoridad >= 0),
    analizado_en      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT;

-- El análisis con modelos (el agregado de ~4 MB: MusiCNN y sus siete cabezas).
CREATE TABLE analisis_profundo (
    pista_id          INTEGER PRIMARY KEY REFERENCES pistas (id) ON DELETE CASCADE,
    version           TEXT    NOT NULL,
    sha256            TEXT    CHECK (sha256 IS NULL OR length(sha256) = 64),
    -- Probabilidades de cada cabeza, de 0 a 1.
    feliz             REAL    CHECK (feliz BETWEEN 0 AND 1),
    triste            REAL    CHECK (triste BETWEEN 0 AND 1),
    relajada          REAL    CHECK (relajada BETWEEN 0 AND 1),
    agresiva          REAL    CHECK (agresiva BETWEEN 0 AND 1),
    fiesta            REAL    CHECK (fiesta BETWEEN 0 AND 1),
    bailable          REAL    CHECK (bailable BETWEEN 0 AND 1),
    activacion        REAL,
    valencia          REAL,
    -- El embedding de MusiCNN promediado sobre la pista, en `f32` little-endian:
    -- 200 dimensiones son 800 bytes. La V1 lo guardaba como texto JSON fotograma a
    -- fotograma. Lo usan el DJ y "parecidas a esta".
    embedding         BLOB    CHECK (embedding IS NULL OR length(embedding) = 4 * dimensiones),
    dimensiones       INTEGER CHECK (dimensiones BETWEEN 1 AND 2048),
    -- JSON con las etiquetas de estilo más probables y su puntuación
    -- (`[["rock", 0.19], …]`), no la distribución entera.
    etiquetas         TEXT    CHECK (etiquetas IS NULL OR (json_valid(etiquetas) AND length(etiquetas) <= 2048)),
    analizado_en      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT;

-- Etiquetas de ambiente (`bailable`, `nocturna`, `triste`…), por regla o por modelo.
CREATE TABLE etiquetas_ambiente (
    pista_id        INTEGER NOT NULL REFERENCES pistas (id) ON DELETE CASCADE,
    etiqueta        TEXT    NOT NULL CHECK (etiqueta <> '' AND length(etiqueta) <= 32),
    fuente          TEXT    NOT NULL CHECK (fuente IN ('basic_rules', 'deep_model')),
    puntuacion      REAL    NOT NULL,
    confianza       REAL    NOT NULL CHECK (confianza BETWEEN 0 AND 1),
    version         TEXT    NOT NULL,
    actualizada_en  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (pista_id, etiqueta, fuente)
) STRICT, WITHOUT ROWID;

-- Las listas por ánimo: "las pistas más nocturnas", de mayor a menor.
CREATE INDEX etiquetas_por_ambiente ON etiquetas_ambiente (etiqueta, puntuacion);

-- El color dominante de cada portada, en `#rrggbb`. Pinta el hueco de la portada
-- mientras la lista virtual no la pide porque se está desplazando rápido
-- (docs/audit/2026-10-29-prototipo-lista.md), y el fondo de la vista de
-- reproducción mientras carga la imagen.
ALTER TABLE portadas ADD COLUMN color TEXT
    CHECK (color IS NULL OR (length(color) = 7 AND color GLOB '#[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]'));
