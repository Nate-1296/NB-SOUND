//! La catalogación (Fase 4): de un archivo cualquiera a una pista con sus datos,
//! portada y letra, o a Por revisar con el motivo.
//!
//! Es la canalización de la V1 (`core/pipeline.py` y sus etapas) portada pieza a
//! pieza, con sus pruebas, antes de rediseñar nada del algoritmo (regla de la
//! fase).

pub mod acoustid;
pub mod canalizacion;
pub mod duplicados;
pub mod emparejador;
pub mod etapas;
pub mod etiquetas;
pub mod ia;
pub mod importacion;
pub mod letras_red;
pub mod modelo;
pub mod musicbrainz;
pub mod normalizacion;
pub mod organizacion;
pub mod por_revisar;
pub mod portadas_red;
pub mod shazam;
pub mod texto;
pub mod vigilancia;
