-- V7: búsqueda de texto completo (F1.3.1).
--
-- Un índice FTS5 por pista con su título, artista, álbum y letra. Sin contenido
-- propio (`content=''`): el texto ya está en `pistas` y `letras`, y guardarlo dos
-- veces duplicaría las letras, que son lo más grande de la base. `contentless_delete`
-- permite borrar y sustituir filas, que es lo que hacen los disparadores.
--
-- `remove_diacritics 2`: quien escribe "cancion" encuentra "canción", y "Mana",
-- "Maná". El prefijo de 2 y 3 caracteres hace que buscar mientras se escribe no
-- recorra el índice entero en las primeras letras.
--
-- La V1 indexaba también el género, vacío en todas las pistas, y no las letras.

CREATE VIRTUAL TABLE busqueda USING fts5 (
    titulo, artista, album, letra,
    content = '',
    contentless_delete = 1,
    tokenize = 'unicode61 remove_diacritics 2',
    prefix = '2 3'
);

-- La letra que se indexa: la plana, o la sincronizada si no hay otra. Las marcas
-- de tiempo de la sincronizada (`[00:12.34]`) son tokens numéricos que nadie
-- busca; no estorban al orden porque la letra pesa poco.
CREATE TRIGGER busqueda_al_insertar_pista AFTER INSERT ON pistas
BEGIN
    INSERT OR REPLACE INTO busqueda (rowid, titulo, artista, album, letra)
    VALUES (NEW.id, NEW.titulo, NEW.artista_nombre, NEW.album_titulo,
            (SELECT coalesce(planas, sincronizadas) FROM letras WHERE pista_id = NEW.id));
END;

CREATE TRIGGER busqueda_al_cambiar_pista AFTER UPDATE OF titulo, artista_nombre, album_titulo
ON pistas
BEGIN
    INSERT OR REPLACE INTO busqueda (rowid, titulo, artista, album, letra)
    VALUES (NEW.id, NEW.titulo, NEW.artista_nombre, NEW.album_titulo,
            (SELECT coalesce(planas, sincronizadas) FROM letras WHERE pista_id = NEW.id));
END;

CREATE TRIGGER busqueda_al_borrar_pista AFTER DELETE ON pistas
BEGIN
    DELETE FROM busqueda WHERE rowid = OLD.id;
END;

CREATE TRIGGER busqueda_al_insertar_letra AFTER INSERT ON letras
BEGIN
    INSERT OR REPLACE INTO busqueda (rowid, titulo, artista, album, letra)
    SELECT id, titulo, artista_nombre, album_titulo, coalesce(NEW.planas, NEW.sincronizadas)
    FROM pistas WHERE id = NEW.pista_id;
END;

CREATE TRIGGER busqueda_al_cambiar_letra AFTER UPDATE ON letras
BEGIN
    INSERT OR REPLACE INTO busqueda (rowid, titulo, artista, album, letra)
    SELECT id, titulo, artista_nombre, album_titulo, coalesce(NEW.planas, NEW.sincronizadas)
    FROM pistas WHERE id = NEW.pista_id;
END;

-- Al borrar una pista, la cascada borra su letra después: la pista ya no existe y
-- el SELECT no inserta nada.
CREATE TRIGGER busqueda_al_borrar_letra AFTER DELETE ON letras
BEGIN
    INSERT OR REPLACE INTO busqueda (rowid, titulo, artista, album, letra)
    SELECT id, titulo, artista_nombre, album_titulo, NULL
    FROM pistas WHERE id = OLD.pista_id;
END;

-- El orden por defecto: una coincidencia en el título vale más que en el artista,
-- y esta más que en el álbum o en la letra.
INSERT INTO busqueda (busqueda, rank) VALUES ('rank', 'bm25(10.0, 5.0, 3.0, 1.0)');

INSERT INTO busqueda (rowid, titulo, artista, album, letra)
SELECT p.id, p.titulo, p.artista_nombre, p.album_titulo, coalesce(l.planas, l.sincronizadas)
FROM pistas p LEFT JOIN letras l ON l.pista_id = p.id;
