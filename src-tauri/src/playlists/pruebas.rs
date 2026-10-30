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
