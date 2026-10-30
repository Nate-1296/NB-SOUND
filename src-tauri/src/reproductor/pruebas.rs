//! El servicio entero sobre la salida fuera de línea: pistas de verdad (WAV) en una
//! base de verdad, renderizando hasta que la cola se acaba.

use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use super::*;
use crate::audio::pruebas::{motor, renderizar, ruido, wav, Offline};

#[derive(Default, Clone)]
struct Apuntes {
    instantaneas: Arc<Mutex<Vec<Instantanea>>>,
    avisos: Arc<Mutex<Vec<AvisoReproductor>>>,
}

impl Oyente for Apuntes {
    fn instantanea(&self, i: &Instantanea) {
        self.instantaneas.lock().unwrap().push(i.clone());
    }
    fn aviso(&self, a: &AvisoReproductor) {
        self.avisos.lock().unwrap().push(a.clone());
    }
}

struct Escenario {
    dir: PathBuf,
    db: BaseDeDatos,
}

impl Drop for Escenario {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.dir);
    }
}

fn escenario(nombre: &str, pistas: &[(i64, usize)]) -> Escenario {
    let dir = std::env::temp_dir().join(format!("ns-reproductor-{nombre}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let db = BaseDeDatos::en_memoria().unwrap();
    let conn = db.conexion().unwrap();
    conn.execute(
        "INSERT INTO artistas (id, nombre, clave) VALUES (1, 'a', 'a')",
        [],
    )
    .unwrap();
    for (id, frames) in pistas {
        let ruta = dir.join(format!("{id}.wav"));
        let _ = wav(&ruta, 44_100, *frames, ruido(*id as u32));
        conn.execute(
            "INSERT INTO pistas (id, artista_id, titulo, artista_nombre, ruta, duracion_seg)
             VALUES (?1, 1, ?2, 'a', ?3, ?4)",
            rusqlite::params![
                id,
                format!("pista {id}"),
                ruta.to_string_lossy(),
                *frames as f64 / 44_100.0
            ],
        )
        .unwrap();
    }
    drop(conn);
    Escenario { dir, db }
}

fn servicio(e: &Escenario, apuntes: &Apuntes) -> Servicio<Offline> {
    Servicio::nuevo(
        motor(44_100),
        Cola::default(),
        e.db.clone(),
        e.dir.join("stems"),
        Box::new(apuntes.clone()),
    )
    .unwrap()
}

/// Renderiza y atiende al motor hasta que se cumple `hasta` o pasan 20 s.
fn correr(s: &mut Servicio<Offline>, hasta: impl Fn(&Servicio<Offline>) -> bool) {
    let limite = Instant::now() + Duration::from_secs(20);
    while !hasta(s) && Instant::now() < limite {
        let _ = renderizar(s.motor(), 2_048);
        std::thread::sleep(Duration::from_millis(2));
        s.atender_motor();
    }
}

fn cuenta(db: &BaseDeDatos, sql: &str) -> i64 {
    db.conexion()
        .unwrap()
        .query_row(sql, [], |f| f.get(0))
        .unwrap()
}

#[test]
fn una_cola_suena_entera_y_cada_pista_queda_en_el_historial() {
    let e = escenario("entera", &[(1, 20_000), (2, 15_000), (3, 10_000)]);
    let apuntes = Apuntes::default();
    let mut s = servicio(&e, &apuntes);
    s.atender(Orden::ReproducirPistas {
        ids: vec![1, 2, 3],
        desde: 0,
    });
    assert_eq!(s.instantanea().estado, "reproduciendo");
    correr(&mut s, |s| s.instantanea().estado == "finalizada");
    let i = s.instantanea();
    assert_eq!(i.estado, "finalizada");
    assert_eq!(i.pista_id, Some(3), "la última sigue marcada");
    assert_eq!(i.indice_cola, Some(2));
    assert_eq!(
        cuenta(&e.db, "SELECT count(*) FROM historial WHERE completada = 1"),
        3
    );
    assert_eq!(cuenta(&e.db, "SELECT sum(reproducciones) FROM pistas"), 3);
    // La interfaz vio pasar las tres.
    let vistas: Vec<Option<i64>> = apuntes
        .instantaneas
        .lock()
        .unwrap()
        .iter()
        .map(|i| i.pista_id)
        .collect();
    for id in [1, 2, 3] {
        assert!(vistas.contains(&Some(id)), "{id}");
    }
}

#[test]
fn la_sesion_se_restaura_al_volver_a_abrir() {
    let e = escenario("sesion", &[(1, 44_100 * 3), (2, 10_000), (3, 10_000)]);
    let apuntes = Apuntes::default();
    {
        let mut s = servicio(&e, &apuntes);
        s.atender(Orden::ReproducirPistas {
            ids: vec![1, 2, 3],
            desde: 0,
        });
        s.atender(Orden::Volumen(0.4));
        s.atender(Orden::Repeticion(Repeticion::Todo));
        correr(&mut s, |s| s.instantanea().posicion_seg > 0.5);
        s.guardar_al_cerrar();
    }
    let s = servicio(&e, &apuntes);
    let i = s.instantanea();
    assert_eq!(i.cola, [1, 2, 3]);
    assert_eq!(i.estado, "detenido", "restaurar no empieza a sonar");
    assert_eq!(i.volumen, 0.4);
    assert_eq!(i.repeticion, "todo");
    let segundo: f64 =
        e.db.conexion()
            .unwrap()
            .query_row("SELECT posicion_seg FROM estado_reproductor", [], |f| {
                f.get(0)
            })
            .unwrap();
    assert!(segundo > 0.4, "{segundo}");
}

#[test]
fn una_pista_cuyo_archivo_falta_se_avisa_y_se_salta() {
    let e = escenario("falta", &[(1, 10_000), (2, 10_000)]);
    std::fs::remove_file(e.dir.join("1.wav")).unwrap();
    let apuntes = Apuntes::default();
    let mut s = servicio(&e, &apuntes);
    s.atender(Orden::ReproducirPistas {
        ids: vec![1, 2],
        desde: 0,
    });
    correr(&mut s, |s| s.instantanea().estado == "finalizada");
    let avisos = apuntes.avisos.lock().unwrap();
    assert!(avisos
        .iter()
        .any(|a| a.codigo == "FILE_NOT_FOUND" && a.pista_id == Some(1)));
    assert_eq!(
        cuenta(&e.db, "SELECT count(*) FROM historial WHERE pista_id = 2"),
        1
    );
}

#[test]
fn una_pista_que_ya_no_esta_en_la_base_se_avisa_sin_romper_nada() {
    let e = escenario("sin-fila", &[(1, 10_000)]);
    let apuntes = Apuntes::default();
    let mut s = servicio(&e, &apuntes);
    s.atender(Orden::ReproducirPista(99));
    assert!(apuntes
        .avisos
        .lock()
        .unwrap()
        .iter()
        .any(|a| a.pista_id == Some(99)));
    s.atender(Orden::ReproducirPista(1));
    assert_eq!(s.instantanea().estado, "reproduciendo");
}

#[test]
fn buscar_fuera_de_rango_se_acota_a_la_duracion() {
    let e = escenario("buscar", &[(1, 44_100 * 2)]);
    let apuntes = Apuntes::default();
    let mut s = servicio(&e, &apuntes);
    s.atender(Orden::ReproducirPista(1));
    correr(&mut s, |s| s.instantanea().posicion_seg > 0.0);
    s.atender(Orden::Buscar(-5.0));
    correr(&mut s, |s| s.instantanea().posicion_seg < 0.5);
    assert!(s.instantanea().posicion_seg < 0.5);
}

#[test]
fn el_ecualizador_elegido_se_guarda_en_las_preferencias() {
    let e = escenario("eq", &[(1, 1_000)]);
    let apuntes = Apuntes::default();
    let mut s = servicio(&e, &apuntes);
    s.atender(Orden::Ecualizador(AjustesEcualizador {
        activo: true,
        preseleccion: Some(13),
        bandas: crate::audio::ecualizador::PRESELECCIONES[13].bandas_db,
        preamp: 5.0,
    }));
    let conn = e.db.conexion().unwrap();
    let leido = persistencia::leer_ecualizador(&conn).unwrap();
    assert!(leido.activo);
    assert_eq!(leido.preseleccion, Some(13));
}

#[test]
fn las_preferencias_de_la_v1_se_leen_tal_como_las_dejo_el_importador() {
    let e = escenario("eq-v1", &[]);
    e.db.conexion()
        .unwrap()
        .execute_batch(
            "INSERT INTO preferencias (clave, valor) VALUES
                 ('ecualizador_activo', 'true'), ('ecualizador_preajuste', '\"11\"'),
                 ('ecualizador_bandas', '[-1.6,4.8,7.2,8,5.6,0,-2.4,-2.4,-1.6,-1.6]'),
                 ('ecualizador_preamplificacion', '6');",
        )
        .unwrap();
    let a = persistencia::leer_ecualizador(&e.db.conexion().unwrap()).unwrap();
    assert_eq!(a.preseleccion, Some(11));
    assert_eq!(a.bandas[1], 4.8);
    assert_eq!(a.preamp, 6.0);
}

#[test]
fn recargar_trae_la_sesion_que_dejo_el_importador_si_no_suena_nada() {
    let e = escenario("recargar", &[(1, 1_000), (2, 1_000)]);
    let apuntes = Apuntes::default();
    let mut s = servicio(&e, &apuntes);
    assert!(s.instantanea().cola.is_empty());
    e.db.conexion()
        .unwrap()
        .execute_batch(
            "INSERT INTO cola (posicion, pista_id) VALUES (0, 2), (1, 1);
             UPDATE estado_reproductor SET volumen = 0.25;",
        )
        .unwrap();
    s.atender(Orden::Recargar);
    assert_eq!(s.instantanea().cola, [2, 1]);
    assert_eq!(s.instantanea().volumen, 0.25);
}

#[test]
fn una_cola_de_pistas_muy_cortas_suena_entera_sin_saltarse_ninguna() {
    let pistas: Vec<(i64, usize)> = (1..=6).map(|id| (id, 900)).collect();
    let e = escenario("cortas", &pistas);
    let apuntes = Apuntes::default();
    let mut s = servicio(&e, &apuntes);
    s.atender(Orden::ReproducirPistas {
        ids: (1..=6).collect(),
        desde: 0,
    });
    correr(&mut s, |s| s.instantanea().estado == "finalizada");
    assert_eq!(s.instantanea().pista_id, Some(6));
    assert_eq!(cuenta(&e.db, "SELECT count(*) FROM historial"), 6);
    assert_eq!(
        cuenta(&e.db, "SELECT count(DISTINCT pista_id) FROM historial"),
        6
    );
}
