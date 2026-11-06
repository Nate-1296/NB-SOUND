-- V1: metadatos de la propia instalación.
--
-- Deliberadamente mínima: el esquema del dominio llega en las migraciones
-- siguientes. Esta existe para que el motor de migraciones tenga algo real que
-- aplicar.
--
-- Contrato: docs/adr/decisions/ADR-004-datos.md

CREATE TABLE instalacion (
    clave          TEXT PRIMARY KEY,
    valor          TEXT NOT NULL,
    actualizado_en TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT;

INSERT INTO instalacion (clave, valor) VALUES
    ('creada_por_version', '2.0.0-alpha.0'),
    ('id_instalacion', lower(hex(randomblob(16))));
