//! La prioridad de los hilos de fondo (enmienda de ADR-002, 2026-11-05).
//!
//! El karaoke, el análisis, la sonoridad, los vectores del DJ, la auditoría y la
//! copia automática trabajan sin que nadie los espere: solo
//! deben usar lo que el equipo no está usando. Antes corrían a prioridad normal y,
//! mientras se preparaba una canción, competían de igual a igual con la interfaz,
//! con el audio y con el resto del escritorio.
//!
//! Se llama desde el propio hilo, antes de crear sus sesiones de ONNX Runtime:
//! los hilos que crea la sesión heredan la prioridad.

/// Baja la prioridad del hilo que llama. Si el sistema no lo permite, sigue igual.
pub fn bajar_hilo_actual() {
    #[cfg(target_os = "linux")]
    {
        // En Linux la prioridad `nice` es de cada hilo: `PRIO_PROCESS` con el id del
        // hilo solo cambia este.
        // SAFETY: `gettid` y `setpriority` no reciben punteros y no pueden dejar
        // memoria en mal estado; un fallo solo devuelve -1.
        let resultado = unsafe {
            let hilo = libc::gettid();
            libc::setpriority(libc::PRIO_PROCESS, hilo as libc::id_t, 19)
        };
        if resultado != 0 {
            tracing::debug!("no se pudo bajar la prioridad de un hilo de fondo");
        }
        // Y la del disco: la copia automática lee y escribe gigas al abrir y, con
        // la del procesador baja pero el disco a la par, la canción que sonaba a
        // la vez se entrecortaba (Nathan, la primera apertura del día). La clase
        // ociosa solo usa el disco cuando nadie más lo pide.
        const IOPRIO_WHO_PROCESS: libc::c_long = 1;
        const IOPRIO_CLASS_IDLE: libc::c_long = 3;
        const IOPRIO_CLASS_SHIFT: libc::c_long = 13;
        // SAFETY: `ioprio_set` recibe tres enteros; un fallo solo devuelve -1.
        let disco = unsafe {
            libc::syscall(
                libc::SYS_ioprio_set,
                IOPRIO_WHO_PROCESS,
                libc::c_long::from(libc::gettid()),
                IOPRIO_CLASS_IDLE << IOPRIO_CLASS_SHIFT,
            )
        };
        if disco != 0 {
            tracing::debug!("no se pudo bajar la prioridad de disco de un hilo de fondo");
        }
    }
    #[cfg(target_os = "macos")]
    {
        // SAFETY: cambia la clase de servicio del hilo actual; no recibe punteros.
        let resultado =
            unsafe { libc::pthread_set_qos_class_self_np(libc::qos_class_t::QOS_CLASS_UTILITY, 0) };
        if resultado != 0 {
            tracing::debug!("no se pudo bajar la prioridad de un hilo de fondo");
        }
    }
}

#[cfg(all(test, target_os = "linux"))]
mod tests {
    #[test]
    fn el_hilo_de_fondo_queda_con_prioridad_baja_y_los_demas_no() {
        let principal = unsafe { libc::getpriority(libc::PRIO_PROCESS, 0) };
        let en_el_hilo = std::thread::spawn(|| {
            super::bajar_hilo_actual();
            // Uno creado desde él la hereda, como los de ONNX Runtime.
            let heredada = std::thread::spawn(|| unsafe {
                libc::getpriority(libc::PRIO_PROCESS, libc::gettid() as libc::id_t)
            })
            .join()
            .unwrap();
            let propia =
                unsafe { libc::getpriority(libc::PRIO_PROCESS, libc::gettid() as libc::id_t) };
            (propia, heredada)
        })
        .join()
        .unwrap();
        assert_eq!(en_el_hilo, (19, 19));
        assert_eq!(
            unsafe { libc::getpriority(libc::PRIO_PROCESS, 0) },
            principal,
            "el resto de la aplicación no cambia"
        );
    }
}
