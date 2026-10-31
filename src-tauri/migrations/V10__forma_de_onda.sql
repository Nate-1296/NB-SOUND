-- V10: la forma de onda de cada pista (F8.1).
--
-- Los picos salen de la misma decodificación que mide la sonoridad, así que viven
-- en su fila: se miden juntos y caducan juntos. 1.000 bytes, el máximo absoluto de
-- cada tramo de 0 a 255. Vacío si el archivo no se pudo leer (para no reintentarlo,
-- como la sonoridad sin valores); NULL en lo medido antes de esta versión, que por
-- eso se vuelve a medir.
ALTER TABLE sonoridad ADD COLUMN picos BLOB
    CHECK (picos IS NULL OR length(picos) IN (0, 1000));

