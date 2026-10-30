-- V2: el catálogo (F1.1.2).
--
-- Destino de cada columna de la V1: docs/engineering/migracion-v1.md. Los `id` de
-- artistas, álbumes y pistas se conservan tal cual al importar, porque NB Sound
-- Mobile los tiene guardados (ADR-005); por eso ninguna tabla usa AUTOINCREMENT
-- con huecos propios: el siguiente `id` es el mayor más uno, como en la V1.
--
-- Las marcas de tiempo son TEXT. Las de la V1 se copian tal cual, aunque mezclan
-- `2026-05-24 05:45:57` e ISO 8601 con `Z`, porque el móvil recibe algunas
-- (`favorita_actualizada_en`) y compara cadenas. Las nuevas son ISO 8601 en UTC.
--
-- Cada índice dice qué consulta lo pide. Un índice sin consulta es escritura que
-- se paga en cada importación sin que nada lo lea.

-- Portadas e imágenes de artista. Un archivo por contenido (`sha256`): la V1 tenía
-- la misma portada repetida en cada variante y en cada pista del álbum.
CREATE TABLE portadas (
    id       INTEGER PRIMARY KEY,
    sha256   TEXT    NOT NULL UNIQUE CHECK (length(sha256) = 64),
    -- Relativa a la carpeta de portadas de la V2 (`paths.rs`), nunca absoluta.
    ruta     TEXT    NOT NULL,
    ancho    INTEGER NOT NULL CHECK (ancho > 0),
    alto     INTEGER NOT NULL CHECK (alto > 0),
    bytes    INTEGER NOT NULL CHECK (bytes > 0),
    mime     TEXT    NOT NULL CHECK (mime IN ('image/jpeg', 'image/png', 'image/webp')),
    -- De dónde salió: la etiqueta del archivo, un servicio con su nombre o la V1.
    origen   TEXT    NOT NULL,
    creada_en TEXT   NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT;

CREATE TABLE artistas (
    id             INTEGER PRIMARY KEY,
    nombre         TEXT    NOT NULL CHECK (nombre <> ''),
    -- La clave de unicidad: el nombre normalizado. Las de la V1 se copian tal cual
    -- (`nombre_slug`) y las nuevas siguen la misma regla, para que importar dos
    -- veces el mismo artista no dé dos filas.
    clave          TEXT    NOT NULL UNIQUE CHECK (clave <> ''),
    mbid           TEXT,
    imagen_id      INTEGER REFERENCES portadas (id) ON DELETE SET NULL,
    creado_en      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    sync_version   INTEGER NOT NULL DEFAULT 0 CHECK (sync_version >= 0)
) STRICT;

-- El manifiesto móvil pide los cambios desde una versión (`WHERE sync_version > ?`).
CREATE INDEX artistas_por_sync_version ON artistas (sync_version);

CREATE TABLE albumes (
    id             INTEGER PRIMARY KEY,
    -- Sin cascada: borrar un artista no puede llevarse sus álbumes en silencio,
    -- que es lo que hacía el `ON DELETE CASCADE` de la V1.
    artista_id     INTEGER NOT NULL REFERENCES artistas (id),
    titulo         TEXT    NOT NULL CHECK (titulo <> ''),
    clave          TEXT    NOT NULL CHECK (clave <> ''),
    -- `Album` y `Single` en la instalación real; el contrato móvil los envía tal cual.
    tipo           TEXT    NOT NULL DEFAULT 'Album' CHECK (tipo <> ''),
    anio           INTEGER CHECK (anio BETWEEN 1000 AND 9999),
    mbid           TEXT,
    -- Relativa a la carpeta de la música.
    carpeta        TEXT,
    portada_id     INTEGER REFERENCES portadas (id) ON DELETE SET NULL,
    creado_en      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    sync_version   INTEGER NOT NULL DEFAULT 0 CHECK (sync_version >= 0),
    UNIQUE (artista_id, clave)
) STRICT;

-- La unicidad de arriba ya sirve para "álbumes de un artista" (su prefijo).
CREATE INDEX albumes_por_sync_version ON albumes (sync_version);
-- La pestaña Álbumes, ordenada por título sin distinguir mayúsculas.
CREATE INDEX albumes_por_titulo ON albumes (titulo COLLATE NOCASE);

CREATE TABLE pistas (
    id                  INTEGER PRIMARY KEY,
    album_id            INTEGER REFERENCES albumes (id) ON DELETE SET NULL,
    artista_id          INTEGER REFERENCES artistas (id) ON DELETE SET NULL,
    titulo              TEXT    NOT NULL CHECK (titulo <> ''),
    -- Copias del artista y del álbum *tal como los nombra la pista*. No son
    -- redundantes: en 40 pistas de la instalación real el álbum de la pista no es
    -- idéntico al título del álbum (mayúsculas, signos). El móvil recibe estas.
    artista_nombre      TEXT    NOT NULL DEFAULT '',
    album_titulo        TEXT    NOT NULL DEFAULT '',
    numero              INTEGER CHECK (numero > 0),
    disco               INTEGER CHECK (disco > 0),
    -- En segundos con decimales, no en milisegundos: el móvil recibe el valor de la
    -- V1 con toda su precisión (`285.91020408163263`) y redondearlo lo cambiaría.
    duracion_seg        REAL    CHECK (duracion_seg >= 0),
    anio                INTEGER CHECK (anio BETWEEN 1000 AND 9999),
    genero              TEXT,
    isrc                TEXT,
    mbid_grabacion      TEXT,
    mbid_lanzamiento    TEXT,
    tipo_lanzamiento    TEXT,
    -- JSON corto: de qué fuente salió cada etiqueta.
    fuentes_etiquetado  TEXT,
    -- El archivo. Relativa a la carpeta de la música: la biblioteca sobrevive a
    -- que el usuario mueva la carpeta entera.
    ruta                TEXT    NOT NULL UNIQUE CHECK (ruta <> ''),
    tamano              INTEGER NOT NULL DEFAULT 0 CHECK (tamano >= 0),
    -- Es la `x-nb-sound-hash` del contrato móvil.
    sha256              TEXT    CHECK (sha256 IS NULL OR length(sha256) = 64),
    bitrate_kbps        INTEGER CHECK (bitrate_kbps > 0),
    portada_id          INTEGER REFERENCES portadas (id) ON DELETE SET NULL,
    -- `duplicado`: la deduplicación de la V1 la apartó; no se ve ni va al móvil.
    estado              TEXT    NOT NULL DEFAULT 'biblioteca'
                                CHECK (estado IN ('biblioteca', 'duplicado')),
    -- 0 si se importó tal como estaba desde Por revisar (enmienda de ADR-007).
    verificada          INTEGER NOT NULL DEFAULT 1 CHECK (verificada IN (0, 1)),
    -- La favorita se queda en la pista, con su marca de tiempo aunque se desmarque:
    -- el móvil resuelve los conflictos comparando `favorita_actualizada_en`, y una
    -- tabla aparte perdería la hora de quien desmarcó.
    favorita            INTEGER NOT NULL DEFAULT 0 CHECK (favorita IN (0, 1)),
    favorita_actualizada_en TEXT,
    reproducciones      INTEGER NOT NULL DEFAULT 0 CHECK (reproducciones >= 0),
    ultima_reproduccion TEXT,
    creada_en           TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    actualizada_en      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    sync_version        INTEGER NOT NULL DEFAULT 0 CHECK (sync_version >= 0)
) STRICT;

-- El detalle de un álbum, en su orden; también evita recorrer la tabla entera al
-- anular `album_id` cuando se borra un álbum.
CREATE INDEX pistas_por_album ON pistas (album_id, disco, numero);
-- El detalle de un artista, y lo mismo al borrarlo.
CREATE INDEX pistas_por_artista ON pistas (artista_id);
-- El manifiesto móvil.
CREATE INDEX pistas_por_sync_version ON pistas (sync_version);
-- La pestaña Canciones, ordenada por título. Parcial: las duplicadas no se listan.
CREATE INDEX pistas_por_titulo ON pistas (titulo COLLATE NOCASE) WHERE estado = 'biblioteca';
-- La deduplicación al importar: "¿ya tengo este archivo?".
CREATE INDEX pistas_por_sha256 ON pistas (sha256) WHERE sha256 IS NOT NULL;
-- El filtro Favoritas y la playlist del sistema, que son pocas entre muchas.
CREATE INDEX pistas_favoritas ON pistas (favorita_actualizada_en) WHERE favorita = 1;
-- El filtro "Sin verificar" de Biblioteca.
CREATE INDEX pistas_sin_verificar ON pistas (id) WHERE verificada = 0;

-- Letras. En la V1 vivían fuera de la base, en un manifiesto JSONL indexado por la
-- ruta del archivo; mover un archivo las perdía.
CREATE TABLE letras (
    pista_id       INTEGER PRIMARY KEY REFERENCES pistas (id) ON DELETE CASCADE,
    planas         TEXT,
    -- En formato LRC.
    sincronizadas  TEXT,
    proveedor      TEXT,
    idioma         TEXT,
    obtenidas_en   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (coalesce(planas, '') <> '' OR coalesce(sincronizadas, '') <> '')
) STRICT;

-- Las importaciones, para que Por revisar diga de cuál viene cada archivo.
CREATE TABLE importaciones (
    id             INTEGER PRIMARY KEY,
    origen         TEXT    NOT NULL,
    iniciada_en    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    terminada_en   TEXT,
    estado         TEXT    NOT NULL DEFAULT 'en_curso'
                           CHECK (estado IN ('en_curso', 'terminada', 'cancelada', 'fallida')),
    descubiertos   INTEGER NOT NULL DEFAULT 0 CHECK (descubiertos >= 0),
    aceptados      INTEGER NOT NULL DEFAULT 0 CHECK (aceptados >= 0),
    por_revisar    INTEGER NOT NULL DEFAULT 0 CHECK (por_revisar >= 0),
    errores        INTEGER NOT NULL DEFAULT 0 CHECK (errores >= 0)
) STRICT;

-- Por revisar: archivos que no entraron solos (ADR-007, enmienda). La V1 los
-- repartía entre "revisión" y "cuarentena"; la V2 tiene una sola lista y la causa
-- dice la gravedad.
CREATE TABLE por_revisar (
    id             INTEGER PRIMARY KEY,
    -- Absoluta: el archivo todavía no está en la carpeta de la música.
    ruta           TEXT    NOT NULL UNIQUE CHECK (ruta <> ''),
    causa          TEXT    NOT NULL CHECK (causa IN (
                       'candidatos_ambiguos', 'puntaje_intermedio', 'duracion_marginal',
                       'release_type_dudoso', 'sin_candidatos', 'metadata_insuficiente',
                       'puntaje_bajo', 'escritura_fallida', 'validacion_post_escritura',
                       'duplicado', 'duracion_invalida', 'audio_ilegible')),
    -- JSON: lo que hace falta para "importar tal como está" y para comparar
    -- candidatos, no el manifiesto entero de la V1.
    metadatos      TEXT,
    importacion_id INTEGER REFERENCES importaciones (id) ON DELETE SET NULL,
    registrado_en  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    resuelto_en    TEXT
) STRICT;

-- La vista Por revisar solo lista lo pendiente.
CREATE INDEX por_revisar_pendientes ON por_revisar (registrado_en) WHERE resuelto_en IS NULL;

-- Correcciones manuales del catálogo (los `overrides_catalogacion` de la V1): una
-- regla que, al importar, gana a lo que digan las fuentes.
CREATE TABLE correcciones_catalogo (
    id             INTEGER PRIMARY KEY,
    tipo           TEXT    NOT NULL CHECK (tipo <> ''),
    valor          TEXT    NOT NULL CHECK (valor <> ''),
    -- JSON con los campos que se imponen.
    cambios        TEXT    NOT NULL,
    motivo         TEXT    NOT NULL DEFAULT '',
    origen         TEXT    NOT NULL DEFAULT 'manual',
    activa         INTEGER NOT NULL DEFAULT 1 CHECK (activa IN (0, 1)),
    creada_en      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    actualizada_en TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT;

-- Al importar se buscan las reglas activas de un tipo y valor.
CREATE INDEX correcciones_activas ON correcciones_catalogo (tipo, valor) WHERE activa = 1;
