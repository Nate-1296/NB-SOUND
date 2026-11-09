-- V11: lo que la biblioteca ya intentó completar en segundo plano (A9).
--
-- Una pista sin portada, sin letra o con su artista sin imagen se vuelve a buscar
-- sola, pero no cada vez que se abre NB Sound: lo que no se encontró se reintenta
-- pasado un mes. Borrar la pista borra su intento.
CREATE TABLE completado_fondo (
    pista_id     INTEGER PRIMARY KEY REFERENCES pistas (id) ON DELETE CASCADE,
    intentado_en TEXT    NOT NULL
) STRICT;
