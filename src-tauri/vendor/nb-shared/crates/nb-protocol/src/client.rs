//! Cliente secuencial: un único comando en vuelo, sin reintentos implícitos.

use thiserror::Error;
use tokio::io::{AsyncRead, AsyncWrite};

use crate::{
    ErrorCode, MAX_REQUEST_ID, Operation, Outcome, PROTOCOL_VERSION, Request, Response, ResultData,
    frame::{FrameError, read_frame, write_frame},
};

#[derive(Debug, Error)]
pub enum ClientError {
    #[error(transparent)]
    Frame(#[from] FrameError),
    #[error("CONNECTION_CLOSED")]
    Closed,
    #[error("RESPONSE_ID_MISMATCH")]
    ResponseId,
    #[error("UNEXPECTED_RESPONSE")]
    UnexpectedResponse,
    #[error("REQUEST_ID_EXHAUSTED")]
    Exhausted,
    #[error("REMOTE_ERROR: {0:?}")]
    Remote(ErrorCode),
}

/// Tras un fallo de transporte o cancelación se descarta la conexión completa.
pub struct Client<R, W> {
    reader: R,
    writer: W,
    next_id: u64,
    usable: bool,
}

impl<R: AsyncRead + Unpin, W: AsyncWrite + Unpin> Client<R, W> {
    pub async fn connect(reader: R, writer: W) -> Result<Self, ClientError> {
        let mut client = Self {
            reader,
            writer,
            next_id: 1,
            usable: true,
        };
        match client
            .call(Operation::Hello {
                protocol_version: PROTOCOL_VERSION,
            })
            .await?
        {
            ResultData::Hello {
                protocol_version: PROTOCOL_VERSION,
            } => Ok(client),
            _ => Err(ClientError::UnexpectedResponse),
        }
    }

    pub async fn call(&mut self, operation: Operation) -> Result<ResultData, ClientError> {
        if !self.usable {
            return Err(ClientError::Closed);
        }
        if self.next_id > MAX_REQUEST_ID {
            self.usable = false;
            return Err(ClientError::Exhausted);
        }
        // Invalidar antes del primer await también protege frente a cancelación del futuro.
        self.usable = false;
        let id = self.next_id;
        self.next_id += 1;
        let shutting_down = matches!(operation, Operation::Shutdown);
        let expected = operation.clone();
        write_frame(&mut self.writer, &Request { id, operation }).await?;
        let response: Response = read_frame(&mut self.reader)
            .await?
            .ok_or(ClientError::Closed)?;
        if response.id != id {
            return Err(ClientError::ResponseId);
        }
        match response.outcome {
            Outcome::Ok(data) => {
                let matches = matches!(
                    (&expected, &data),
                    (Operation::Hello { .. }, ResultData::Hello { .. })
                        | (Operation::Ping, ResultData::Pong)
                        | (Operation::ListCapabilities, ResultData::Capabilities { .. })
                        | (Operation::Shutdown, ResultData::ShuttingDown)
                        | (
                            Operation::ReadResource { .. },
                            ResultData::ResourceSnapshot(_)
                        )
                        | (
                            Operation::ChangeResource { .. },
                            ResultData::ResourceChange(_)
                        )
                        | (
                            Operation::ObserveResource { .. },
                            ResultData::ResourceSnapshot(_) | ResultData::ResourceNoChange
                        )
                        | (
                            Operation::ReadResource { .. }
                                | Operation::ChangeResource { .. }
                                | Operation::ObserveResource { .. },
                            ResultData::ResourceFailure { .. }
                        )
                );
                if !matches {
                    return Err(ClientError::UnexpectedResponse);
                }
                self.usable = !shutting_down;
                Ok(data)
            }
            Outcome::Error(code) => Err(ClientError::Remote(code)),
        }
    }
}
