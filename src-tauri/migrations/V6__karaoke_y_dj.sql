-- V6: karaoke y DJ Privado (F1.1.6).
--
-- Destino de cada columna de la V1: docs/engineering/migracion-v1.md.

-- Los stems de cada pista. La V1 repartía este estado entre cinco columnas de
-- `pistas` y la tabla de trabajos; aquí hay una fila por pista que tiene, o
-- espera, su instrumental. Una pista sin fila no se ha pedido nunca.
CREATE TABLE stems (
    pista_id       INTEGER PRIMARY KEY REFERENCES pistas (id) ON DELETE CASCADE,
    estado         TEXT    NOT NULL DEFAULT 'pendiente'
                           CHECK (estado IN ('pendiente', 'separando', 'lista', 'fallida')),
    -- Relativas a la carpeta de stems de la V2. La voz es opcional: la V1 solo
    -- guardaba el instrumental.
    instrumental   TEXT,
    voz            TEXT,
    bytes          INTEGER CHECK (bytes >= 0),
    modelo         TEXT,
    -- El hash del audio separado: si el archivo cambia, el instrumental ya no es suyo.
    sha256         TEXT    CHECK (sha256 IS NULL OR length(sha256) = 64),
    intentos       INTEGER NOT NULL DEFAULT 0 CHECK (intentos >= 0),
    error          TEXT,
    solicitada_en  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    terminada_en   TEXT,
    -- Una lista tiene su instrumental; ninguna otra lo dice tener.
    CHECK ((estado = 'lista') = (instrumental IS NOT NULL))
) STRICT;

-- La cola de separación: las pendientes, por orden de petición. Y el filtro
-- "Listas para cantar" de Biblioteca.
CREATE INDEX stems_por_estado ON stems (estado, solicitada_en);

-- Que una pista tenga instrumental es un cambio que el móvil descarga (la V1
-- subía la versión de la pista al terminar la separación, `karaoke/jobs_repo.py`).
CREATE TRIGGER stems_sync_al_cambiar AFTER UPDATE OF estado ON stems
WHEN (SELECT pausada FROM sincronizacion) = 0
     AND (OLD.estado = 'lista') <> (NEW.estado = 'lista')
BEGIN
    UPDATE sincronizacion SET version = version + 1;
    UPDATE pistas SET sync_version = (SELECT version FROM sincronizacion) WHERE id = NEW.pista_id;
END;

CREATE TRIGGER stems_sync_al_insertar_lista AFTER INSERT ON stems
WHEN (SELECT pausada FROM sincronizacion) = 0 AND NEW.estado = 'lista'
BEGIN
    UPDATE sincronizacion SET version = version + 1;
    UPDATE pistas SET sync_version = (SELECT version FROM sincronizacion) WHERE id = NEW.pista_id;
END;

CREATE TRIGGER stems_sync_al_borrar_lista AFTER DELETE ON stems
WHEN (SELECT pausada FROM sincronizacion) = 0 AND OLD.estado = 'lista'
BEGIN
    UPDATE sincronizacion SET version = version + 1;
    UPDATE pistas SET sync_version = (SELECT version FROM sincronizacion) WHERE id = OLD.pista_id;
END;

CREATE TABLE dj_sesiones (
    id                INTEGER PRIMARY KEY,
    -- Lo que pidió el usuario, con sus palabras.
    peticion          TEXT    NOT NULL,
    -- JSON: cómo la interpretó el DJ.
    intencion         TEXT    NOT NULL DEFAULT '{}' CHECK (json_valid(intencion)),
    objetivo_minutos  INTEGER NOT NULL DEFAULT 60 CHECK (objetivo_minutos > 0),
    estado            TEXT    NOT NULL DEFAULT 'construyendo' CHECK (estado <> ''),
    motor_version     TEXT    NOT NULL,
    semilla           INTEGER,
    notas             TEXT,
    resumen           TEXT    NOT NULL DEFAULT '{}' CHECK (json_valid(resumen)),
    -- La playlist en la que se guardó, si el usuario la guardó.
    playlist_id       INTEGER REFERENCES playlists (id) ON DELETE SET NULL,
    creada_en         TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    actualizada_en    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    terminada_en      TEXT
) STRICT;

-- El historial del DJ, de la más reciente a la más antigua.
CREATE INDEX dj_sesiones_por_fecha ON dj_sesiones (creada_en);

-- Las pistas de una sesión, en su orden, con las puntuaciones que explican por
-- qué el DJ eligió cada una.
CREATE TABLE dj_sesion_pistas (
    sesion_id           INTEGER NOT NULL REFERENCES dj_sesiones (id) ON DELETE CASCADE,
    posicion            INTEGER NOT NULL CHECK (posicion >= 0),
    pista_id            INTEGER NOT NULL REFERENCES pistas (id) ON DELETE CASCADE,
    puntuacion          REAL    NOT NULL DEFAULT 0,
    puntuacion_intencion REAL   NOT NULL DEFAULT 0,
    puntuacion_transicion REAL  NOT NULL DEFAULT 0,
    puntuacion_curva    REAL    NOT NULL DEFAULT 0,
    razones             TEXT    NOT NULL DEFAULT '[]' CHECK (json_valid(razones)),
    transicion          TEXT    NOT NULL DEFAULT '{}' CHECK (json_valid(transicion)),
    estado              TEXT    NOT NULL DEFAULT 'planificada' CHECK (estado <> ''),
    -- El usuario la fijó: el DJ no la sustituye al replanificar.
    bloqueada           INTEGER NOT NULL DEFAULT 0 CHECK (bloqueada IN (0, 1)),
    fundido_en_seg      REAL    CHECK (fundido_en_seg >= 0),
    agregada_en         TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (sesion_id, posicion)
) STRICT, WITHOUT ROWID;

-- La cascada al borrar una pista, y "¿en qué sesiones sonó?".
CREATE INDEX dj_sesion_pistas_por_pista ON dj_sesion_pistas (pista_id);

-- Lo que hizo el usuario durante una sesión (saltar, repetir, "no me gusta"):
-- el DJ lo usa para no volver a proponer lo rechazado.
CREATE TABLE dj_eventos (
    id         INTEGER PRIMARY KEY,
    sesion_id  INTEGER NOT NULL REFERENCES dj_sesiones (id) ON DELETE CASCADE,
    pista_id   INTEGER REFERENCES pistas (id) ON DELETE SET NULL,
    tipo       TEXT    NOT NULL CHECK (tipo <> ''),
    datos      TEXT    NOT NULL DEFAULT '{}' CHECK (json_valid(datos)),
    creado_en  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT;

-- Los eventos de una sesión, en orden, y los de un tipo dentro de ella.
CREATE INDEX dj_eventos_por_sesion ON dj_eventos (sesion_id, tipo, creado_en);
CREATE INDEX dj_eventos_por_pista ON dj_eventos (pista_id);

-- Una sola fila: dónde va la sesión que está sonando. La V1 lo guardaba en seis
-- claves de `config_ui`.
CREATE TABLE dj_en_curso (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    sesion_id        INTEGER REFERENCES dj_sesiones (id) ON DELETE SET NULL,
    indice           INTEGER CHECK (indice >= 0),
    posicion_seg     REAL    NOT NULL DEFAULT 0 CHECK (posicion_seg >= 0),
    -- La posición dentro de la sesión entera, que no es la suma de las pistas
    -- cuando hay fundidos.
    posicion_global_seg REAL NOT NULL DEFAULT 0 CHECK (posicion_global_seg >= 0),
    volumen          REAL    NOT NULL DEFAULT 1 CHECK (volumen BETWEEN 0 AND 1)
) STRICT;

INSERT INTO dj_en_curso (id) VALUES (1);

CREATE TABLE dj_preferencias (
    clave           TEXT PRIMARY KEY CHECK (clave <> ''),
    valor           TEXT NOT NULL CHECK (json_valid(valor)),
    actualizada_en  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT, WITHOUT ROWID;
