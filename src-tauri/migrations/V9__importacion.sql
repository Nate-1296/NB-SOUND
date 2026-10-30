-- V9: lo que falta por importar (F4.1.13).
--
-- La V1 reconstruía una importación cortada leyendo sus manifiestos
-- (`core/import_recovery_service.py`). La V2 apunta cada archivo antes de empezar
-- y lo borra al terminarlo: si la aplicación se cierra a medias, al volver sigue
-- por donde iba, sin repetir lo hecho ni perder lo que faltaba.
CREATE TABLE pendientes_importacion (
    ruta            TEXT    PRIMARY KEY CHECK (ruta <> ''),
    importacion_id  INTEGER NOT NULL REFERENCES importaciones (id) ON DELETE CASCADE,
    orden           INTEGER NOT NULL,
    anadida_en      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT, WITHOUT ROWID;

-- Se procesan en el orden en que llegaron.
CREATE INDEX pendientes_en_orden ON pendientes_importacion (importacion_id, orden);
