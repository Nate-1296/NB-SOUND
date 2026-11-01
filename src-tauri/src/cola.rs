//! La cola de reproducción, con aleatorio y repetición (F2.1.2).
//!
//! Es una máquina de estados pura: no toca el motor ni la base. Cada operación
//! cambia la cola y devuelve la [`Accion`] que el motor tiene que hacer. Su
//! especificación son las pruebas de la V1 (`legado/tests/test_reproductor_ui_contract.py`),
//! traducidas una a una al final de este archivo con el nombre de la original, y la
//! lógica es la de `legado/servicios/reproductor.py`:
//!
//! * **La cola no se consume.** La pista que termina se queda; solo avanza el
//!   puntero, y se puede volver atrás, como en Spotify.
//! * **Aleatorio reordena la cola visible**: la que suena queda primera y el resto
//!   se baraja, y "siguiente" sigue ese orden. Al quitarlo vuelve el orden de
//!   partida, completo.
//! * **Elegir una pista suelta sustituye la cola** por esa pista.
//!
//! La V1 guardaba además un "contexto" que reconstruía la cola con repetir todo,
//! pero lo copiaba de la cola tras cada cambio, así que nunca difería de ella: no
//! se porta.

/// Una fila de la cola. Dos filas son la misma pista si comparten `pista_id`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Fila {
    pub pista_id: i64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Repeticion {
    Ninguno,
    Todo,
    Uno,
}

impl Repeticion {
    /// Los valores que guardaba la V1 (`modo_repeticion`).
    pub fn desde_v1(texto: &str) -> Option<Self> {
        match texto {
            "ninguno" => Some(Self::Ninguno),
            "todo" => Some(Self::Todo),
            "uno" => Some(Self::Uno),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Estado {
    Detenido,
    Reproduciendo,
    Pausado,
    /// Se acabó la cola: la última pista sigue marcada y "reproducir" la repite.
    Finalizada,
}

/// Lo que el motor tiene que hacer después de una operación.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Accion {
    Nada,
    Reproducir { fila: Fila, desde_seg: f64 },
    Pausar,
    Reanudar,
    Detener,
}

/// El azar, inyectable para que las pruebas sean deterministas.
pub trait Azar: Send {
    fn barajar(&mut self, filas: &mut [Fila]);
    /// Un entero en `[desde, hasta]`, ambos incluidos.
    fn entre(&mut self, desde: usize, hasta: usize) -> usize;
}

/// Xorshift sembrado con el reloj. Barajar una cola no necesita más, y no
/// justifica una dependencia.
pub struct AzarDelSistema(u64);

impl Default for AzarDelSistema {
    fn default() -> Self {
        let semilla = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_or(0x9e37_79b9, |d| d.as_nanos() as u64);
        Self(semilla | 1)
    }
}

impl AzarDelSistema {
    fn siguiente(&mut self) -> u64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        self.0
    }
}

impl Azar for AzarDelSistema {
    fn barajar(&mut self, filas: &mut [Fila]) {
        // Fisher-Yates.
        for i in (1..filas.len()).rev() {
            let j = (self.siguiente() % (i as u64 + 1)) as usize;
            filas.swap(i, j);
        }
    }

    fn entre(&mut self, desde: usize, hasta: usize) -> usize {
        desde + (self.siguiente() % (hasta - desde + 1) as u64) as usize
    }
}

pub struct Cola {
    filas: Vec<Fila>,
    posicion: usize,
    /// La pista activa salió de la cola (y no, por ejemplo, de una restauración).
    activa_desde_cola: bool,
    /// El orden sin barajar, para devolverlo al quitar el aleatorio.
    base: Vec<Fila>,
    activa: Option<Fila>,
    estado: Estado,
    aleatorio: bool,
    repeticion: Repeticion,
    /// La posición a la que volver al reanudar una sesión restaurada.
    reanudar_en_seg: f64,
    azar: Box<dyn Azar>,
}

impl Default for Cola {
    fn default() -> Self {
        Self::con_azar(Box::new(AzarDelSistema::default()))
    }
}

impl Cola {
    pub fn con_azar(azar: Box<dyn Azar>) -> Self {
        Self {
            filas: Vec::new(),
            posicion: 0,
            activa_desde_cola: false,
            base: Vec::new(),
            activa: None,
            estado: Estado::Detenido,
            aleatorio: false,
            repeticion: Repeticion::Ninguno,
            reanudar_en_seg: 0.0,
            azar,
        }
    }

    // --- Lo que se lee ---------------------------------------------------------

    pub fn filas(&self) -> &[Fila] {
        &self.filas
    }

    /// La fila que suena, o `None` si la activa no salió de la cola.
    pub fn indice(&self) -> Option<usize> {
        (self.activa_desde_cola && !self.filas.is_empty()).then_some(self.posicion)
    }

    pub fn activa(&self) -> Option<Fila> {
        self.activa
    }

    pub fn estado(&self) -> Estado {
        self.estado
    }

    pub fn aleatorio(&self) -> bool {
        self.aleatorio
    }

    pub fn repeticion(&self) -> Repeticion {
        self.repeticion
    }

    /// Lo que sonará al terminar la actual, sin cambiar nada: el motor lo prepara
    /// por adelantado para encadenarlo sin hueco.
    pub fn prevista(&self) -> Option<Fila> {
        if self.repeticion == Repeticion::Uno {
            return self.activa;
        }
        if self.activa_desde_cola {
            if self.filas.is_empty() {
                return None;
            }
            let siguiente = self.posicion.min(self.filas.len() - 1) + 1;
            return match self.filas.get(siguiente) {
                Some(f) => Some(*f),
                None if self.repeticion == Repeticion::Todo => self.filas.first().copied(),
                None => None,
            };
        }
        self.filas.first().copied()
    }

    // --- Ayudas ----------------------------------------------------------------

    fn normalizar_indice(&mut self) {
        self.posicion = if self.filas.is_empty() {
            0
        } else {
            self.posicion.min(self.filas.len() - 1)
        };
    }

    fn indice_de_la_activa(&self) -> Option<usize> {
        let activa = self.activa?;
        self.filas
            .iter()
            .position(|f| f.pista_id == activa.pista_id)
    }

    fn reproducir(&mut self, fila: Fila, desde_cola: bool, desde_seg: f64) -> Accion {
        self.activa = Some(fila);
        self.activa_desde_cola = desde_cola;
        self.estado = Estado::Reproduciendo;
        Accion::Reproducir { fila, desde_seg }
    }

    fn detener(&mut self) -> Accion {
        self.estado = Estado::Detenido;
        self.activa_desde_cola = false;
        Accion::Detener
    }

    fn detener_y_limpiar(&mut self, estado: Estado) -> Accion {
        self.estado = estado;
        self.activa = None;
        self.posicion = 0;
        self.activa_desde_cola = false;
        Accion::Detener
    }

    /// La que suena primera y las demás barajadas. Con `inicial`, esa encabeza
    /// (una cola recién cargada); sin ella, la que suena.
    fn barajar(&mut self, inicial: Option<usize>) {
        if self.filas.len() <= 1 {
            self.normalizar_indice();
            return;
        }
        let primera = match inicial {
            Some(i) => i.min(self.filas.len() - 1),
            None if !self.activa_desde_cola => {
                self.azar.barajar(&mut self.filas);
                self.posicion = 0;
                return;
            }
            None => self
                .indice_de_la_activa()
                .unwrap_or(self.posicion)
                .min(self.filas.len() - 1),
        };
        let actual = self.filas.remove(primera);
        self.azar.barajar(&mut self.filas);
        self.filas.insert(0, actual);
        self.posicion = 0;
    }

    // --- Operaciones -----------------------------------------------------------

    /// Una pista elegida suelta: pasa a ser la única fila de la cola.
    pub fn reproducir_pista(&mut self, fila: Fila) -> Accion {
        self.filas = vec![fila];
        self.posicion = 0;
        self.base = self.filas.clone();
        self.reproducir(fila, true, 0.0)
    }

    /// Sustituye la cola y empieza por `desde`. Con aleatorio, `desde` encabeza la
    /// baraja: es la pista que el usuario eligió (regresión del 2026-10-29).
    pub fn reproducir_cola(&mut self, filas: Vec<Fila>, desde: usize) -> Accion {
        self.filas = filas;
        self.base = self.filas.clone();
        self.posicion = desde.min(self.filas.len().saturating_sub(1));
        if self.aleatorio {
            self.barajar(Some(self.posicion));
        }
        match self.filas.get(self.posicion).copied() {
            Some(f) => self.reproducir(f, true, 0.0),
            None => Accion::Nada,
        }
    }

    /// Salta a una fila sin reordenar. `None` si el índice no existe.
    pub fn reproducir_indice(&mut self, indice: usize) -> Option<Accion> {
        let fila = *self.filas.get(indice)?;
        self.posicion = indice;
        Some(self.reproducir(fila, true, 0.0))
    }

    /// Al final, o detrás de la que suena con `justo_despues`. Con aleatorio, en
    /// un sitio al azar de lo que queda por sonar.
    pub fn agregar(&mut self, fila: Fila, justo_despues: bool) {
        let inicio = if self.activa_desde_cola {
            self.posicion + 1
        } else {
            0
        };
        if justo_despues {
            self.filas.insert(inicio.min(self.filas.len()), fila);
            // En el orden base, detrás de la activa si está; si no, al principio.
            match self
                .activa
                .and_then(|a| self.base.iter().position(|f| f.pista_id == a.pista_id))
            {
                Some(i) => self.base.insert(i + 1, fila),
                None if self.base.is_empty() => self.base.push(fila),
                None => self.base.insert(0, fila),
            }
        } else if self.aleatorio && !self.filas.is_empty() {
            self.normalizar_indice();
            let inicio = inicio.min(self.filas.len());
            let donde = self.azar.entre(inicio, self.filas.len());
            self.filas.insert(donde, fila);
            self.base.push(fila);
        } else {
            self.filas.push(fila);
            self.base.push(fila);
        }
    }

    pub fn agregar_varias(&mut self, filas: &[Fila]) {
        for f in filas {
            self.agregar(*f, false);
        }
    }

    /// Vacía la cola; lo que suena sigue sonando.
    pub fn limpiar(&mut self) {
        self.filas.clear();
        self.base.clear();
        self.posicion = 0;
        self.activa_desde_cola = false;
    }

    /// Vacía la cola salvo la fila que suena.
    pub fn vaciar_salvo_la_actual(&mut self) -> Accion {
        let actual = self
            .activa_desde_cola
            .then(|| self.filas.get(self.posicion).copied())
            .flatten();
        match actual {
            Some(f) => {
                self.filas = vec![f];
                self.base = self.filas.clone();
                self.posicion = 0;
                Accion::Nada
            }
            None => {
                self.limpiar();
                Accion::Nada
            }
        }
    }

    pub fn mover(&mut self, desde: usize, hasta: usize) {
        if desde >= self.filas.len() || hasta >= self.filas.len() {
            return;
        }
        let fila = self.filas.remove(desde);
        self.filas.insert(hasta, fila);
        if self.activa_desde_cola {
            if desde == self.posicion {
                self.posicion = hasta;
            } else if desde < self.posicion && self.posicion <= hasta {
                self.posicion -= 1;
            } else if hasta <= self.posicion && self.posicion < desde {
                self.posicion += 1;
            }
        } else {
            self.posicion = 0;
        }
        self.base = self.filas.clone();
    }

    /// Quita una fila. Si era la que sonaba, suena la que ocupa su sitio, o la
    /// anterior si era la última; si no queda ninguna, se detiene y se limpia.
    pub fn quitar(&mut self, indice: usize) -> Accion {
        if indice >= self.filas.len() {
            return Accion::Nada;
        }
        let mut era_la_activa = self.activa_desde_cola && indice == self.posicion;
        let quitada = self.filas.remove(indice);
        if !era_la_activa && !self.activa_desde_cola {
            era_la_activa = self.activa.is_some_and(|a| a.pista_id == quitada.pista_id);
        }
        if let Some(i) = self
            .base
            .iter()
            .position(|f| f.pista_id == quitada.pista_id)
        {
            self.base.remove(i);
        }
        if self.filas.is_empty() {
            self.posicion = 0;
            self.activa_desde_cola = false;
            return if era_la_activa {
                self.detener_y_limpiar(Estado::Detenido)
            } else {
                Accion::Nada
            };
        }
        if era_la_activa {
            self.posicion = indice.min(self.filas.len() - 1);
            let fila = self.filas[self.posicion];
            return self.reproducir(fila, true, 0.0);
        }
        if indice < self.posicion {
            self.posicion -= 1;
        }
        self.normalizar_indice();
        Accion::Nada
    }

    /// Quita todas las apariciones de una pista: la que se borra de la biblioteca.
    pub fn purgar(&mut self, pista_id: i64) -> Accion {
        let mut accion = Accion::Nada;
        while let Some(i) = self.filas.iter().position(|f| f.pista_id == pista_id) {
            let a = self.quitar(i);
            if a != Accion::Nada {
                accion = a;
            }
        }
        if !self.activa_desde_cola && self.activa.is_some_and(|a| a.pista_id == pista_id) {
            accion = self.detener_y_limpiar(Estado::Detenido);
        }
        accion
    }

    pub fn pausar_reanudar(&mut self) -> Accion {
        match self.estado {
            Estado::Reproduciendo => {
                self.estado = Estado::Pausado;
                Accion::Pausar
            }
            Estado::Pausado => {
                self.estado = Estado::Reproduciendo;
                Accion::Reanudar
            }
            _ if !self.filas.is_empty() => {
                self.normalizar_indice();
                let fila = self.filas[self.posicion];
                let desde = std::mem::take(&mut self.reanudar_en_seg);
                self.reproducir(fila, true, desde)
            }
            _ => match self.activa {
                Some(fila) => {
                    let desde = std::mem::take(&mut self.reanudar_en_seg);
                    self.reproducir(fila, false, desde)
                }
                None => Accion::Nada,
            },
        }
    }

    pub fn siguiente(&mut self) -> Accion {
        if self.filas.is_empty() {
            return match self.activa {
                Some(f) if self.repeticion == Repeticion::Uno => self.reproducir(f, false, 0.0),
                Some(_) => self.detener(),
                None => Accion::Nada,
            };
        }
        self.normalizar_indice();
        if self.repeticion == Repeticion::Uno {
            let f = self.filas[self.posicion];
            return self.reproducir(f, true, 0.0);
        }
        if !self.activa_desde_cola {
            self.posicion = 0;
            let f = self.filas[0];
            return self.reproducir(f, true, 0.0);
        }
        let mut siguiente = self.posicion + 1;
        if siguiente >= self.filas.len() {
            if self.repeticion == Repeticion::Todo {
                siguiente = 0;
            } else {
                return self.detener();
            }
        }
        self.posicion = siguiente;
        let f = self.filas[siguiente];
        self.reproducir(f, true, 0.0)
    }

    pub fn anterior(&mut self) -> Accion {
        if self.filas.is_empty() || !self.activa_desde_cola {
            return match self.activa {
                Some(f) => {
                    let desde_cola = self.activa_desde_cola;
                    self.reproducir(f, desde_cola, 0.0)
                }
                None => Accion::Nada,
            };
        }
        self.normalizar_indice();
        self.posicion = if self.posicion == 0 && self.repeticion == Repeticion::Todo {
            self.filas.len() - 1
        } else {
            self.posicion.saturating_sub(1)
        };
        let f = self.filas[self.posicion];
        self.reproducir(f, true, 0.0)
    }

    /// Se acabó la pista que sonaba.
    pub fn fin_de_pista(&mut self) -> Accion {
        if self.repeticion == Repeticion::Uno {
            if let Some(f) = self.activa {
                let desde_cola = self.activa_desde_cola;
                return self.reproducir(f, desde_cola, 0.0);
            }
        }
        if self.activa_desde_cola {
            if self.filas.is_empty() {
                return self.detener_y_limpiar(Estado::Finalizada);
            }
            self.normalizar_indice();
            let mut siguiente = self.posicion + 1;
            if siguiente >= self.filas.len() {
                if self.repeticion == Repeticion::Todo {
                    siguiente = 0;
                } else {
                    // Se conserva todo: la última sigue marcada y "reproducir"
                    // la vuelve a tocar.
                    self.estado = Estado::Finalizada;
                    return Accion::Detener;
                }
            }
            self.posicion = siguiente;
            let f = self.filas[siguiente];
            return self.reproducir(f, true, 0.0);
        }
        if let Some(f) = self.filas.first().copied() {
            self.posicion = 0;
            return self.reproducir(f, true, 0.0);
        }
        if self.activa.is_some() {
            self.detener_y_limpiar(Estado::Finalizada)
        } else {
            self.estado = Estado::Finalizada;
            Accion::Detener
        }
    }

    pub fn fijar_repeticion(&mut self, modo: Repeticion) {
        self.repeticion = modo;
    }

    pub fn fijar_aleatorio(&mut self, activo: bool) {
        if self.aleatorio == activo {
            return;
        }
        self.aleatorio = activo;
        if activo {
            self.barajar(None);
            return;
        }
        if self.filas == self.base {
            self.normalizar_indice();
            return;
        }
        self.filas = self.base.clone();
        if self.filas.is_empty() {
            self.posicion = 0;
            self.activa_desde_cola = false;
        } else if self.activa_desde_cola {
            match self.indice_de_la_activa() {
                Some(i) => self.posicion = i,
                None => self.normalizar_indice(),
            }
        } else {
            self.posicion = 0;
        }
    }

    /// Marca el aleatorio sin barajar: al restaurar una sesión, la cola guardada ya
    /// es la barajada. El orden de partida no se guardó, así que quitar el
    /// aleatorio deja la cola como está.
    pub fn marcar_aleatorio(&mut self) {
        self.aleatorio = true;
    }

    /// Restaura una sesión guardada sin empezar a sonar: la cola, su puntero y la
    /// posición dentro de la pista, que "reproducir" consume.
    pub fn restaurar(&mut self, filas: Vec<Fila>, posicion: usize, segundos: f64) {
        self.base = filas.clone();
        self.filas = filas;
        self.posicion = posicion;
        self.normalizar_indice();
        self.activa_desde_cola = !self.filas.is_empty();
        self.activa = self.filas.get(self.posicion).copied();
        self.reanudar_en_seg = segundos.max(0.0);
        self.estado = Estado::Detenido;
    }
}

#[cfg(test)]
mod pruebas;
