-- V3: lo que el usuario hace con su música (F1.1.3).
--
-- Destino de cada columna de la V1: docs/engineering/migracion-v1.md.

CREATE TABLE playlists (
    id                 INTEGER PRIMARY KEY,
    nombre             TEXT    NOT NULL CHECK (nombre <> ''),
    descripcion        TEXT,
    -- Los tres campos que el contrato móvil envía tal cual, con los valores de la V1.
    tipo               TEXT    NOT NULL DEFAULT 'manual'
                               CHECK (tipo IN ('manual', 'automatica', 'sistema')),
    subtipo            TEXT,
    origen             TEXT    NOT NULL DEFAULT 'usuario'
                               CHECK (origen IN ('usuario', 'sistema', 'generado')),
    -- JSON con la regla de una playlist automática.
    regla              TEXT,
    -- Identifica una automática entre regeneraciones (`this_is:12`, `mood:calma`…).
    clave_auto         TEXT    UNIQUE,
    -- Las dos, porque en la V1 hay una anclada sin fecha y el orden de las ancladas
    -- sale de la fecha.
    anclada            INTEGER NOT NULL DEFAULT 0 CHECK (anclada IN (0, 1)),
    anclada_en         TEXT,
    visible            INTEGER NOT NULL DEFAULT 1 CHECK (visible IN (0, 1)),
    generada_en        TEXT,
    auto_actualizable  INTEGER NOT NULL DEFAULT 0 CHECK (auto_actualizable IN (0, 1)),
    -- Una automática que el usuario tocó deja de regenerarse sola.
    editada            INTEGER NOT NULL DEFAULT 0 CHECK (editada IN (0, 1)),
    creada_en          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    actualizada_en     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    sync_version       INTEGER NOT NULL DEFAULT 0 CHECK (sync_version >= 0)
) STRICT;

-- El manifiesto móvil.
CREATE INDEX playlists_por_sync_version ON playlists (sync_version);

-- Una pista aparece una sola vez en cada playlist, como en la V1: el contrato móvil
-- envía `pista_ids` y el móvil no espera repeticiones.
CREATE TABLE playlist_pistas (
    playlist_id  INTEGER NOT NULL REFERENCES playlists (id) ON DELETE CASCADE,
    pista_id     INTEGER NOT NULL REFERENCES pistas (id) ON DELETE CASCADE,
    posicion     INTEGER NOT NULL CHECK (posicion >= 0),
    agregada_en  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (playlist_id, pista_id)
) STRICT, WITHOUT ROWID;

-- Abrir una playlist en su orden.
CREATE INDEX playlist_pistas_en_orden ON playlist_pistas (playlist_id, posicion);
-- Borrar una pista recorre sus playlists por la cascada.
CREATE INDEX playlist_pistas_por_pista ON playlist_pistas (pista_id);

CREATE TABLE historial (
    id               INTEGER PRIMARY KEY,
    pista_id         INTEGER REFERENCES pistas (id) ON DELETE SET NULL,
    -- Sobreviven a que la pista se borre: "Tu música" sigue contando lo escuchado.
    titulo           TEXT,
    artista          TEXT,
    reproducida_en   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    escuchado_seg    REAL    CHECK (escuchado_seg >= 0),
    -- 0 si se saltó: alimenta las recomendaciones y el DJ.
    completada       INTEGER NOT NULL DEFAULT 1 CHECK (completada IN (0, 1))
) STRICT;

-- Recientes, "Continuar escuchando" y el resumen anual: siempre por fecha.
CREATE INDEX historial_por_fecha ON historial (reproducida_en);
-- Las estadísticas de una pista, y la cascada al borrarla.
CREATE INDEX historial_por_pista ON historial (pista_id);

CREATE TABLE cola (
    posicion     INTEGER PRIMARY KEY CHECK (posicion >= 0),
    pista_id     INTEGER NOT NULL REFERENCES pistas (id) ON DELETE CASCADE,
    agregada_en  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT;

CREATE INDEX cola_por_pista ON cola (pista_id);

-- Una sola fila: dónde se quedó el reproductor. La V1 lo repartía entre claves de
-- `config_ui` como texto; aquí cada valor tiene su tipo y su rango.
CREATE TABLE estado_reproductor (
    id             INTEGER PRIMARY KEY CHECK (id = 1),
    pista_id       INTEGER REFERENCES pistas (id) ON DELETE SET NULL,
    posicion_cola  INTEGER CHECK (posicion_cola >= 0),
    posicion_seg   REAL    NOT NULL DEFAULT 0 CHECK (posicion_seg >= 0),
    -- De 0 a 1, la escala del motor; la V1 guardaba de 0 a 100.
    volumen        REAL    NOT NULL DEFAULT 1 CHECK (volumen BETWEEN 0 AND 1),
    aleatorio      INTEGER NOT NULL DEFAULT 0 CHECK (aleatorio IN (0, 1)),
    -- Los valores de la V1, para no traducir nada al importar.
    repeticion     TEXT    NOT NULL DEFAULT 'ninguno' CHECK (repeticion IN ('ninguno', 'todo', 'uno')),
    normalizar     INTEGER NOT NULL DEFAULT 1 CHECK (normalizar IN (0, 1)),
    actualizado_en TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT;

INSERT INTO estado_reproductor (id) VALUES (1);

-- Preferencias del usuario. Clave y valor JSON: son pocas, se leen todas al
-- arrancar, y cada una la valida el servicio que la usa, no la base. Ninguna clave
-- de servicio entra aquí: van al llavero (`secrets.rs`).
CREATE TABLE preferencias (
    clave          TEXT    PRIMARY KEY CHECK (clave <> ''),
    valor          TEXT    NOT NULL CHECK (json_valid(valor)),
    actualizada_en TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT, WITHOUT ROWID;
