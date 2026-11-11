//! Coordinación dentro de la aplicación propietaria. No accede a bases ni valida dominio.

#[cfg(all(feature = "local", any(unix, windows)))]
pub mod port;

use std::sync::{Arc, Mutex, MutexGuard};

use nb_protocol::capability::{
    ChangeResult, Epoch, ResourceError, ResourceKey, Revision, Sequence, Snapshot,
};
use tokio::sync::watch;

/// La aplicación obtiene valor y secuencia de una lectura consistente de su almacenamiento.
pub struct StoredSnapshot<V> {
    pub sequence: Sequence,
    pub value: V,
}

pub enum Commit<V> {
    Applied(StoredSnapshot<V>),
    Unchanged(StoredSnapshot<V>),
    Conflict(StoredSnapshot<V>),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OwnerError {
    InvalidInput,
    Persistence,
    ResultUnknown,
    Unavailable,
    RevisionExhausted,
}

impl From<OwnerError> for ResourceError {
    fn from(error: OwnerError) -> Self {
        match error {
            OwnerError::InvalidInput => Self::InvalidInput,
            OwnerError::Persistence => Self::Persistence,
            OwnerError::ResultUnknown => Self::ResultUnknown,
            OwnerError::Unavailable => Self::Unavailable,
            OwnerError::RevisionExhausted => Self::RevisionExhausted,
        }
    }
}

/// Implementado en la app. `compare_and_set` debe comprobar y persistir en una transacción.
/// Ejecutar estos métodos síncronos en hilos de trabajo, fuera de la UI/event loop.
pub trait StateOwner: Send + 'static {
    type Value: Clone + PartialEq + Send + Sync + 'static;
    type Command;

    fn read(&mut self) -> Result<StoredSnapshot<Self::Value>, OwnerError>;
    fn compare_and_set(
        &mut self,
        expected: Sequence,
        command: Self::Command,
    ) -> Result<Commit<Self::Value>, OwnerError>;
}

#[derive(Debug)]
pub enum ResourceEvent<V> {
    Confirmed(Arc<Snapshot<V>>),
    Unavailable(ResourceError),
}

impl<V> Clone for ResourceEvent<V> {
    fn clone(&self) -> Self {
        match self {
            Self::Confirmed(snapshot) => Self::Confirmed(snapshot.clone()),
            Self::Unavailable(error) => Self::Unavailable(*error),
        }
    }
}

pub struct Subscription<V> {
    receiver: watch::Receiver<ResourceEvent<V>>,
}

pub type Observation<V> = (Arc<Snapshot<V>>, Subscription<V>);

impl<V> Subscription<V> {
    /// Los cambios intermedios pueden agruparse. No es una cola de eventos de dominio.
    pub async fn next(&mut self) -> Result<ResourceEvent<V>, ResourceError> {
        self.receiver
            .changed()
            .await
            .map_err(|_| ResourceError::Unavailable)?;
        Ok(self.receiver.borrow_and_update().clone())
    }

    pub fn has_changed(&self) -> Result<bool, ResourceError> {
        self.receiver
            .has_changed()
            .map_err(|_| ResourceError::Unavailable)
    }
}

struct Inner<O: StateOwner> {
    owner: O,
    current: Arc<Snapshot<O::Value>>,
    events: watch::Sender<ResourceEvent<O::Value>>,
    unavailable: bool,
    faulted: bool,
}

/// Un recurso por instancia de autoridad; compartir clones entre todos sus escritores locales.
pub struct OwnedResource<O: StateOwner> {
    inner: Arc<Mutex<Inner<O>>>,
}

impl<O: StateOwner> Clone for OwnedResource<O> {
    fn clone(&self) -> Self {
        Self {
            inner: self.inner.clone(),
        }
    }
}

impl<O: StateOwner> OwnedResource<O> {
    pub fn new(key: ResourceKey, mut owner: O) -> Result<Self, ResourceError> {
        let stored = owner.read().map_err(ResourceError::from)?;
        let current = Arc::new(Snapshot {
            key,
            revision: Revision {
                epoch: new_epoch()?,
                sequence: stored.sequence,
            },
            value: stored.value,
        });
        let (events, _) = watch::channel(ResourceEvent::Confirmed(current.clone()));
        Ok(Self {
            inner: Arc::new(Mutex::new(Inner {
                owner,
                current,
                events,
                unavailable: false,
                faulted: false,
            })),
        })
    }

    fn lock(&self) -> Result<MutexGuard<'_, Inner<O>>, ResourceError> {
        self.inner
            .lock()
            .map_err(|_| ResourceError::Synchronization)
    }

    pub fn read(&self) -> Result<Arc<Snapshot<O::Value>>, ResourceError> {
        let mut inner = self.lock()?;
        inner.refresh()?;
        Ok(inner.current.clone())
    }

    /// Captura y receptor se establecen bajo la misma exclusión que las publicaciones.
    pub fn subscribe(&self) -> Result<Observation<O::Value>, ResourceError> {
        let mut inner = self.lock()?;
        inner.refresh()?;
        Ok((
            inner.current.clone(),
            Subscription {
                receiver: inner.events.subscribe(),
            },
        ))
    }

    pub fn compare_and_set(
        &self,
        expected: &Revision,
        command: O::Command,
    ) -> Result<ChangeResult<O::Value>, ResourceError> {
        let mut inner = self.lock()?;
        inner.refresh()?;
        if &inner.current.revision != expected {
            return Ok(ChangeResult::Conflict((*inner.current).clone()));
        }
        let result = inner.owner.compare_and_set(expected.sequence, command);
        match result {
            Ok(Commit::Applied(stored)) => {
                if stored.sequence <= expected.sequence {
                    return Err(inner.contract_failure());
                }
                inner.accept(stored)?;
                Ok(ChangeResult::Applied((*inner.current).clone()))
            }
            Ok(Commit::Unchanged(stored)) => {
                if stored.sequence != expected.sequence || stored.value != inner.current.value {
                    return Err(inner.contract_failure());
                }
                inner.accept(stored)?;
                Ok(ChangeResult::Unchanged((*inner.current).clone()))
            }
            Ok(Commit::Conflict(stored)) => {
                if stored.sequence <= expected.sequence {
                    return Err(inner.contract_failure());
                }
                inner.accept(stored)?;
                Ok(ChangeResult::Conflict((*inner.current).clone()))
            }
            Err(error) => Err(inner.owner_failure(error)),
        }
    }

    /// Usar al reabrir tras restauración: una época nueva invalida todas las revisiones antiguas.
    pub fn reinitialize(&self, mut owner: O) -> Result<Arc<Snapshot<O::Value>>, ResourceError> {
        let mut inner = self.lock()?;
        let stored = owner.read().map_err(ResourceError::from)?;
        let epoch = new_epoch()?;
        let current = Arc::new(Snapshot {
            key: inner.current.key.clone(),
            revision: Revision {
                epoch,
                sequence: stored.sequence,
            },
            value: stored.value,
        });
        inner.owner = owner;
        inner.current = current.clone();
        inner.unavailable = false;
        inner.faulted = false;
        inner
            .events
            .send_replace(ResourceEvent::Confirmed(current.clone()));
        Ok(current)
    }
}

impl<O: StateOwner> Inner<O> {
    fn refresh(&mut self) -> Result<(), ResourceError> {
        if self.faulted {
            return Err(ResourceError::OwnerContractViolation);
        }
        match self.owner.read() {
            Ok(stored) => self.accept(stored),
            Err(error) => Err(self.owner_failure(error)),
        }
    }

    fn accept(&mut self, stored: StoredSnapshot<O::Value>) -> Result<(), ResourceError> {
        let previous = self.current.revision.sequence;
        if stored.sequence < previous
            || (stored.sequence == previous && stored.value != self.current.value)
        {
            return Err(self.contract_failure());
        }
        if stored.sequence != previous || self.unavailable {
            self.current = Arc::new(Snapshot {
                key: self.current.key.clone(),
                revision: Revision {
                    epoch: self.current.revision.epoch.clone(),
                    sequence: stored.sequence,
                },
                value: stored.value,
            });
            self.unavailable = false;
            self.events
                .send_replace(ResourceEvent::Confirmed(self.current.clone()));
        }
        Ok(())
    }

    fn contract_failure(&mut self) -> ResourceError {
        self.faulted = true;
        self.unavailable = true;
        self.events.send_replace(ResourceEvent::Unavailable(
            ResourceError::OwnerContractViolation,
        ));
        ResourceError::OwnerContractViolation
    }

    fn owner_failure(&mut self, error: OwnerError) -> ResourceError {
        let error = ResourceError::from(error);
        if error != ResourceError::InvalidInput {
            self.unavailable = true;
            self.events.send_replace(ResourceEvent::Unavailable(error));
        }
        error
    }
}

fn new_epoch() -> Result<Epoch, ResourceError> {
    let mut bytes = [0_u8; 16];
    getrandom::fill(&mut bytes).map_err(|_| ResourceError::EntropyUnavailable)?;
    let mut encoded = String::with_capacity(32);
    const HEX: &[u8; 16] = b"0123456789abcdef";
    for byte in bytes {
        encoded.push(HEX[(byte >> 4) as usize] as char);
        encoded.push(HEX[(byte & 15) as usize] as char);
    }
    Epoch::try_from(encoded).map_err(|_| ResourceError::EntropyUnavailable)
}
