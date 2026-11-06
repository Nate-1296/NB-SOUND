//! La catalogación (Fase 4): de un archivo cualquiera a una pista con sus datos,
//! portada y letra, o a Por revisar con el motivo.
//!
//! La canalización (`core/pipeline.py` y sus etapas), pieza a pieza y con sus
//! pruebas.

pub mod acoustid;
pub mod auditoria;
pub mod borrado;
pub mod canalizacion;
pub mod carpeta;
pub mod completar_datos;
pub mod correcciones;
pub mod duplicados;
pub mod edicion;
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
pub mod ubicacion;
pub mod vigilancia;
