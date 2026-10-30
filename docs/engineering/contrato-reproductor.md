# Contrato del reproductor: las pruebas de la V1

> **Estado:** Vigente desde el 2026-10-30. Lo exige el criterio de F2.1.2 ([fase 2](../plan/fase-2-escuchar.md)): las
> 112 pruebas de `legado/tests/test_reproductor_ui_contract.py` se traducen a pruebas de la V2. Esta tabla dice dónde
> vive cada una y cuál falta.

Las de la cola viven en `src-tauri/src/cola/pruebas.rs` con el nombre de la original sin el prefijo `test_`. Las de
las vistas (`qml_*`) se traducen a recorridos de Playwright cuando existe la vista: lo que verificaban era la
disposición de QML, y su equivalente es la vista de la V2, no un archivo de QML.

Traducidas: **37 de 112**.

| Prueba de la V1 | Estado | Dónde vive en la V2 |
|---|---|---|
| `reproductor_resuelve_portada_de_album_en_pista_activa` | Pendiente | F2.2.1, portada de la pista activa |
| `modelo_reproductor_expone_snapshot_de_pista_activa_para_qml` | Pendiente | F2.1.7, servicio de reproducción (estado y sesión) |
| `modelo_reproductor_expone_pista_visual_de_cola_persistida_sin_activar` | Pendiente | F2.1.7, servicio de reproducción (estado y sesión) |
| `modelo_reproductor_pista_visual_usa_cola_cacheada_sin_consultar_backend` | Pendiente | F2.1.7, servicio de reproducción (errores del motor) |
| `reanudar_cola_persistida_no_bloquea_al_leer_pista_visual` | Pendiente | F2.1.7, servicio de reproducción (estado y sesión) |
| `reproductor_resuelve_portada_desde_assets_manifest` | Pendiente | F2.2.1, portada de la pista activa |
| `reproductor_expone_portada_hd_desde_assets_manifest` | Pendiente | F2.2.1, portada de la pista activa |
| `modelo_reproductor_expone_portada_hd_para_qml` | Pendiente | F2.2.1, portada de la pista activa |
| `modelo_biblioteca_abre_album_desde_id_directo` | Pendiente | F2.2.3, Biblioteca |
| `modelo_biblioteca_abre_album_por_metadata_sin_id` | Pendiente | F2.2.3, Biblioteca |
| `modelo_biblioteca_abre_artista_por_metadata_sin_id` | Pendiente | F2.2.3, Biblioteca |
| `modelo_biblioteca_no_abre_metadata_ambigua` | Pendiente | F2.2.3, Biblioteca |
| `biblioteca_grupos_albums_disponibles_oculta_vacios_y_clasifica_otros` | Hecha | `src-tauri/src/biblioteca.rs`: `los_albumes_vacios_no_se_listan_y_cada_uno_trae_sus_cifras` |
| `listar_pistas_sin_limite_de_500_y_con_filtros_reales` | Hecha | `src-tauri/src/biblioteca.rs`: `los_filtros_se_combinan`, `un_tramo_empieza_donde_se_pide_y_el_total_no_cambia` |
| `biblioteca_busqueda_albumes_artistas_por_metadata_cruzada_con_conteos_completos` | Hecha | `src-tauri/src/biblioteca.rs`: `buscar_albumes_y_artistas_no_necesita_tildes` |
| `biblioteca_ordenes_directos_e_inversos` | Hecha | `src-tauri/src/biblioteca.rs`: `cada_orden_de_la_v1_ordena_y_su_inverso_lo_invierte` |
| `detalle_artista_expone_todas_las_pistas_y_destacadas` | Hecha | `src-tauri/src/biblioteca.rs`: `un_album_o_artista_sin_canciones_visibles_no_existe_para_la_interfaz`, y la vista lista todas en la ventana virtual |
| `modelo_biblioteca_persiste_estado_y_carga_pistas_filtradas` | Pendiente | F2.2.3, Biblioteca |
| `modelo_biblioteca_toggle_favorita_y_filtro_reflejan_estado` | Hecha | `src-tauri/src/biblioteca.rs`: `desmarcar_una_favorita_tambien_guarda_la_hora_y_sube_la_version`, `los_filtros_se_combinan` |
| `modelo_biblioteca_favorita_refleja_lista_album_y_artista` | Pendiente | F2.2.3, Biblioteca |
| `siguiente_sin_cola_detiene_y_play_reanuda_pista_activa` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `anterior_en_repetir_todo_envuelve_al_final_de_la_cola` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `aleatorio_reordena_cola_visible_y_siguiente_respeta_ese_orden` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `reproducir_cola_con_aleatorio_arranca_en_la_pista_elegida` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `desactivar_aleatorio_restaura_orden_original_restante` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `desactivar_aleatorio_restaura_orden_base_completo` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `modelo_buscar_posicion_actualiza_progreso_inmediato` | Pendiente | F2.1.7, servicio de reproducción (posición y volumen) |
| `modelo_buscar_posicion_clampa_fuera_de_rango` | Pendiente | F2.1.7, servicio de reproducción (posición y volumen) |
| `modelo_buscar_posicion_con_duracion_desconocida_no_avanza` | Pendiente | F2.2.1, formato de tiempos en la barra y la cola |
| `modelo_progreso_ratio_no_lanza_con_estado_corrupto` | Pendiente | F2.1.7, servicio de reproducción (posición y volumen) |
| `modelo_set_volumen_clampa_rango` | Pendiente | F2.1.7, servicio de reproducción (posición y volumen) |
| `modelo_progreso_reportado_no_supera_duracion_real` | Pendiente | F2.2.1, formato de tiempos en la barra y la cola |
| `modelo_formatea_tiempos_con_duracion_canonica` | Pendiente | F2.2.1, formato de tiempos en la barra y la cola |
| `modelo_lyrics_mood_fallback_estable_y_en_rango` | Pendiente | F2.2.6, letras sincronizadas |
| `modelo_lyrics_mood_usa_color_dominante_de_portada` | Pendiente | F2.2.6, letras sincronizadas |
| `modelo_mood_visual_es_alias_compatible_de_lyrics_mood` | Pendiente | F2.2.6, letras sincronizadas |
| `modelo_lyrics_normaliza_synced_y_elimina_traduccion` | Pendiente | F2.2.6, letras sincronizadas |
| `modelo_lyrics_malformada_oculta_plain_fallback` | Pendiente | F2.2.6, letras sincronizadas |
| `modelo_lyrics_ignora_metadata_lrc_sin_invalidar` | Pendiente | F2.2.6, letras sincronizadas |
| `modelo_lyrics_plain_sin_synced_se_sanitiza` | Pendiente | F2.2.6, letras sincronizadas |
| `modelo_lyrics_plain_tipo_documento_se_oculta` | Pendiente | F2.2.6, letras sincronizadas |
| `modelo_reproductor_expone_y_alterna_karaoke_lista` | Pendiente | F5.2.2, micrófono del reproductor |
| `alternar_karaoke_preserva_lyrics_y_estado` | Pendiente | F2.2.6, letras sincronizadas |
| `modelo_reproductor_oculta_karaoke_si_no_esta_lista` | Pendiente | F5.2.2, micrófono del reproductor |
| `sorprenderme_devuelve_true_y_reproduce_sin_pista_activa` | Pendiente | F2.2.2, Inicio (Sorpréndeme) |
| `sorprenderme_reproduce_inmediato_aun_con_reproduccion_activa` | Pendiente | F2.2.2, Inicio (Sorpréndeme) |
| `sorprenderme_devuelve_false_sin_candidatas_validas` | Pendiente | F2.2.2, Inicio (Sorpréndeme) |
| `sorpresa_activa_se_limpia_al_finalizar_o_reproducir_normal` | Pendiente | F2.2.2, Inicio (Sorpréndeme) |
| `sorpresa_activa_se_mantiene_en_sorpresas_consecutivas` | Pendiente | F2.2.2, Inicio (Sorpréndeme) |
| `sorprenderme_diversifica_artistas_y_albums_con_alternativas` | Pendiente | F2.2.2, Inicio (Sorpréndeme) |
| `sorprenderme_funciona_si_toda_la_biblioteca_es_del_mismo_artista` | Pendiente | F2.2.2, Inicio (Sorpréndeme) |
| `sorprenderme_no_repite_pistas_en_biblioteca_amplia` | Pendiente | F2.2.2, Inicio (Sorpréndeme) |
| `sorprenderme_evita_repetir_artista_si_hay_alternativas` | Pendiente | F2.2.2, Inicio (Sorpréndeme) |
| `modelo_reproductor_expone_duracion_total_de_cola` | Pendiente | F2.2.1, formato de tiempos en la barra y la cola |
| `modelo_duracion_cola_no_reentra_lock_del_reproductor` | Pendiente | F2.2.1, formato de tiempos en la barra y la cola |
| `modelo_estadisticas_formatear_duracion_detallada` | Pendiente | F2.2.1, formato de tiempos en la barra y la cola |
| `modelo_reproductor_formatea_duracion_larga_para_cola` | Pendiente | F2.2.1, formato de tiempos en la barra y la cola |
| `limpiar_cola_vacia_lista_sin_detener_pista_activa` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `vaciar_cola_mantener_actual_conserva_solo_fila_activa` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `vaciar_cola_mantener_actual_vacia_si_no_hay_fila_activa` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `quitar_unica_pista_activa_resetea_reproductor` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `quitar_unica_pista_activa_pausada_resetea_reproductor` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `quitar_pista_activa_con_mas_cola_reproduce_siguiente` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `quitar_ultima_pista_activa_con_mas_cola_reproduce_anterior` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `modelo_quitar_unica_pista_activa_limpia_barra_visual` | Pendiente | F2.1.7, servicio de reproducción |
| `modelo_vaciar_cola_mantener_actual_sincroniza_cola_visible` | Pendiente | F2.1.7, servicio de reproducción |
| `modelo_reproductor_agrega_varias_a_cola_en_una_operacion` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `modelo_quitar_unica_pista_sin_iniciar_limpia_pista_visual` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `controles_sin_pista_y_cola_vacia_no_rompen_estado` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `reproductor_pista_inexistente_emite_warning_y_estado_error` | Pendiente | F2.1.7, servicio de reproducción (errores del motor) |
| `reproductor_error_de_backend_audio_no_bloquea_ui` | Pendiente | F2.1.7, servicio de reproducción (errores del motor) |
| `reproductor_error_backend_emite_warning` | Pendiente | F2.1.7, servicio de reproducción (errores del motor) |
| `reproductor_sin_vlc_real_emite_error_critico_retenido` | Pendiente | F2.1.7, servicio de reproducción (errores del motor) |
| `repetir_uno_no_consume_cola_al_finalizar` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `repetir_todo_cicla_al_terminar_ultima_pista` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `repetir_todo_no_revive_contexto_tras_limpiar_cola` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `repetir_todo_contexto_respeta_reorden_manual` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `repetir_todo_no_reintroduce_pista_quitada` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `reproducir_pista_individual_reemplaza_cola_previa` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `modelo_reproducir_pista_individual_actualiza_cola_visible` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `reproducir_pista_existente_en_cola_reemplaza_sin_duplicar` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `reproducir_cola_conserva_contexto_completo` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `reproductor_avanza_en_cola_al_finalizar_sin_consumir` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `reproductor_detiene_conservando_pista_al_terminar_ultima` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `reproductor_avanza_a_pista_anadida_conservando_individual` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `reproducir_indice_cola_reproduce_sin_reconstruir_orden` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `reproducir_indice_cola_invalido_no_cambia_estado` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `mover_en_cola_reordena_y_preserva_indice_activo` | Hecha | `src-tauri/src/cola/pruebas.rs` |
| `reproductor_permite_desregistrar_callbacks_de_progreso_y_estado` | Pendiente | F2.1.7, servicio de reproducción (posición y volumen) |
| `qml_no_declara_tooltips_visibles` | Pendiente | F2.2.x, recorrido de Playwright de la vista |
| `qml_barra_no_muestra_toast_exito_sorpresa` | Pendiente | F2.2.x, recorrido de Playwright de la vista |
| `qml_lyrics_overlay_no_reacomoda_con_barra_y_sync_es_fijo` | Pendiente | F2.2.x, recorrido de Playwright de la vista |
| `qml_fullscreen_info_usa_mood_visual_y_salida_limpia` | Pendiente | F2.2.x, recorrido de Playwright de la vista |
| `qml_mini_reproductor_es_ventana_flotante_con_controles_svg` | Pendiente | F2.2.x, recorrido de Playwright de la vista |
| `qml_queue_panel_usa_iconos_svg_para_acciones_de_fila` | Pendiente | F2.2.x, recorrido de Playwright de la vista |
| `qml_queue_panel_vaciar_usa_slot_especifico_para_conservar_actual` | Pendiente | F2.2.x, recorrido de Playwright de la vista |
| `qml_queue_panel_auto_scroll_durante_drag` | Pendiente | F2.2.x, recorrido de Playwright de la vista |
| `qml_queue_panel_distingue_sonando_y_pausada_y_oculta_0s_en_vacio` | Pendiente | F2.2.x, recorrido de Playwright de la vista |
| `qml_popup_cola_es_responsive_y_limitado_al_viewport` | Pendiente | F2.2.x, recorrido de Playwright de la vista |
| `qml_popup_cola_vacia_abre_con_altura_positiva` | Pendiente | F2.2.x, recorrido de Playwright de la vista |
| `qml_popup_cola_cierra_con_click_fuera` | Pendiente | F2.2.x, recorrido de Playwright de la vista |
| `qml_popup_cola_tocar_boton_playlist_abierto_lo_cierra` | Pendiente | F2.2.x, recorrido de Playwright de la vista |
| `qml_principal_escucha_avisos_y_usa_toast_o_dialog` | Pendiente | F2.2.x, recorrido de Playwright de la vista |
| `qml_metadata_activa_usa_fallback_de_biblioteca` | Pendiente | F2.2.x, recorrido de Playwright de la vista |
| `qml_barra_y_mini_usan_pista_visual_sin_habilitar_overlays` | Pendiente | F2.2.x, recorrido de Playwright de la vista |
| `qml_nav_lateral_compacta_vertical_y_usa_animacion_compartida` | Pendiente | F2.2.x, recorrido de Playwright de la vista |
| `qml_reproduccion_individual_y_playlist_usa_cola_con_indice` | Pendiente | F2.2.x, recorrido de Playwright de la vista |
| `qml_playlists_fase8_contrato_visual_y_acciones` | Pendiente | F2.2.x, recorrido de Playwright de la vista |
| `qml_biblioteca_fase5_estado_filtros_y_reset_nav` | Pendiente | F2.2.x, recorrido de Playwright de la vista |
| `qml_biblioteca_fase5_ux_acciones_claras_sin_deprecated` | Pendiente | F2.2.x, recorrido de Playwright de la vista |
| `qml_vista_busqueda_fase6_contrato_visual_y_acciones` | Pendiente | F2.2.x, recorrido de Playwright de la vista |
| `qml_vista_inicio_fase7_dashboard_vivo_sin_accesos_rapidos` | Pendiente | F2.2.x, recorrido de Playwright de la vista |
