//! Decodificación con Symphonia 0.6 a PCM entrelazado estéreo en `f32`.
//!
//! Se pide al decodificador que recorte el retardo y el relleno del codificador
//! (`gapless`), que es lo que hace posible la reproducción sin cortes entre pistas.

use std::fs::File;
use std::path::Path;

use symphonia::core::codecs::audio::AudioDecoderOptions;
use symphonia::core::codecs::CodecParameters;
use symphonia::core::errors::Error;
use symphonia::core::formats::probe::Hint;
use symphonia::core::formats::{FormatOptions, FormatReader, SeekMode, SeekTo, TrackType};
use symphonia::core::io::MediaSourceStream;
use symphonia::core::meta::MetadataOptions;
use symphonia::core::units::Time;

pub struct Pcm {
    pub tasa: u32,
    /// Estéreo entrelazado. Lo mono se duplica en los dos canales.
    pub muestras: Vec<f32>,
    /// Lo que el contenedor declara, para comparar con lo decodificado.
    pub frames_declarados: Option<u64>,
}

impl Pcm {
    pub fn frames(&self) -> usize {
        self.muestras.len() / 2
    }
}

fn abrir(ruta: &Path) -> Result<Box<dyn FormatReader>, Error> {
    let archivo = File::open(ruta)?;
    let mss = MediaSourceStream::new(Box::new(archivo), Default::default());
    let mut pista = Hint::new();
    if let Some(ext) = ruta.extension().and_then(|e| e.to_str()) {
        pista.with_extension(ext);
    }
    symphonia::default::get_probe().probe(
        &pista,
        mss,
        FormatOptions::default(),
        MetadataOptions::default(),
    )
}

/// Decodifica desde `desde_segundos` (o desde el principio) hasta el final.
///
/// Con `desde_segundos`, la búsqueda es precisa: se busca el paquete anterior y se
/// descartan las muestras sobrantes hasta el instante pedido.
pub fn decodificar(ruta: &Path, desde_segundos: Option<f64>) -> Result<Pcm, Error> {
    let mut lector = abrir(ruta)?;
    let pista = lector
        .first_track_known_codec(TrackType::Audio)
        .ok_or(Error::Unsupported("sin pista de audio"))?
        .clone();
    let Some(CodecParameters::Audio(params)) = pista.codec_params.clone() else {
        return Err(Error::Unsupported("la pista no es de audio"));
    };
    let mut decodificador = symphonia::default::get_codecs()
        .make_audio_decoder(&params, &AudioDecoderOptions::default().gapless(true))?;
    let tasa = params.sample_rate.unwrap_or(44_100);

    let mut descartar: u64 = 0;
    if let Some(segundos) = desde_segundos {
        let tiempo = Time::try_from_secs_f64(segundos).ok_or(Error::Unsupported("tiempo"))?;
        let buscado = lector.seek(
            SeekMode::Accurate,
            SeekTo::Time {
                time: tiempo,
                track_id: Some(pista.id),
            },
        )?;
        decodificador.reset();
        descartar = (buscado.required_ts.get() - buscado.actual_ts.get()).max(0) as u64;
    }

    let mut muestras = Vec::new();
    let mut tmp: Vec<f32> = Vec::new();
    loop {
        let paquete = match lector.next_packet() {
            Ok(Some(p)) => p,
            Ok(None) => break,
            Err(Error::ResetRequired) => break,
            Err(e) => return Err(e),
        };
        if paquete.track_id != pista.id {
            continue;
        }
        let buffer = match decodificador.decode(&paquete) {
            Ok(b) => b,
            Err(Error::DecodeError(_)) => continue,
            Err(e) => return Err(e),
        };
        let canales = buffer.spec().channels().count().max(1);
        tmp.clear();
        buffer.copy_to_vec_interleaved(&mut tmp);
        for frame in tmp.chunks_exact(canales) {
            if descartar > 0 {
                descartar -= 1;
                continue;
            }
            let izq = frame[0];
            let der = if canales > 1 { frame[1] } else { frame[0] };
            muestras.push(izq);
            muestras.push(der);
        }
    }

    Ok(Pcm {
        tasa,
        muestras,
        frames_declarados: pista.num_frames,
    })
}
