//! Decodificación en streaming con Symphonia 0.6 (ADR-003).
//!
//! Entrega frames estéreo en `f32` por bloques, sin cargar la pista entera: una
//! canción de cinco minutos son 106 MB en `f32`, y el prototipo, que la decodificaba
//! de golpe, no habría aguantado una cola. Se pide al decodificador que recorte el
//! retardo y el relleno del codificador (`gapless`), que es lo que hace posible
//! encadenar pistas sin silencio.

use std::fs::File;
use std::path::Path;

use kira::Frame;
use symphonia::core::codecs::audio::{AudioDecoder, AudioDecoderOptions};
use symphonia::core::codecs::CodecParameters;
use symphonia::core::errors::Error;
use symphonia::core::formats::probe::Hint;
use symphonia::core::formats::{FormatOptions, FormatReader, SeekMode, SeekTo, TrackType};
use symphonia::core::io::MediaSourceStream;
use symphonia::core::meta::MetadataOptions;
use symphonia::core::units::Time;

use crate::error::{NsError, NsResult};

/// Un archivo abierto y listo para leer.
pub struct Decodificador {
    lector: Box<dyn FormatReader>,
    decodificador: Box<dyn AudioDecoder>,
    pista_id: u32,
    pub tasa: u32,
    /// Lo decodificado que aún no se ha entregado.
    sobrante: Vec<Frame>,
    entrelazado: Vec<f32>,
    /// Frames que hay que tirar tras una búsqueda para caer en el instante exacto.
    descartar: u64,
    ganancia: f32,
    agotado: bool,
}

fn error_de(error: &Error) -> NsError {
    match error {
        Error::IoError(e) if e.kind() == std::io::ErrorKind::NotFound => NsError::FileNotFound,
        Error::Unsupported(_) => NsError::FormatUnsupported,
        Error::DecodeError(_) => NsError::AudioCorrupted,
        _ => NsError::AudioCorrupted,
    }
}

impl Decodificador {
    /// Abre un archivo. `ganancia_db` es la normalización de volumen de la pista
    /// (F2.1.4), que se aplica aquí, al decodificar, y no en la mezcla.
    ///
    /// # Errors
    ///
    /// - [`NsError::FileNotFound`] si el archivo no existe.
    /// - [`NsError::FormatUnsupported`] si Symphonia no sabe leerlo.
    /// - [`NsError::AudioCorrupted`] si el archivo está dañado.
    pub fn abrir(ruta: &Path, ganancia_db: f32) -> NsResult<Self> {
        let archivo = File::open(ruta).map_err(|e| match e.kind() {
            std::io::ErrorKind::NotFound => NsError::FileNotFound,
            _ => NsError::StorageFailure,
        })?;
        let mss = MediaSourceStream::new(Box::new(archivo), Default::default());
        let mut pista = Hint::new();
        if let Some(ext) = ruta.extension().and_then(|e| e.to_str()) {
            pista.with_extension(ext);
        }
        let lector = symphonia::default::get_probe()
            .probe(
                &pista,
                mss,
                FormatOptions::default(),
                MetadataOptions::default(),
            )
            .map_err(|e| error_de(&e))?;
        let pista = lector
            .first_track_known_codec(TrackType::Audio)
            .ok_or(NsError::FormatUnsupported)?
            .clone();
        let Some(CodecParameters::Audio(params)) = pista.codec_params.clone() else {
            return Err(NsError::FormatUnsupported);
        };
        let decodificador = symphonia::default::get_codecs()
            .make_audio_decoder(&params, &AudioDecoderOptions::default().gapless(true))
            .map_err(|e| error_de(&e))?;
        Ok(Self {
            lector,
            decodificador,
            pista_id: pista.id,
            tasa: params.sample_rate.unwrap_or(44_100),
            sobrante: Vec::new(),
            entrelazado: Vec::new(),
            descartar: 0,
            ganancia: 10f32.powf(ganancia_db / 20.0),
            agotado: false,
        })
    }

    /// Salta al instante pedido con precisión de muestra: se busca el paquete
    /// anterior y se descartan los frames sobrantes (F0.4.1 midió un error de un
    /// frame en MP3 con VBR).
    ///
    /// # Errors
    ///
    /// [`NsError::AudioCorrupted`] si el archivo no admite la búsqueda.
    pub fn buscar(&mut self, segundos: f64) -> NsResult<u64> {
        let tiempo = Time::try_from_secs_f64(segundos.max(0.0)).ok_or(NsError::Internal)?;
        let buscado = self
            .lector
            .seek(
                SeekMode::Accurate,
                SeekTo::Time {
                    time: tiempo,
                    track_id: Some(self.pista_id),
                },
            )
            .map_err(|e| error_de(&e))?;
        self.decodificador.reset();
        self.sobrante.clear();
        self.agotado = false;
        let requerido = buscado.required_ts.get().max(0) as u64;
        let real = buscado.actual_ts.get().max(0) as u64;
        self.descartar = requerido.saturating_sub(real);
        Ok(requerido)
    }

    /// Añade a `destino` hasta `n` frames. Devuelve cuántos añadió; 0 es el final.
    ///
    /// # Errors
    ///
    /// [`NsError::AudioCorrupted`] si el archivo deja de poder leerse. Un paquete
    /// dañado suelto se salta, como hacen todos los reproductores.
    pub fn leer(&mut self, destino: &mut Vec<Frame>, n: usize) -> NsResult<usize> {
        let mut escritos = 0;
        while escritos < n {
            if !self.sobrante.is_empty() {
                let tomar = (n - escritos).min(self.sobrante.len());
                destino.extend(self.sobrante.drain(..tomar));
                escritos += tomar;
                continue;
            }
            if self.agotado || !self.decodificar_paquete()? {
                self.agotado = true;
                break;
            }
        }
        Ok(escritos)
    }

    /// Decodifica un paquete en `sobrante`. `false` si no quedan.
    fn decodificar_paquete(&mut self) -> NsResult<bool> {
        loop {
            let paquete = match self.lector.next_packet() {
                Ok(Some(p)) => p,
                Ok(None) | Err(Error::ResetRequired) => return Ok(false),
                Err(Error::IoError(e)) if e.kind() == std::io::ErrorKind::UnexpectedEof => {
                    return Ok(false);
                }
                Err(e) => return Err(error_de(&e)),
            };
            if paquete.track_id != self.pista_id {
                continue;
            }
            let buffer = match self.decodificador.decode(&paquete) {
                Ok(b) => b,
                Err(Error::DecodeError(_)) => continue,
                Err(e) => return Err(error_de(&e)),
            };
            let canales = buffer.spec().channels().count().max(1);
            self.entrelazado.clear();
            buffer.copy_to_vec_interleaved(&mut self.entrelazado);
            let g = self.ganancia;
            for frame in self.entrelazado.chunks_exact(canales) {
                if self.descartar > 0 {
                    self.descartar -= 1;
                    continue;
                }
                let izq = frame[0];
                let der = if canales > 1 { frame[1] } else { frame[0] };
                self.sobrante.push(Frame::new(izq * g, der * g));
            }
            return Ok(true);
        }
    }
}
