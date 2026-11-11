-- ADR-013: la preferencia sigue en preferencias; solo su revisión vive aquí.
CREATE TABLE revision_de_recursos (
    recurso TEXT PRIMARY KEY,
    secuencia INTEGER NOT NULL CHECK (secuencia BETWEEN 0 AND 9007199254740991)
) STRICT;

INSERT INTO revision_de_recursos (recurso, secuencia) VALUES ('copia_frecuencia', 0);
