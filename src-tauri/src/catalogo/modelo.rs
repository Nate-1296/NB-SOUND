//! Los tipos que recorren la canalización (`domain/models.py` de la V1).
//!
//! Las causas conservan los valores de la V1 (`archivo_corrupto`,
//! `puntaje_intermedio`…): son las claves con las que Por revisar dice el motivo
//! en lenguaje llano (enmienda de ADR-007), y la tabla de esa enmienda las nombra
//! así.

use serde::Serialize;

/// De dónde salió un dato (`FuenteIdentificacion`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Fuente {
    #[default]
    TagLocal,
    NombreArchivo,
    Acoustid,
    Shazam,
    Musicbrainz,
    Ia,
}

/// Lo que dijo Shazam (`ResultadoShazam`).
#[derive(Debug, Clone, Default, PartialEq)]
pub struct DeShazam {
    pub identificado: bool,
    pub titulo: String,
    pub artista: String,
    pub isrc: Option<String>,
    pub album: Option<String>,
    pub anio: Option<i32>,
}

/// Lo que dijo AcoustID (`ResultadoAcoustID`): grabaciones y confianzas, en orden.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct DeAcoustid {
    pub grabaciones: Vec<String>,
    pub confianzas: Vec<f64>,
}

impl DeAcoustid {
    pub fn mejor(&self) -> f64 {
        self.confianzas.iter().copied().fold(0.0, f64::max)
    }
}

/// Los datos de una pista listos para buscar y comparar (`MetadataNormalizada`).
#[derive(Debug, Clone, Default, PartialEq)]
pub struct Normalizada {
    pub titulo: String,
    pub titulo_para_match: String,
    pub artista: String,
    pub artista_para_match: String,
    pub featuring: Option<String>,
    pub album: String,
    pub album_para_match: String,
    pub numero: Option<u32>,
    pub anio: Option<i32>,
    pub duracion_seg: Option<f64>,
    pub isrc: Option<String>,
    pub fuente_titulo: Fuente,
    pub fuente_artista: Fuente,
    pub confianza: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CausaCuarentena {
    ArchivoCorrupto,
    ArchivoMuyPequeno,
    ArchivoIlegible,
    DuracionInvalida,
    BitrateInsuficiente,
    MetadataInsuficiente,
    MetadataFinalInvalida,
    SinCandidatos,
    PuntajeBajo,
    OwnershipInvalido,
    EscrituraFallida,
    ValidacionPostEscritura,
    ErrorInesperado,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CausaRevision {
    PuntajeIntermedio,
    CandidatosAmbiguos,
    OwnershipAmbiguo,
    ReleaseTypeDudoso,
    DuracionMarginal,
    IaRevisionManual,
    FuentesDiscrepantes,
    ClasificacionProvisional,
}

/// Lo que se decide de un archivo (`DecisionTipo` con su causa).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Veredicto {
    Aceptado,
    /// Identidad sólida y clasificación del lanzamiento incompleta.
    Provisional(CausaRevision),
    Revision(CausaRevision),
    Cuarentena(CausaCuarentena),
}

impl Veredicto {
    /// Entra en la biblioteca sin pasar por Por revisar.
    pub fn entra(self) -> bool {
        matches!(self, Self::Aceptado | Self::Provisional(_))
    }
}
