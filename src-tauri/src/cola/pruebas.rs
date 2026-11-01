//! Las pruebas de la cola de la V1, traducidas una a una. Cada una lleva el nombre
//! de la original de `legado/tests/test_reproductor_ui_contract.py` sin el prefijo
//! `test_`, que ya describe la propiedad. Como allí,
//! barajar invierte el orden y el sitio al azar es siempre el último, para que
//! sean deterministas.

use super::*;

struct Invertir;

impl Azar for Invertir {
    fn barajar(&mut self, filas: &mut [Fila]) {
        filas.reverse();
    }

    fn entre(&mut self, _desde: usize, hasta: usize) -> usize {
        hasta
    }
}

fn cola() -> Cola {
    Cola::con_azar(Box::new(Invertir))
}

fn f(id: i64) -> Fila {
    Fila { pista_id: id }
}

fn ids(c: &Cola) -> Vec<i64> {
    c.filas().iter().map(|f| f.pista_id).collect()
}

fn activa(c: &Cola) -> Option<i64> {
    c.activa().map(|f| f.pista_id)
}

#[test]
fn siguiente_sin_cola_detiene_y_play_reanuda_pista_activa() {
    let mut c = cola();
    c.reproducir_pista(f(3));
    assert_eq!(c.siguiente(), Accion::Detener);
    assert_eq!(c.estado(), Estado::Detenido);
    c.pausar_reanudar();
    assert_eq!(c.estado(), Estado::Reproduciendo);
    assert_eq!(activa(&c), Some(3));
}

#[test]
fn anterior_en_repetir_todo_envuelve_al_final_de_la_cola() {
    let mut c = cola();
    c.reproducir_cola(vec![f(4), f(5)], 0);
    c.fijar_repeticion(Repeticion::Todo);
    c.anterior();
    assert_eq!(c.indice(), Some(1));
    assert_eq!(activa(&c), Some(5));
}

#[test]
fn aleatorio_reordena_cola_visible_y_siguiente_respeta_ese_orden() {
    let mut c = cola();
    c.reproducir_cola(vec![f(6), f(7), f(8), f(9)], 1);
    c.fijar_aleatorio(true);
    assert_eq!(ids(&c), [7, 9, 8, 6]);
    assert_eq!(c.indice(), Some(0));
    c.siguiente();
    assert_eq!(activa(&c), Some(9));
}

#[test]
fn reproducir_cola_con_aleatorio_arranca_en_la_pista_elegida() {
    let mut c = cola();
    let pistas = vec![f(1), f(2), f(3), f(4)];
    c.reproducir_cola(pistas.clone(), 0);
    c.fijar_aleatorio(true);
    assert_eq!(activa(&c), Some(1));
    c.reproducir_cola(pistas, 2);
    assert_eq!(activa(&c), Some(3));
    assert_eq!(c.indice(), Some(0));
    assert_eq!(ids(&c)[0], 3);
    let mut todas = ids(&c);
    todas.sort_unstable();
    assert_eq!(todas, [1, 2, 3, 4]);
}

#[test]
fn desactivar_aleatorio_restaura_orden_original_restante() {
    let mut c = cola();
    c.reproducir_cola(vec![f(1), f(2), f(3), f(4)], 1);
    c.fijar_aleatorio(true);
    c.fijar_aleatorio(false);
    assert_eq!(ids(&c), [1, 2, 3, 4]);
    assert_eq!(c.indice(), Some(1));
    assert_eq!(activa(&c), Some(2));
}

#[test]
fn desactivar_aleatorio_restaura_orden_base_completo() {
    let mut c = cola();
    c.reproducir_cola(vec![f(1), f(2), f(3), f(4)], 1);
    c.fijar_aleatorio(true);
    c.fin_de_pista();
    c.fijar_aleatorio(false);
    assert_eq!(ids(&c), [1, 2, 3, 4]);
    assert_eq!(c.indice(), Some(3));
    assert_eq!(activa(&c), Some(4));
}

#[test]
fn limpiar_cola_vacia_lista_sin_detener_pista_activa() {
    let mut c = cola();
    c.reproducir_cola(vec![f(1), f(2)], 0);
    c.limpiar();
    assert!(c.filas().is_empty());
    assert_eq!(c.estado(), Estado::Reproduciendo);
    assert_eq!(activa(&c), Some(1));
}

#[test]
fn vaciar_cola_mantener_actual_conserva_solo_fila_activa() {
    let mut c = cola();
    c.reproducir_cola(vec![f(1), f(2), f(3)], 1);
    c.vaciar_salvo_la_actual();
    assert_eq!(ids(&c), [2]);
    assert_eq!(c.indice(), Some(0));
    assert_eq!(c.estado(), Estado::Reproduciendo);
    assert_eq!(activa(&c), Some(2));
}

#[test]
fn vaciar_cola_mantener_actual_vacia_si_no_hay_fila_activa() {
    let mut c = cola();
    c.agregar(f(1), false);
    c.agregar(f(2), false);
    c.vaciar_salvo_la_actual();
    assert!(c.filas().is_empty());
    assert_eq!(c.indice(), None);
    assert_eq!(activa(&c), None);
    assert_eq!(c.estado(), Estado::Detenido);
}

#[test]
fn quitar_unica_pista_activa_resetea_reproductor() {
    let mut c = cola();
    c.reproducir_pista(f(1));
    assert_eq!(c.quitar(0), Accion::Detener);
    assert!(c.filas().is_empty());
    assert_eq!(activa(&c), None);
    assert_eq!(c.indice(), None);
    assert_eq!(c.estado(), Estado::Detenido);
}

#[test]
fn quitar_unica_pista_activa_pausada_resetea_reproductor() {
    let mut c = cola();
    c.reproducir_pista(f(1));
    c.pausar_reanudar();
    assert_eq!(c.estado(), Estado::Pausado);
    c.quitar(0);
    assert!(c.filas().is_empty());
    assert_eq!(activa(&c), None);
    assert_eq!(c.indice(), None);
    assert_eq!(c.estado(), Estado::Detenido);
}

#[test]
fn quitar_pista_activa_con_mas_cola_reproduce_siguiente() {
    let mut c = cola();
    c.reproducir_cola(vec![f(1), f(2), f(3)], 1);
    assert_eq!(
        c.quitar(1),
        Accion::Reproducir {
            fila: f(3),
            desde_seg: 0.0
        }
    );
    assert_eq!(ids(&c), [1, 3]);
    assert_eq!(c.indice(), Some(1));
    assert_eq!(activa(&c), Some(3));
    assert_eq!(c.estado(), Estado::Reproduciendo);
}

#[test]
fn quitar_ultima_pista_activa_con_mas_cola_reproduce_anterior() {
    let mut c = cola();
    c.reproducir_cola(vec![f(1), f(2)], 1);
    c.quitar(1);
    assert_eq!(ids(&c), [1]);
    assert_eq!(c.indice(), Some(0));
    assert_eq!(activa(&c), Some(1));
    assert_eq!(c.estado(), Estado::Reproduciendo);
}

#[test]
fn modelo_reproductor_agrega_varias_a_cola_en_una_operacion() {
    let mut c = cola();
    c.agregar_varias(&[f(1), f(2)]);
    assert_eq!(ids(&c), [1, 2]);
}

#[test]
fn modelo_quitar_unica_pista_sin_iniciar_limpia_pista_visual() {
    let mut c = cola();
    c.agregar(f(1), false);
    assert_eq!(activa(&c), None);
    assert_eq!(c.quitar(0), Accion::Nada);
    assert!(c.filas().is_empty());
    assert_eq!(activa(&c), None);
}

#[test]
fn controles_sin_pista_y_cola_vacia_no_rompen_estado() {
    let mut c = cola();
    c.pausar_reanudar();
    c.siguiente();
    c.anterior();
    c.limpiar();
    c.quitar(0);
    c.fijar_aleatorio(true);
    c.fijar_repeticion(Repeticion::Todo);
    c.siguiente();
    assert_eq!(c.estado(), Estado::Detenido);
    assert_eq!(activa(&c), None);
    assert!(c.filas().is_empty());
    assert!(c.aleatorio());
    assert_eq!(c.repeticion(), Repeticion::Todo);
}

#[test]
fn repetir_uno_no_consume_cola_al_finalizar() {
    let mut c = cola();
    c.reproducir_cola(vec![f(1), f(2)], 0);
    c.fijar_repeticion(Repeticion::Uno);
    c.fin_de_pista();
    assert_eq!(ids(&c), [1, 2]);
    assert_eq!(c.indice(), Some(0));
    assert_eq!(c.estado(), Estado::Reproduciendo);
    assert_eq!(activa(&c), Some(1));
}

#[test]
fn repetir_todo_cicla_al_terminar_ultima_pista() {
    let mut c = cola();
    c.reproducir_cola(vec![f(1), f(2)], 0);
    c.fijar_repeticion(Repeticion::Todo);
    c.fin_de_pista();
    c.fin_de_pista();
    assert_eq!(ids(&c), [1, 2]);
    assert_eq!(c.indice(), Some(0));
    assert_eq!(c.estado(), Estado::Reproduciendo);
    assert_eq!(activa(&c), Some(1));
}

#[test]
fn repetir_todo_no_revive_contexto_tras_limpiar_cola() {
    let mut c = cola();
    c.reproducir_cola(vec![f(1), f(2)], 0);
    c.fijar_repeticion(Repeticion::Todo);
    c.limpiar();
    c.fin_de_pista();
    assert!(c.filas().is_empty());
    assert_eq!(c.indice(), None);
    assert_eq!(activa(&c), None);
    assert_eq!(c.estado(), Estado::Finalizada);
}

#[test]
fn repetir_todo_contexto_respeta_reorden_manual() {
    let mut c = cola();
    c.reproducir_cola(vec![f(1), f(2), f(3)], 1);
    c.mover(2, 0);
    c.fijar_repeticion(Repeticion::Todo);
    c.fin_de_pista();
    c.fin_de_pista();
    c.fin_de_pista();
    assert_eq!(ids(&c), [3, 1, 2]);
    assert_eq!(c.indice(), Some(2));
    assert_eq!(activa(&c), Some(2));
}

#[test]
fn repetir_todo_no_reintroduce_pista_quitada() {
    let mut c = cola();
    c.reproducir_cola(vec![f(1), f(2), f(3)], 0);
    c.quitar(1);
    c.fijar_repeticion(Repeticion::Todo);
    c.fin_de_pista();
    c.fin_de_pista();
    assert_eq!(ids(&c), [1, 3]);
    assert_eq!(activa(&c), Some(1));
}

#[test]
fn reproducir_pista_individual_reemplaza_cola_previa() {
    let mut c = cola();
    c.agregar(f(2), false);
    c.agregar(f(3), false);
    c.reproducir_pista(f(1));
    assert_eq!(ids(&c), [1]);
    assert_eq!(c.indice(), Some(0));
    assert_eq!(activa(&c), Some(1));
}

#[test]
fn modelo_reproducir_pista_individual_actualiza_cola_visible() {
    let mut c = cola();
    c.reproducir_pista(f(1));
    assert_eq!(ids(&c), [1]);
    assert_eq!(c.indice(), Some(0));
}

#[test]
fn reproducir_pista_existente_en_cola_reemplaza_sin_duplicar() {
    let mut c = cola();
    c.agregar(f(1), false);
    c.agregar(f(2), false);
    c.agregar(f(3), false);
    c.reproducir_pista(f(2));
    assert_eq!(ids(&c), [2]);
    assert_eq!(c.indice(), Some(0));
    assert_eq!(activa(&c), Some(2));
}

#[test]
fn reproducir_cola_conserva_contexto_completo() {
    let mut c = cola();
    c.reproducir_cola(vec![f(1), f(2), f(3)], 1);
    assert_eq!(ids(&c), [1, 2, 3]);
    assert_eq!(c.indice(), Some(1));
    assert_eq!(activa(&c), Some(2));
}

#[test]
fn reproductor_avanza_en_cola_al_finalizar_sin_consumir() {
    let mut c = cola();
    c.reproducir_cola(vec![f(1), f(2)], 0);
    c.fin_de_pista();
    assert_eq!(ids(&c), [1, 2]);
    assert_eq!(c.indice(), Some(1));
    assert_eq!(activa(&c), Some(2));
}

#[test]
fn reproductor_detiene_conservando_pista_al_terminar_ultima() {
    let mut c = cola();
    c.agregar(f(1), false);
    c.agregar(f(2), false);
    c.reproducir_pista(f(9));
    assert_eq!(c.fin_de_pista(), Accion::Detener);
    assert_eq!(ids(&c), [9]);
    assert_eq!(c.indice(), Some(0));
    assert_eq!(activa(&c), Some(9));
    assert_eq!(c.estado(), Estado::Finalizada);
}

#[test]
fn reproductor_avanza_a_pista_anadida_conservando_individual() {
    let mut c = cola();
    c.reproducir_pista(f(9));
    c.agregar(f(1), false);
    c.agregar(f(2), false);
    c.fin_de_pista();
    assert_eq!(ids(&c), [9, 1, 2]);
    assert_eq!(c.indice(), Some(1));
    assert_eq!(activa(&c), Some(1));
}

#[test]
fn reproducir_indice_cola_reproduce_sin_reconstruir_orden() {
    let mut c = cola();
    c.reproducir_cola(vec![f(1), f(2), f(3)], 0);
    assert!(c.reproducir_indice(2).is_some());
    assert_eq!(ids(&c), [1, 2, 3]);
    assert_eq!(c.indice(), Some(2));
    assert_eq!(activa(&c), Some(3));
}

#[test]
fn reproducir_indice_cola_invalido_no_cambia_estado() {
    let mut c = cola();
    c.reproducir_cola(vec![f(1), f(2)], 1);
    assert!(c.reproducir_indice(9).is_none());
    assert_eq!(ids(&c), [1, 2]);
    assert_eq!(c.indice(), Some(1));
    assert_eq!(activa(&c), Some(2));
}

#[test]
fn mover_en_cola_reordena_y_preserva_indice_activo() {
    let mut c = cola();
    c.reproducir_cola(vec![f(1), f(2), f(3)], 1);
    c.mover(2, 0);
    assert_eq!(ids(&c), [3, 1, 2]);
    assert_eq!(c.indice(), Some(2));
    assert_eq!(activa(&c), Some(2));
}

// --- Propiedades de la V2 ------------------------------------------------------

#[test]
fn lo_previsto_es_lo_que_sonara_al_acabar_la_pista() {
    for repeticion in [Repeticion::Ninguno, Repeticion::Todo, Repeticion::Uno] {
        for desde in 0..3 {
            let mut c = cola();
            c.fijar_repeticion(repeticion);
            c.reproducir_cola(vec![f(1), f(2), f(3)], desde);
            let prevista = c.prevista();
            let accion = c.fin_de_pista();
            let sonara = match accion {
                Accion::Reproducir { fila, .. } => Some(fila),
                _ => None,
            };
            assert_eq!(prevista, sonara, "{repeticion:?} desde {desde}");
        }
    }
}

#[test]
fn restaurar_una_sesion_no_suena_hasta_reproducir_y_vuelve_a_su_segundo() {
    let mut c = cola();
    c.restaurar(vec![f(1), f(2), f(3)], 1, 42.5);
    assert_eq!(c.estado(), Estado::Detenido);
    assert_eq!(activa(&c), Some(2));
    assert_eq!(
        c.pausar_reanudar(),
        Accion::Reproducir {
            fila: f(2),
            desde_seg: 42.5
        }
    );
    c.pausar_reanudar();
    c.siguiente();
    assert_eq!(
        activa(&c),
        Some(3),
        "el segundo guardado se consume una vez"
    );
}

#[test]
fn purgar_una_pista_borrada_la_quita_de_todas_partes() {
    let mut c = cola();
    c.reproducir_cola(vec![f(1), f(2), f(1), f(3)], 0);
    let accion = c.purgar(1);
    assert_eq!(ids(&c), [2, 3]);
    assert!(matches!(accion, Accion::Reproducir { .. }));
    assert_ne!(activa(&c), Some(1));
}

#[test]
fn el_azar_del_sistema_baraja_sin_perder_filas() {
    let mut azar = AzarDelSistema::default();
    let mut filas: Vec<Fila> = (0..50).map(f).collect();
    azar.barajar(&mut filas);
    let mut ordenadas: Vec<i64> = filas.iter().map(|f| f.pista_id).collect();
    assert_ne!(
        ordenadas,
        (0..50).collect::<Vec<_>>(),
        "con 50 filas, barajar cambia algo"
    );
    ordenadas.sort_unstable();
    assert_eq!(ordenadas, (0..50).collect::<Vec<_>>());
    for _ in 0..100 {
        let x = azar.entre(3, 7);
        assert!((3..=7).contains(&x));
    }
}
