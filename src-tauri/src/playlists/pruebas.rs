use super::*;

fn base() -> BaseDeDatos {
    let db = BaseDeDatos::en_memoria().unwrap();
    db.conexion()
        .unwrap()
        .execute_batch(
            "INSERT INTO artistas (id, nombre, clave) VALUES (1, 'a', 'a');
             INSERT INTO pistas (id, artista_id, titulo, ruta, duracion_seg) VALUES
                 (1, 1, 'uno', 'x1', 100), (2, 1, 'dos', 'x2', 100), (3, 1, 'tres', 'x3', 100);
             INSERT INTO playlists (id, nombre, tipo, subtipo, origen, clave_auto) VALUES
                 (50, 'Rápidas', 'automatica', 'mood', 'generado', 'mood:rapidas');",
        )
        .unwrap();
    db
}

fn todas(db: &BaseDeDatos) -> Vec<PlaylistResumen> {
    listar(
        db,
        &ConsultaPlaylists {
            texto: None,
            categoria: None,
            orden: OrdenPlaylists::NombreAsc,
        },
    )
    .unwrap()
}

#[test]
fn la_clasificacion_es_la_que_envia_la_v1_al_movil() {
    assert_eq!(
        clasificar("sistema", Some("favoritos"), "sistema"),
        (Categoria::MeGusta, "Me gusta")
    );
    assert_eq!(
        clasificar("manual", Some("usuario"), "usuario"),
        (Categoria::Creada, "Manual")
    );
    assert_eq!(
        clasificar("automatica", Some("this_is"), "generado"),
        (Categoria::ThisIs, "This is...")
    );
    assert_eq!(
        clasificar("automatica", Some("mood"), "generado"),
        (Categoria::Inteligente, "Inteligente")
    );
    assert_eq!(
        clasificar("automatica", Some("album_mix"), "generado").1,
        "Mix"
    );
    assert_eq!(
        clasificar("manual", None, "usuario"),
        (Categoria::Creada, "Manual")
    );
}

#[test]
fn una_playlist_nueva_se_crea_ordena_y_borra() {
    let db = base();
    let id = crear(&db, "  Para   correr ", Some("")).unwrap();
    assert_eq!(una(&db, id).unwrap().unwrap().nombre, "Para correr");
    assert_eq!(
        agregar(&db, id, &[3, 1, 2, 1, 99]).unwrap(),
        3,
        "sin repetidas ni inexistentes"
    );
    assert_eq!(ids(&db, id).unwrap(), [3, 1, 2]);
    mover(&db, id, 0, 2).unwrap();
    assert_eq!(ids(&db, id).unwrap(), [1, 2, 3]);
    quitar(&db, id, 2).unwrap();
    assert_eq!(ids(&db, id).unwrap(), [1, 3]);
    let p = una(&db, id).unwrap().unwrap();
    assert_eq!((p.num_pistas, p.duracion_seg, p.editable), (2, 200.0, true));
    borrar(&db, id).unwrap();
    assert_eq!(una(&db, id).unwrap(), None);
    let tumbas: i64 = db
        .conexion()
        .unwrap()
        .query_row(
            "SELECT count(*) FROM tumbas WHERE entidad = 'playlist' AND entidad_id = ?1",
            [id],
            |f| f.get(0),
        )
        .unwrap();
    assert_eq!(tumbas, 1, "el móvil se entera del borrado");
}

#[test]
fn los_nombres_vacios_largos_o_repetidos_se_rechazan() {
    let db = base();
    assert_eq!(crear(&db, "   ", None), Err(NsError::InvalidInput));
    assert_eq!(
        crear(&db, &"x".repeat(121), None),
        Err(NsError::InvalidInput)
    );
    crear(&db, "Fiesta", None).unwrap();
    assert_eq!(crear(&db, "FIESTA", None), Err(NsError::NameTaken));
    assert_eq!(
        crear(&db, "RÁPIDAS", None),
        Err(NsError::NameTaken),
        "también con las automáticas"
    );
}

#[test]
fn las_automaticas_no_se_editan_pero_si_se_anclan() {
    let db = base();
    assert_eq!(agregar(&db, 50, &[1]), Err(NsError::PathNotAllowed));
    assert_eq!(borrar(&db, 50), Err(NsError::PathNotAllowed));
    anclar(&db, 50, true).unwrap();
    crear(&db, "Aaa", None).unwrap();
    assert_eq!(todas(&db)[0].id, 50, "las ancladas van delante");
}

#[test]
fn marcar_favoritas_mantiene_me_gusta_con_la_ultima_primera() {
    let db = base();
    crate::biblioteca::fijar_favorita(&db, 1, true).unwrap();
    crate::biblioteca::fijar_favorita(&db, 3, true).unwrap();
    let me_gusta = todas(&db)
        .into_iter()
        .find(|p| p.categoria == Categoria::MeGusta)
        .unwrap();
    assert_eq!(me_gusta.nombre, "Me gusta");
    assert!(me_gusta.anclada);
    assert_eq!(ids(&db, me_gusta.id).unwrap(), [3, 1]);
    crate::biblioteca::fijar_favorita(&db, 1, false).unwrap();
    assert_eq!(ids(&db, me_gusta.id).unwrap(), [3]);
}

#[test]
fn me_gusta_nace_con_las_favoritas_que_marco_el_telefono() {
    let db = base();
    // El merge del teléfono marca sin crear "Me gusta".
    crate::movil::aplicar_historial(
        &db,
        &serde_json::json!({"favoritos": [
            {"pista_id": 2, "favorita": true, "actualizada_en": "2026-01-01T00:00:00.000Z"}
        ]}),
    )
    .unwrap();
    assert!(todas(&db).iter().all(|p| p.categoria != Categoria::MeGusta));
    crate::biblioteca::fijar_favorita(&db, 1, true).unwrap();
    let me_gusta = todas(&db)
        .into_iter()
        .find(|p| p.categoria == Categoria::MeGusta)
        .unwrap();
    assert_eq!(ids(&db, me_gusta.id).unwrap(), [1, 2]);
}

#[test]
fn buscar_y_filtrar_por_categoria() {
    let db = base();
    crear(&db, "Canción triste", None).unwrap();
    let c = |texto: Option<&str>, categoria| {
        listar(
            &db,
            &ConsultaPlaylists {
                texto: texto.map(str::to_owned),
                categoria,
                orden: OrdenPlaylists::NombreAsc,
            },
        )
        .unwrap()
        .into_iter()
        .map(|p| p.nombre)
        .collect::<Vec<_>>()
    };
    assert_eq!(c(Some("cancion"), None), ["Canción triste"]);
    assert_eq!(c(Some("rapidas"), None), ["Rápidas"]);
    assert_eq!(c(None, Some(Categoria::Inteligente)), ["Rápidas"]);
}

fn regla_base() -> ReglaInteligente {
    ReglaInteligente {
        bpm_min: None,
        bpm_max: None,
        energia_min: None,
        energia_max: None,
        animo: None,
        con_instrumental: None,
        solo_favoritas: false,
        reproducciones_min: None,
        reproducciones_max: None,
        escuchada_en_dias: None,
        sin_escuchar_dias: None,
        anio_min: None,
        anio_max: None,
        genero: None,
        orden: OrdenInteligente::BpmDesc,
        limite: 50,
    }
}

#[test]
fn una_lista_inteligente_evalua_rasgos_uso_e_instrumental_y_se_mantiene_viva() {
    let db = base();
    db.conexion()
        .unwrap()
        .execute_batch(
            "UPDATE pistas SET anio = 2021, genero = 'Synth Pop', favorita = 1, reproducciones = 4,
                 ultima_reproduccion = strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-2 days') WHERE id = 1;
             UPDATE pistas SET anio = 2023, genero = 'Synth Rock', favorita = 0, reproducciones = 12,
                 ultima_reproduccion = strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-90 days') WHERE id = 2;
             UPDATE pistas SET anio = 2018, genero = 'Jazz', favorita = 1, reproducciones = 0,
                 ultima_reproduccion = NULL WHERE id = 3;
             INSERT INTO rasgos (pista_id, version, bpm, energia) VALUES
                 (1, 'v2-basico-1', 124.0, 0.75),
                 (2, 'v2-basico-1', 132.0, 0.85),
                 (3, 'v2-basico-1', 92.0, 0.30);
             INSERT INTO etiquetas_ambiente (pista_id, etiqueta, fuente, puntuacion, confianza, version) VALUES
                 (1, 'bailable', 'basic_rules', 0.82, 0.82, 'v2-basico-1'),
                 (2, 'bailable', 'basic_rules', 0.78, 0.78, 'v2-basico-1'),
                 (3, 'tranquila', 'basic_rules', 0.90, 0.90, 'v2-basico-1');
             INSERT INTO stems (pista_id, estado, instrumental) VALUES
                 (1, 'lista', '1.flac'),
                 (2, 'lista', '2.flac');",
        )
        .unwrap();

    let mut r = regla_base();
    r.bpm_min = Some(120.0);
    r.bpm_max = Some(140.0);
    r.energia_min = Some(0.6);
    r.animo = Some("bailable".to_owned());
    r.con_instrumental = Some(true);
    r.solo_favoritas = true;
    r.anio_min = Some(2020);
    r.genero = Some("synth".to_owned());

    let id = crear_inteligente(&db, "Noche synth", Some("Para cantar"), &r).unwrap();
    let resumen = una(&db, id).unwrap().unwrap();
    assert_eq!(resumen.categoria, Categoria::Inteligente);
    assert_eq!(resumen.etiqueta, "Inteligente");
    assert!(!resumen.editable);
    assert!(resumen.borrable);
    assert_eq!(resumen.regla_inteligente.as_ref(), Some(&r));
    assert_eq!(ids(&db, id).unwrap(), [1]);

    // Si nada cambia, volver a leerla no sube su sync_version.
    let v_antes: i64 = db
        .conexion()
        .unwrap()
        .query_row(
            "SELECT sync_version FROM playlists WHERE id = ?1",
            [id],
            |f| f.get(0),
        )
        .unwrap();
    assert_eq!(ids(&db, id).unwrap(), [1]);
    let v_igual: i64 = db
        .conexion()
        .unwrap()
        .query_row(
            "SELECT sync_version FROM playlists WHERE id = ?1",
            [id],
            |f| f.get(0),
        )
        .unwrap();
    assert_eq!(
        v_antes, v_igual,
        "sin cambios no se reescribe ni sube sync_version"
    );

    // Al marcar la pista 2 como favorita, entra sola y en orden de BPM descendente.
    crate::biblioteca::fijar_favorita(&db, 2, true).unwrap();
    assert_eq!(ids(&db, id).unwrap(), [2, 1]);
    let v_despues: i64 = db
        .conexion()
        .unwrap()
        .query_row(
            "SELECT sync_version FROM playlists WHERE id = ?1",
            [id],
            |f| f.get(0),
        )
        .unwrap();
    assert!(v_despues > v_antes, "al entrar una pista sube sync_version");

    // Editar la regla para pedir pistas sin escuchar desde hace 30 días deja solo la 2 (o 3 si quitamos BPM).
    let mut r2 = regla_base();
    r2.solo_favoritas = true;
    r2.sin_escuchar_dias = Some(30);
    r2.orden = OrdenInteligente::TituloAsc;
    editar_inteligente(&db, id, "Favoritas olvidadas mías", None, &r2).unwrap();
    assert_eq!(ids(&db, id).unwrap(), [2, 3]);

    // No admite edición manual de pistas, pero sí borrarse.
    assert_eq!(agregar(&db, id, &[1]), Err(NsError::PathNotAllowed));
    borrar(&db, id).unwrap();
    assert_eq!(una(&db, id).unwrap(), None);
}

#[test]
fn regenerar_automaticas_crea_las_que_alcanzan_el_minimo_y_respeta_las_editadas() {
    let db = BaseDeDatos::en_memoria().unwrap();
    {
        let conn = db.conexion().unwrap();
        conn.execute(
            "INSERT INTO artistas (id, nombre, clave) VALUES (1, 'Soda Stereo', 'soda-stereo')",
            [],
        )
        .unwrap();
        for i in 1..=25 {
            conn.execute(
                "INSERT INTO pistas (id, artista_id, titulo, ruta, duracion_seg, favorita, reproducciones)
                 VALUES (?1, 1, ?2, ?3, 180, ?4, ?5)",
                rusqlite::params![
                    i,
                    format!("Tema {i:02}"),
                    format!("p{i}.mp3"),
                    i32::from(i <= 6),
                    if i <= 6 { 3 } else { 0 }
                ],
            )
            .unwrap();
        }
    }

    let tocadas = regenerar_automaticas(&db).unwrap();
    assert!(tocadas >= 4);
    let nombres: Vec<String> = todas(&db).into_iter().map(|p| p.nombre).collect();
    assert!(nombres.contains(&"Favoritas que siguen sonando".to_owned()));
    assert!(nombres.contains(&"Recientes de tu biblioteca".to_owned()));
    assert!(nombres.contains(&"Canciones por descubrir".to_owned()));
    assert!(nombres.contains(&"Recientes sin escuchar".to_owned()));
    assert!(nombres.contains(&"This is Soda Stereo".to_owned()));

    // Segunda pasada sin cambios: 0 playlists reescritas.
    assert_eq!(regenerar_automaticas(&db).unwrap(), 0);

    // Si una automática fue editada por el usuario, no se toca aunque baje del mínimo.
    db.conexion()
        .unwrap()
        .execute(
            "UPDATE playlists SET editada = 1 WHERE clave_auto = 'auto:favoritas_sonando'",
            [],
        )
        .unwrap();
    db.conexion()
        .unwrap()
        .execute("UPDATE pistas SET favorita = 0", [])
        .unwrap();
    regenerar_automaticas(&db).unwrap();
    let sigue = todas(&db)
        .into_iter()
        .any(|p| p.nombre == "Favoritas que siguen sonando");
    assert!(sigue, "la editada por el usuario se conserva visible");
}
