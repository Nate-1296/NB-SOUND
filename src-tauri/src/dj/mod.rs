//! El DJ Privado (Fase 6): `servicios/dj_privado/` de la V1.

pub mod azar;
pub mod constructor;
pub mod ejecutor;
pub mod embeddings;
pub mod intencion;
pub mod mezcla;
pub mod narrativa;
pub mod ontologia;
mod ontologia_datos;
pub mod planificador;
pub mod transiciones;

/// `sum()` de Python 3.12 en adelante, que suma flotantes con la compensación de
/// Neumaier: un `fold` simple difiere en la última cifra, y esas cifras deciden
/// desempates y lo que se guarda frente a la V1.
pub(crate) fn suma(valores: impl IntoIterator<Item = f64>) -> f64 {
    let (mut total, mut c) = (0.0f64, 0.0f64);
    for x in valores {
        let t = total + x;
        c += if total.abs() >= x.abs() {
            (total - t) + x
        } else {
            (x - t) + total
        };
        total = t;
    }
    if c != 0.0 && c.is_finite() {
        total += c;
    }
    total
}

/// `round(x, n)` de Python: al par sobre el valor decimal exacto del `f64`, que es
/// como `format!` redondea.
pub(crate) fn redondear(x: f64, decimales: usize) -> f64 {
    format!("{x:.decimales$}").parse().unwrap_or(x)
}

#[cfg(test)]
mod pruebas {
    #[test]
    fn la_suma_compensa_como_la_de_python() {
        assert_eq!(super::suma([0.1; 10]), 1.0);
        assert_ne!([0.1; 10].iter().fold(0.0, |a, x| a + x), 1.0);
        assert_eq!(super::suma([]), 0.0);
    }

    #[test]
    fn el_redondeo_va_al_par_sobre_el_valor_exacto() {
        // 2,675 es 2,67499999… en binario: Python da 2,67.
        assert_eq!(super::redondear(2.675, 2), 2.67);
        assert_eq!(super::redondear(0.125, 2), 0.12);
        assert_eq!(super::redondear(0.375, 2), 0.38);
    }
}
