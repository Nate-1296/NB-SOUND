//! La catalogación (Fase 4): de un archivo cualquiera a una pista con sus datos,
//! portada y letra, o a Por revisar con el motivo.
//!
//! Es la canalización de la V1 (`core/pipeline.py` y sus etapas) portada pieza a
//! pieza, con sus pruebas, antes de rediseñar nada del algoritmo (regla de la
//! fase).

pub mod acoustid;
pub mod etiquetas;
pub mod musicbrainz;
pub mod organizacion;
pub mod texto;
