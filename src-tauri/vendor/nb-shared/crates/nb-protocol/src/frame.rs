//! Prefijo de longitud de 4 bytes big-endian seguido de JSON UTF-8 acotado.

use std::io;

use serde::{Serialize, de::DeserializeOwned};
use thiserror::Error;
use tokio::io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt};
use zeroize::Zeroizing;

use crate::MAX_FRAME_BYTES;

/// Los errores no incluyen el mensaje recibido ni detalles del sistema de archivos.
#[derive(Debug, Error)]
pub enum FrameError {
    #[error("IO_ERROR")]
    Io(#[source] io::Error),
    #[error("TRUNCATED_FRAME")]
    Truncated,
    #[error("INVALID_FRAME_LENGTH")]
    InvalidLength,
    #[error("INVALID_JSON_MESSAGE")]
    InvalidMessage,
}

/// EOF entre mensajes es un cierre normal; EOF dentro de un mensaje es un fallo.
pub async fn read_frame<R, T>(reader: &mut R) -> Result<Option<T>, FrameError>
where
    R: AsyncRead + Unpin,
    T: DeserializeOwned,
{
    let mut header = [0_u8; 4];
    let count = reader
        .read(&mut header[..1])
        .await
        .map_err(FrameError::Io)?;
    if count == 0 {
        return Ok(None);
    }
    read_exact(reader, &mut header[1..]).await?;
    let length = u32::from_be_bytes(header) as usize;
    if length == 0 || length > MAX_FRAME_BYTES {
        return Err(FrameError::InvalidLength);
    }
    let mut bytes = Zeroizing::new(vec![0; length]);
    read_exact(reader, &mut bytes).await?;
    serde_json::from_slice(&bytes)
        .map(Some)
        .map_err(|_| FrameError::InvalidMessage)
}

async fn read_exact<R: AsyncRead + Unpin>(
    reader: &mut R,
    bytes: &mut [u8],
) -> Result<(), FrameError> {
    reader.read_exact(bytes).await.map(|_| ()).map_err(|e| {
        if e.kind() == io::ErrorKind::UnexpectedEof {
            FrameError::Truncated
        } else {
            FrameError::Io(e)
        }
    })
}

/// Serializa con límite incluso antes de construir el frame de salida completo.
pub async fn write_frame<W, T>(writer: &mut W, value: &T) -> Result<(), FrameError>
where
    W: AsyncWrite + Unpin,
    T: Serialize,
{
    let mut encoded = LimitedBuffer(Zeroizing::new(Vec::new()));
    serde_json::to_writer(&mut encoded, value).map_err(|_| {
        if encoded.0.len() == MAX_FRAME_BYTES {
            FrameError::InvalidLength
        } else {
            FrameError::InvalidMessage
        }
    })?;
    let length = u32::try_from(encoded.0.len()).map_err(|_| FrameError::InvalidLength)?;
    writer
        .write_all(&length.to_be_bytes())
        .await
        .map_err(FrameError::Io)?;
    writer.write_all(&encoded.0).await.map_err(FrameError::Io)?;
    writer.flush().await.map_err(FrameError::Io)
}

struct LimitedBuffer(Zeroizing<Vec<u8>>);

impl io::Write for LimitedBuffer {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        let remaining = MAX_FRAME_BYTES - self.0.len();
        let count = remaining.min(bytes.len());
        self.0.extend_from_slice(&bytes[..count]);
        if count != bytes.len() {
            return Err(io::Error::new(
                io::ErrorKind::FileTooLarge,
                "FRAME_TOO_LARGE",
            ));
        }
        Ok(count)
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}
