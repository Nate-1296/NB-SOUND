-- V5: la sincronización con NB Sound Mobile (F1.1.5).
--
-- Contrato: docs/engineering/contrato-movil.md y ADR-005. El móvil pide "lo que
-- cambió desde la versión N", así que cada cambio visible para él tiene que subir
-- la `sync_version` de su fila, y cada borrado tiene que dejar una tumba.
--
-- La V1 lo hacía a mano: cada servicio llamaba a `marcar_sync_version` después de
-- escribir, en 15 sitios, y un sitio que lo olvidaba dejaba al teléfono con datos
-- viejos para siempre. Aquí lo hacen **disparadores**: ningún camino de escritura
-- puede olvidarlo, tampoco las acciones de las claves foráneas (borrar un álbum
-- anula el `album_id` de sus pistas, y eso también sube su versión).

-- Una sola fila: el contador global y el interruptor del importador.
CREATE TABLE sincronizacion (
    id       INTEGER PRIMARY KEY CHECK (id = 1),
    -- Monótono. Tras importar la V1 vale lo mismo que su `sync_version_actual`,
    -- para que el siguiente cambio de la V2 sea mayor que todo lo que el móvil vio.
    version  INTEGER NOT NULL DEFAULT 0 CHECK (version >= 0),
    -- 1 solo mientras el importador copia la V1: sus filas traen ya su
    -- `sync_version` y no pueden recibir una nueva, o el móvil volvería a
    -- descargar la biblioteca entera.
    pausada  INTEGER NOT NULL DEFAULT 0 CHECK (pausada IN (0, 1))
) STRICT;

INSERT INTO sincronizacion (id) VALUES (1);

CREATE TABLE tumbas (
    id            INTEGER PRIMARY KEY,
    entidad       TEXT    NOT NULL CHECK (entidad IN ('pista', 'album', 'artista', 'playlist')),
    entidad_id    INTEGER NOT NULL,
    sync_version  INTEGER NOT NULL CHECK (sync_version > 0),
    creada_en     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT;

-- El manifiesto móvil: las tumbas desde una versión.
CREATE INDEX tumbas_por_sync_version ON tumbas (sync_version);

CREATE TABLE dispositivos (
    id                   INTEGER PRIMARY KEY,
    -- El SHA-256 del `device_token`, no el token: quien lea la base no puede
    -- hacerse pasar por el teléfono. El móvil no nota nada, porque el servidor
    -- calcula el hash del token que recibe y lo busca aquí. La V1 los guardaba en
    -- claro.
    token_sha256         TEXT    NOT NULL UNIQUE CHECK (length(token_sha256) = 64),
    nombre               TEXT    NOT NULL,
    plataforma           TEXT,
    ultima_conexion      TEXT,
    ultima_sync_version  INTEGER NOT NULL DEFAULT 0 CHECK (ultima_sync_version >= 0),
    -- JSON: qué artistas o playlists sincroniza este teléfono; nula si todo.
    seleccion            TEXT    CHECK (seleccion IS NULL OR json_valid(seleccion)),
    creado_en            TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    -- Un teléfono quitado se conserva revocado: su token tiene que seguir
    -- rechazándose, y borrarlo lo convertiría en desconocido.
    revocado             INTEGER NOT NULL DEFAULT 0 CHECK (revocado IN (0, 1))
) STRICT;

CREATE TABLE transferencias_stems (
    dispositivo_id  INTEGER NOT NULL REFERENCES dispositivos (id) ON DELETE CASCADE,
    pista_id        INTEGER NOT NULL REFERENCES pistas (id) ON DELETE CASCADE,
    -- Los valores de la V1, que el móvil envía tal cual.
    estado          TEXT    NOT NULL DEFAULT 'pending'
                            CHECK (estado IN ('pending', 'in_progress', 'done', 'failed')),
    bytes_enviados  INTEGER NOT NULL DEFAULT 0 CHECK (bytes_enviados >= 0),
    actualizada_en  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (dispositivo_id, pista_id)
) STRICT, WITHOUT ROWID;

CREATE INDEX transferencias_por_pista ON transferencias_stems (pista_id);

-- Los disparadores. Cada `UPDATE OF` enumera solo las columnas que el contrato
-- móvil envía: que suban las reproducciones de una pista no es un cambio que el
-- teléfono tenga que descargar. Al poner una columna nueva en el manifiesto hay
-- que añadirla aquí; cuando el manifiesto exista (F3.1), una prueba comparará las
-- dos listas.

-- Pistas.
CREATE TRIGGER pistas_sync_al_insertar AFTER INSERT ON pistas
WHEN (SELECT pausada FROM sincronizacion) = 0
BEGIN
    UPDATE sincronizacion SET version = version + 1;
    UPDATE pistas SET sync_version = (SELECT version FROM sincronizacion) WHERE id = NEW.id;
END;

CREATE TRIGGER pistas_sync_al_cambiar AFTER UPDATE OF
    titulo, artista_nombre, album_titulo, album_id, artista_id, numero, duracion_seg,
    anio, genero, isrc, mbid_grabacion, favorita, favorita_actualizada_en, sha256, estado
ON pistas
WHEN (SELECT pausada FROM sincronizacion) = 0
BEGIN
    UPDATE sincronizacion SET version = version + 1;
    UPDATE pistas SET sync_version = (SELECT version FROM sincronizacion) WHERE id = NEW.id;
END;

CREATE TRIGGER pistas_sync_al_borrar AFTER DELETE ON pistas
WHEN (SELECT pausada FROM sincronizacion) = 0
BEGIN
    UPDATE sincronizacion SET version = version + 1;
    INSERT INTO tumbas (entidad, entidad_id, sync_version)
    VALUES ('pista', OLD.id, (SELECT version FROM sincronizacion));
END;

-- Álbumes.
CREATE TRIGGER albumes_sync_al_insertar AFTER INSERT ON albumes
WHEN (SELECT pausada FROM sincronizacion) = 0
BEGIN
    UPDATE sincronizacion SET version = version + 1;
    UPDATE albumes SET sync_version = (SELECT version FROM sincronizacion) WHERE id = NEW.id;
END;

CREATE TRIGGER albumes_sync_al_cambiar AFTER UPDATE OF titulo, artista_id, tipo, anio, portada_id
ON albumes
WHEN (SELECT pausada FROM sincronizacion) = 0
BEGIN
    UPDATE sincronizacion SET version = version + 1;
    UPDATE albumes SET sync_version = (SELECT version FROM sincronizacion) WHERE id = NEW.id;
END;

CREATE TRIGGER albumes_sync_al_borrar AFTER DELETE ON albumes
WHEN (SELECT pausada FROM sincronizacion) = 0
BEGIN
    UPDATE sincronizacion SET version = version + 1;
    INSERT INTO tumbas (entidad, entidad_id, sync_version)
    VALUES ('album', OLD.id, (SELECT version FROM sincronizacion));
END;

-- Artistas.
CREATE TRIGGER artistas_sync_al_insertar AFTER INSERT ON artistas
WHEN (SELECT pausada FROM sincronizacion) = 0
BEGIN
    UPDATE sincronizacion SET version = version + 1;
    UPDATE artistas SET sync_version = (SELECT version FROM sincronizacion) WHERE id = NEW.id;
END;

CREATE TRIGGER artistas_sync_al_cambiar AFTER UPDATE OF nombre, imagen_id ON artistas
WHEN (SELECT pausada FROM sincronizacion) = 0
BEGIN
    UPDATE sincronizacion SET version = version + 1;
    UPDATE artistas SET sync_version = (SELECT version FROM sincronizacion) WHERE id = NEW.id;
END;

CREATE TRIGGER artistas_sync_al_borrar AFTER DELETE ON artistas
WHEN (SELECT pausada FROM sincronizacion) = 0
BEGIN
    UPDATE sincronizacion SET version = version + 1;
    INSERT INTO tumbas (entidad, entidad_id, sync_version)
    VALUES ('artista', OLD.id, (SELECT version FROM sincronizacion));
END;

-- Playlists, y su contenido: el móvil recibe `pista_ids` dentro de la playlist,
-- así que añadir, quitar o reordenar una pista es un cambio de la playlist.
CREATE TRIGGER playlists_sync_al_insertar AFTER INSERT ON playlists
WHEN (SELECT pausada FROM sincronizacion) = 0
BEGIN
    UPDATE sincronizacion SET version = version + 1;
    UPDATE playlists SET sync_version = (SELECT version FROM sincronizacion) WHERE id = NEW.id;
END;

CREATE TRIGGER playlists_sync_al_cambiar AFTER UPDATE OF
    nombre, descripcion, tipo, subtipo, origen, clave_auto, anclada, visible
ON playlists
WHEN (SELECT pausada FROM sincronizacion) = 0
BEGIN
    UPDATE sincronizacion SET version = version + 1;
    UPDATE playlists SET sync_version = (SELECT version FROM sincronizacion) WHERE id = NEW.id;
END;

CREATE TRIGGER playlists_sync_al_borrar AFTER DELETE ON playlists
WHEN (SELECT pausada FROM sincronizacion) = 0
BEGIN
    UPDATE sincronizacion SET version = version + 1;
    INSERT INTO tumbas (entidad, entidad_id, sync_version)
    VALUES ('playlist', OLD.id, (SELECT version FROM sincronizacion));
END;

CREATE TRIGGER playlist_pistas_sync_al_insertar AFTER INSERT ON playlist_pistas
WHEN (SELECT pausada FROM sincronizacion) = 0
BEGIN
    UPDATE sincronizacion SET version = version + 1;
    UPDATE playlists SET sync_version = (SELECT version FROM sincronizacion)
    WHERE id = NEW.playlist_id;
END;

CREATE TRIGGER playlist_pistas_sync_al_reordenar AFTER UPDATE OF posicion ON playlist_pistas
WHEN (SELECT pausada FROM sincronizacion) = 0
BEGIN
    UPDATE sincronizacion SET version = version + 1;
    UPDATE playlists SET sync_version = (SELECT version FROM sincronizacion)
    WHERE id = NEW.playlist_id;
END;

CREATE TRIGGER playlist_pistas_sync_al_borrar AFTER DELETE ON playlist_pistas
WHEN (SELECT pausada FROM sincronizacion) = 0
BEGIN
    UPDATE sincronizacion SET version = version + 1;
    UPDATE playlists SET sync_version = (SELECT version FROM sincronizacion)
    WHERE id = OLD.playlist_id;
END;
