//! El azar del DJ: `random.Random` de Python, bit a bit.
//!
//! La V1 desempata con `random.Random(semilla).uniform(-0.001, 0.001)`, y una sesión
//! con semilla tiene que salir igual en la V2 (criterio de la Fase 6). Por eso se
//! escribe aquí el Mersenne Twister de CPython (MT19937 sembrado con
//! `init_by_array` sobre las palabras de 32 bits del valor absoluto de la semilla)
//! en vez de usar un generador de una dependencia, que daría otra secuencia.

const N: usize = 624;
const M: usize = 397;

pub struct Azar {
    estado: [u32; N],
    indice: usize,
}

impl Azar {
    /// `random.Random(semilla)` con un entero: el signo no cuenta.
    #[must_use]
    pub fn con_semilla(semilla: i64) -> Self {
        let mut n = u128::from(semilla.unsigned_abs());
        let mut clave = Vec::new();
        while n > 0 {
            clave.push((n & 0xffff_ffff) as u32);
            n >>= 32;
        }
        if clave.is_empty() {
            clave.push(0);
        }
        Self::por_clave(&clave)
    }

    /// `random.Random(None)`: una semilla que cambia en cada sesión.
    #[must_use]
    pub fn sin_semilla() -> Self {
        use std::hash::{BuildHasher, Hasher};
        // `RandomState` ya trae entropía del sistema; no hace falta otra dependencia
        // para un desempate de una milésima.
        let mut h = std::collections::hash_map::RandomState::new().build_hasher();
        h.write_u64(
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map_or(0, |d| d.as_nanos() as u64),
        );
        let x = h.finish();
        Self::por_clave(&[x as u32, (x >> 32) as u32])
    }

    fn por_clave(clave: &[u32]) -> Self {
        let mut a = Self::por_entero(19_650_218);
        let mt = &mut a.estado;
        let (mut i, mut j) = (1usize, 0usize);
        for _ in 0..N.max(clave.len()) {
            mt[i] = (mt[i] ^ (mt[i - 1] ^ (mt[i - 1] >> 30)).wrapping_mul(1_664_525))
                .wrapping_add(clave[j])
                .wrapping_add(j as u32);
            i += 1;
            j += 1;
            if i >= N {
                mt[0] = mt[N - 1];
                i = 1;
            }
            if j >= clave.len() {
                j = 0;
            }
        }
        for _ in 0..N - 1 {
            mt[i] = (mt[i] ^ (mt[i - 1] ^ (mt[i - 1] >> 30)).wrapping_mul(1_566_083_941))
                .wrapping_sub(i as u32);
            i += 1;
            if i >= N {
                mt[0] = mt[N - 1];
                i = 1;
            }
        }
        mt[0] = 0x8000_0000;
        a
    }

    fn por_entero(s: u32) -> Self {
        let mut estado = [0u32; N];
        estado[0] = s;
        for i in 1..N {
            estado[i] = 1_812_433_253u32
                .wrapping_mul(estado[i - 1] ^ (estado[i - 1] >> 30))
                .wrapping_add(i as u32);
        }
        Self { estado, indice: N }
    }

    fn siguiente(&mut self) -> u32 {
        if self.indice >= N {
            let mt = &mut self.estado;
            for k in 0..N {
                let y = (mt[k] & 0x8000_0000) | (mt[(k + 1) % N] & 0x7fff_ffff);
                let mag = if y & 1 == 0 { 0 } else { 0x9908_b0df };
                mt[k] = mt[(k + M) % N] ^ (y >> 1) ^ mag;
            }
            self.indice = 0;
        }
        let mut y = self.estado[self.indice];
        self.indice += 1;
        y ^= y >> 11;
        y ^= (y << 7) & 0x9d2c_5680;
        y ^= (y << 15) & 0xefc6_0000;
        y ^ (y >> 18)
    }

    /// `random()`: 53 bits en `[0, 1)`.
    pub fn real(&mut self) -> f64 {
        let a = f64::from(self.siguiente() >> 5);
        let b = f64::from(self.siguiente() >> 6);
        (a * 67_108_864.0 + b) / 9_007_199_254_740_992.0
    }

    /// `uniform(a, b)`.
    pub fn uniforme(&mut self, a: f64, b: f64) -> f64 {
        a + (b - a) * self.real()
    }
}

#[cfg(test)]
mod pruebas {
    use super::*;

    fn doradas() -> serde_json::Value {
        serde_json::from_str(include_str!("doradas_sesion.json")).expect("doradas")
    }

    #[test]
    fn la_secuencia_es_la_de_python_para_cada_semilla() {
        let d = doradas();
        for (semilla, esperada) in d["azar"].as_object().expect("azar") {
            let Ok(s) = semilla.parse::<i64>() else {
                continue;
            };
            let mut a = Azar::con_semilla(s);
            let esperada: Vec<f64> = serde_json::from_value(esperada.clone()).expect("lista");
            for v in &esperada[..5] {
                assert_eq!(a.real().to_bits(), v.to_bits(), "semilla {semilla}");
            }
            assert_eq!(a.uniforme(-0.001, 0.001).to_bits(), esperada[5].to_bits());
        }
    }

    #[test]
    fn el_signo_de_la_semilla_no_cambia_la_secuencia() {
        let (mut a, mut b) = (Azar::con_semilla(42), Azar::con_semilla(-42));
        assert_eq!(a.real().to_bits(), b.real().to_bits());
    }
}
