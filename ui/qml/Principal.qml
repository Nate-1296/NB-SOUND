// =============================================================================
// Principal.qml — Shell maestro de la aplicación
//
// Responsabilidades:
//   - Estructura global: NavLateral + StackLayout de vistas + BarraReproduccion.
//   - Lazy loading de vistas mediante Loaders asíncronos; una vista se instancia
//     la primera vez que se visita y permanece viva hasta que la app cierra.
//     Esto evita reconstruir el árbol visual en cada navegación a costa de memoria.
//   - Gestión del z-order global: contenido (z=0), cola (z=120), lyrics (z=200),
//     fullscreen-info (z=220), fullscreen-lyrics (z=230), toasts (z=320).
//   - Overlays de reproducción: overlay_lyrics cubre la ventana y alterna entre
//     tres modos según el estado de reproduccion_expandida_visible y lyrics_visible.
//   - Barra flotante sobre overlay: barra_lyrics se revela con animación
//     de ancho (reveal) al mover el ratón; se oculta automáticamente tras 1.9 s.
//   - Mini-reproductor: ventana Qt::Tool sin marco, frameless, siempre encima,
//     posicionada en la esquina inferior-derecha la primera vez.
//   - Atajos de teclado globales y teclas multimedia; requieren activación explícita
//     mediante activar_atajos_reproduccion() para no interferir con campos de texto.
//   - Señales Python escuchadas: configuracion.onConfiguracionCambiada,
//     importacion.onImportacionFin / onImportacionCancelada,
//     reproductor.onAvisoReproductor.
//   - Escalado de UI: `escala_ui` se aplica con transform scale en TopLeft sobre
//     el contenedor principal; `ancho_base` compensa la escala para los breakpoints.
// =============================================================================

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

import "componentes" as Componentes
import "vistas" as Vistas
import "componentes/UiUtils.js" as UiUtils

ApplicationWindow {
    id: ventana_principal
    visible: true
    width: 1280
    height: 800
    minimumWidth: 900
    minimumHeight: 600
    title: "NB SOUND"

    // Cuando el usuario cierra la ventana principal, salir de la app
    // explícitamente. Sin esto, si la `Window` mini-reproductor (que
    // tiene `Qt.Tool`) está oculta pero no destruida, Qt puede no
    // disparar `aboutToQuit` y el backend de audio (VLC) se queda
    // sonando como proceso huérfano hasta que se mate manualmente.
    //
    // Secuencia robusta:
    //   1. Detener la reproducción del backend inmediatamente (corta
    //      el audio aunque algún teardown async tarde).
    //   2. Ocultar el mini-reproductor y cualquier ventana auxiliar.
    //   3. `Qt.quit()` para que dispare `aboutToQuit` →
    //      `_cleanup_modelos` (main_ui.py) → `Reproductor.cerrar()`.
    onClosing: function(close) {
        try {
            if (typeof reproductor !== "undefined" && reproductor)
                reproductor.detener_forzado()
        } catch (e) { /* fail-safe: el cleanup posterior lo libera */ }
        mini_reproductor_activo = false
        Qt.callLater(Qt.quit)
    }

    // ── Estado de navegación y visibilidad de overlays ────────────────────────
    property string vista_activa: "inicio"
    property int _playlistPendienteId: 0
    property bool reproduccion_expandida_visible: false
    property bool lyrics_visible: false
    readonly property bool reproduccion_lyrics_activado: lyrics_visible
    property bool mini_reproductor_activo: false
    property bool atajos_reproduccion_activos: false
    readonly property bool tooltips_habilitados: false
    property var tema: temaUi
    readonly property var audioDeepModel: audioDeep
    property real escala_ui: _resolver_escala_ui()
    property string fuente_ui: configuracion.obtener("ui_font_family") || "Inter"
    property string keymap_reproduccion: configuracion.obtener("hotkeys_reproduccion") || "{}"
    property real animacion_reproductor_fase: 0
    readonly property int ancho_base: Math.max(0, ventana_principal.width / ventana_principal.escala_ui)
    readonly property int altura_barra_reproduccion: Componentes.UiTokens.controlHeightXl + Componentes.UiTokens.spacing32 + Componentes.UiTokens.spacing10
    readonly property bool layout_compacto: ancho_base < Componentes.UiTokens.breakpointCompact
    readonly property bool layout_medio: ancho_base >= Componentes.UiTokens.breakpointCompact && ancho_base < Componentes.UiTokens.breakpointMedium
    readonly property bool layout_confortable: ancho_base >= Componentes.UiTokens.breakpointMedium
    readonly property bool barra_reproduccion_visible: !reproduccion_expandida_visible && !lyrics_visible
    // ── Z-order global — no modificar sin revisar todos los overlays ─────────
    readonly property int z_capa_contenido_principal: 0
    readonly property int z_capa_cola: 120
    readonly property int z_capa_lyrics: 200
    readonly property int z_capa_fullscreen_info: 220
    readonly property int z_capa_fullscreen_lyrics: 230
    readonly property int z_capa_toasts: 320
    // ── Modos del overlay — determinan qué componente carga el Loader interno ──
    // lyrics_normal:      overlay solo con letra (sin fullscreen).
    // fullscreen_info:    pantalla completa con info de pista (sin letra).
    // fullscreen_lyrics:  pantalla completa con letra.
    // none:               ningún overlay activo.
    readonly property bool overlay_lyrics_visible: lyrics_visible && !reproduccion_expandida_visible
    readonly property bool overlay_fullscreen_info_visible: reproduccion_expandida_visible && !lyrics_visible
    readonly property bool overlay_fullscreen_lyrics_visible: reproduccion_expandida_visible && lyrics_visible
    readonly property bool barra_overlay_visible: overlay_lyrics.visible && overlay_lyrics.barra_visible
    readonly property string overlay_reproductor_modo: overlay_fullscreen_lyrics_visible
                                                    ? "fullscreen_lyrics"
                                                    : (overlay_fullscreen_info_visible
                                                       ? "fullscreen_info"
                                                       : (overlay_lyrics_visible ? "lyrics_normal" : "none"))
    property string ultimo_error_global: ""
    property var alerta_reproductor_critica: ({
        "titulo": "",
        "mensaje": "",
        "soluciones": []
    })
    // Mapa de vistas visitadas: controla cuáles Loaders están activos.
    // Una vista visitada permanece en memoria; las no visitadas tienen active=false.
    property var _vistas_visitadas: ({
        "inicio": true,
        "busqueda": false,
        "biblioteca": false,
        "playlists": false,
        "importacion": false,
        "configuracion": false,
        "perfil": false,
        "karaoke": false,
        "dj_privado": false,
        "explorador_ciego": false,
        "sincronizacion": false
    })

    color: tema.fondo
    font.family: fuente_ui

    Item {
        id: contenido_principal
        anchors.fill: parent
        z: ventana_principal.z_capa_contenido_principal
        scale: ventana_principal.escala_ui
        transformOrigin: Item.TopLeft

        RowLayout {
            id: shell_layout
            width: ventana_principal.ancho_base
            height: ventana_principal.height / ventana_principal.escala_ui
            spacing: 0
            anchors.rightMargin: ventana_principal.layout_compacto ? Componentes.UiTokens.spacing8 : Componentes.UiTokens.spacing12

            Componentes.NavLateral {
                id: nav_lateral
                Layout.preferredWidth: ventana_principal.layout_compacto ? 236 : (ventana_principal.layout_medio ? 258 : 272)
                Layout.fillHeight: true
                vista_activa: ventana_principal.vista_activa
                shell: ventana_principal
                animacion_fase: ventana_principal.animacion_reproductor_fase
                animacion_origen_x: 0
                animacion_ancho_mundo: shell_layout.width
                onNavegar: function(vista) { ventana_principal.navegar_a_vista(vista) }
            }

            Item {
                id: capa_base_contenido
                Layout.fillWidth: true
                Layout.fillHeight: true

                // El contenedor_contenido encapsula el StackLayout de vistas y la BarraReproduccion.
                // Su límite inferior se ancla al tope de barra_principal cuando ésta es visible.
                Rectangle {
                    id: contenedor_contenido
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: barra_principal.visible ? barra_principal.top : parent.bottom
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    color: tema.fondoElevado
                    radius: ventana_principal.vista_activa === "inicio" ? 0 : Componentes.UiTokens.radiusLg
                    border.color: ventana_principal.vista_activa === "inicio" ? "transparent" : tema.borde
                    border.width: 1

                    // StackLayout con Loaders asíncronos por vista.
                    // currentIndex se sincroniza con vista_activa vía _indice_vista().
                    // Los Loaders se activan la primera vez que se visita la vista
                    // y permanecen activos para preservar el estado de scroll y filtros.
                    StackLayout {
                        anchors.fill: parent
                        currentIndex: _indice_vista(ventana_principal.vista_activa)

                        Loader {
                            id: loader_inicio
                            active: ventana_principal._debe_cargar_vista("inicio")
                            asynchronous: true
                            sourceComponent: comp_vista_inicio
                            onStatusChanged: ventana_principal._manejar_estado_loader("inicio", loader_inicio)
                        }
                        Loader {
                            id: loader_busqueda
                            active: ventana_principal._debe_cargar_vista("busqueda")
                            asynchronous: true
                            sourceComponent: comp_vista_busqueda
                            onStatusChanged: ventana_principal._manejar_estado_loader("busqueda", loader_busqueda)
                        }
                        Loader {
                            id: loader_biblioteca
                            active: ventana_principal._debe_cargar_vista("biblioteca")
                            asynchronous: true
                            sourceComponent: comp_vista_biblioteca
                            onStatusChanged: ventana_principal._manejar_estado_loader("biblioteca", loader_biblioteca)
                        }
                        // Caso especial: si la vista de playlists se carga mientras hay una
                        // navegación pendiente desde VistaInicio (abrir_playlist_desde_inicio),
                        // se entrega el id a la vista tan pronto el item esté listo.
                        Loader {
                            id: loader_playlists
                            active: ventana_principal._debe_cargar_vista("playlists")
                            asynchronous: true
                            sourceComponent: comp_vista_playlists
                            onStatusChanged: ventana_principal._manejar_estado_loader("playlists", loader_playlists)
                            onItemChanged: {
                                if (item && ventana_principal._playlistPendienteId > 0) {
                                    var pid = ventana_principal._playlistPendienteId
                                    ventana_principal._playlistPendienteId = 0
                                    Qt.callLater(function() {
                                        if (item && item.abrir_playlist_id)
                                            item.abrir_playlist_id(pid)
                                    })
                                }
                            }
                        }
                        Loader {
                            id: loader_importacion
                            active: ventana_principal._debe_cargar_vista("importacion")
                            asynchronous: true
                            sourceComponent: comp_vista_importacion
                            onStatusChanged: ventana_principal._manejar_estado_loader("importacion", loader_importacion)
                        }
                        Loader {
                            id: loader_configuracion
                            active: ventana_principal._debe_cargar_vista("configuracion")
                            asynchronous: true
                            sourceComponent: comp_vista_configuracion
                            onStatusChanged: ventana_principal._manejar_estado_loader("configuracion", loader_configuracion)
                        }
                        Loader {
                            id: loader_perfil
                            active: ventana_principal._debe_cargar_vista("perfil")
                            asynchronous: true
                            sourceComponent: comp_vista_perfil
                            onStatusChanged: ventana_principal._manejar_estado_loader("perfil", loader_perfil)
                        }
                        Loader {
                            id: loader_karaoke
                            active: ventana_principal._debe_cargar_vista("karaoke")
                            asynchronous: true
                            sourceComponent: comp_vista_karaoke
                            onStatusChanged: ventana_principal._manejar_estado_loader("karaoke", loader_karaoke)
                        }
                        Loader {
                            id: loader_dj_privado
                            active: ventana_principal._debe_cargar_vista("dj_privado")
                            asynchronous: true
                            sourceComponent: comp_vista_dj_privado
                            onStatusChanged: ventana_principal._manejar_estado_loader("dj_privado", loader_dj_privado)
                        }
                        Loader {
                            id: loader_explorador_ciego
                            active: ventana_principal._debe_cargar_vista("explorador_ciego")
                            asynchronous: true
                            sourceComponent: comp_vista_explorador_ciego
                            onStatusChanged: ventana_principal._manejar_estado_loader("explorador_ciego", loader_explorador_ciego)
                        }
                        // Pantalla plug & play: checklist de dependencias.
                        // Cargada bajo demanda igual que el resto; navegada
                        // desde NavLateral con el nombre "estado_sistema".
                        Loader {
                            id: loader_estado_sistema
                            active: ventana_principal._debe_cargar_vista("estado_sistema")
                            asynchronous: true
                            sourceComponent: comp_vista_estado_sistema
                            onStatusChanged: ventana_principal._manejar_estado_loader("estado_sistema", loader_estado_sistema)
                        }
                        // Vista del ecosistema móvil: servidor local + QR + dispositivos.
                        // Cargada bajo demanda; el servidor solo arranca al pulsar "Encender".
                        Loader {
                            id: loader_sincronizacion
                            active: ventana_principal._debe_cargar_vista("sincronizacion")
                            asynchronous: true
                            sourceComponent: comp_vista_sincronizacion
                            onStatusChanged: ventana_principal._manejar_estado_loader("sincronizacion", loader_sincronizacion)
                        }
                    }
                }

                Componentes.BarraReproduccion {
                    id: barra_principal
                    shell: ventana_principal
                    capa_cola_z: ventana_principal.z_capa_cola
                    animacion_fase: ventana_principal.animacion_reproductor_fase
                    animacion_origen_x: nav_lateral.width
                    animacion_ancho_mundo: shell_layout.width
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: ventana_principal.altura_barra_reproduccion
                    visible: ventana_principal.barra_reproduccion_visible
                }
            }
        }
    }

    Component { id: comp_vista_inicio; Vistas.VistaInicio { shell: ventana_principal } }
    Component { id: comp_vista_busqueda; Vistas.VistaBusqueda { shell: ventana_principal } }
    Component { id: comp_vista_biblioteca; Vistas.VistaBiblioteca { shell: ventana_principal } }
    Component { id: comp_vista_playlists; Vistas.VistaPlaylists { shell: ventana_principal } }
    Component {
        id: comp_vista_importacion
        Vistas.VistaImportacion {
            shell: ventana_principal
            temaBase: temaUi
            cfg: configuracion
            imp: importacion
            audioDeep: ventana_principal.audioDeepModel
            rev: revision
        }
    }
    Component { id: comp_vista_configuracion; Vistas.VistaConfiguracion { shell: ventana_principal } }
    Component { id: comp_vista_perfil; Vistas.VistaPerfil { shell: ventana_principal } }
    Component {
        id: comp_vista_karaoke
        Vistas.VistaKaraoke {
            shell: ventana_principal
            temaBase: temaUi
            cfg: configuracion
            kar: karaoke
            rep: reproductor
        }
    }
    Component {
        id: comp_vista_dj_privado
        Vistas.VistaDJPrivado {
            shell: ventana_principal
            temaBase: temaUi
            cfg: configuracion
        }
    }
    Component { id: comp_vista_explorador_ciego; Vistas.VistaExploradorCiego { shell: ventana_principal } }
    Component { id: comp_vista_estado_sistema; Vistas.VistaEstadoSistema { shell: ventana_principal } }
    Component { id: comp_vista_sincronizacion; Vistas.VistaSincronizacion { shell: ventana_principal } }

    // Timer de animación: incrementa la fase en ~24 fps cuando hay reproducción activa.
    // La fase se comparte con NavLateral y BarraReproduccion para sincronizar
    // el fondo animado (AnimatedPlaybackBackground) sin crear timers redundantes.
    Timer {
        interval: 42
        repeat: true
        running: reproductor.reproduciendo
        onTriggered: {
            ventana_principal.animacion_reproductor_fase += 0.045
            if (ventana_principal.animacion_reproductor_fase > 10000)
                ventana_principal.animacion_reproductor_fase = 0
        }
    }

    // ── Funciones auxiliares ───────────────────────────────────────────────────

    // Lee la escala configurada (en %) y la convierte a factor real (≥1.0).
    function _resolver_escala_ui() {
        const escalaGuardada = parseFloat(configuracion.obtener("ui_scale") || "100")
        if (isNaN(escalaGuardada) || escalaGuardada <= 0) {
            return 1.0
        }
        return Math.max(1.0, escalaGuardada / 100.0)
    }

    function _indice_vista(nombre) {
        var mapa = {
            "inicio": 0,
            "busqueda": 1,
            "biblioteca": 2,
            "playlists": 3,
            "importacion": 4,
            "configuracion": 5,
            "perfil": 6,
            "karaoke": 7,
            "dj_privado": 8,
            "explorador_ciego": 9,
            "estado_sistema": 10,
            "sincronizacion": 11
        }
        return mapa[nombre] !== undefined ? mapa[nombre] : 0
    }

    function _marcar_vista_visitada(nombre) {
        if (!_vistas_visitadas[nombre]) {
            _vistas_visitadas[nombre] = true
            _vistas_visitadas = Object.assign({}, _vistas_visitadas)
        }
    }

    function _debe_cargar_vista(nombre) {
        return nombre === vista_activa || !!_vistas_visitadas[nombre]
    }

    function navegar_a_vista(vista) {
        if (vista === "biblioteca" && vista_activa === "biblioteca") {
            if (loader_biblioteca.item && loader_biblioteca.item.ir_a_inicio_biblioteca)
                loader_biblioteca.item.ir_a_inicio_biblioteca()
            return
        }
        vista_activa = vista
    }

    function _manejar_estado_loader(nombreVista, loader) {
        if (!loader || loader.status !== Loader.Error) {
            return
        }
        var mensaje = "No se pudo cargar la vista: " + nombreVista
        console.error("[UI] Falló carga de vista:", nombreVista)
        mostrar_error_global(mensaje)
    }

    function mostrar_error_global(mensaje) {
        if (!mensaje || mensaje === "")
            return
        ultimo_error_global = mensaje
        toast_global.show(mensaje, "danger")
    }

    function mostrar_toast_global(mensaje, tono) {
        if (!mensaje || mensaje === "")
            return
        toast_global.show(mensaje, tono || "info")
    }

    function manejar_aviso_reproductor(aviso) {
        if (!aviso)
            return
        var nivel = String(aviso.nivel || "warning")
        var mensaje = String(aviso.mensaje || aviso.titulo || "")
        if (nivel === "critical") {
            alerta_reproductor_critica = {
                "titulo": String(aviso.titulo || "Error del reproductor"),
                "mensaje": mensaje,
                "soluciones": aviso.soluciones || []
            }
            dialog_error_reproductor.open()
            return
        }
        mostrar_toast_global(mensaje, nivel === "warning" ? "warning" : "info")
    }

    function refrescar_datos_ui() {
        playlists.sincronizar_inteligentes(0)
        estadisticas.cargar()
        biblioteca.recargar()
        revision.cargar()
        playlists.cargar()
        busqueda.recargar()
    }

    function alternar_vista_lyrics() {
        if (!reproductor.titulo_activo)
            return

        if (reproduccion_expandida_visible) {
            alternar_lyrics_en_fullscreen()
            return
        }

        cerrar_colas_reproductor()
        lyrics_visible = !lyrics_visible
    }

    function alternar_lyrics_en_fullscreen() {
        if (!reproductor.titulo_activo || !reproduccion_expandida_visible)
            return

        cerrar_colas_reproductor()
        lyrics_visible = !lyrics_visible
        overlay_lyrics._entrar_o_cambiar_fullscreen_sin_reveal(false)
    }

    function alternar_visualizacion_ampliada() {
        if (!reproductor.titulo_activo)
            return

        cerrar_colas_reproductor()
        var lyricsPrevio = lyrics_visible
        if (!reproduccion_expandida_visible) {
            reproduccion_expandida_visible = true
            cerrar_mini_reproductor()
            lyrics_visible = lyricsPrevio
            _entrar_fullscreen_reproductor()
            showFullScreen()
        } else {
            salir_fullscreen_reproductor(lyrics_visible)
        }
    }

    function cerrar_vista_lyrics() {
        cerrar_colas_reproductor()
        if (reproduccion_expandida_visible) {
            salir_fullscreen_reproductor(true)
            return
        }
        lyrics_visible = false
    }

    function abrir_mini_reproductor() {
        if (reproduccion_expandida_visible)
            return
        cerrar_colas_reproductor()
        mini_reproductor_activo = true
        Qt.callLater(function() {
            mini_window.preparar_apertura()
        })
    }

    function cerrar_mini_reproductor() {
        mini_reproductor_activo = false
    }

    function alternar_modo_mini_reproductor() {
        if (mini_reproductor_activo)
            cerrar_mini_reproductor()
        else
            abrir_mini_reproductor()
    }

    function _restaurar_ventana_post_fullscreen() {
        showMaximized()
        requestActivate()
        Qt.callLater(function() {
            if (ventana_principal.visibility !== Window.Maximized
                    && ventana_principal.visibility !== Window.FullScreen) {
                ventana_principal.x = Math.round((Screen.width - ventana_principal.width) / 2)
                ventana_principal.y = Math.round((Screen.height - ventana_principal.height) / 2)
            }
            ventana_principal.requestActivate()
        })
    }

    function _entrar_fullscreen_reproductor() {
        overlay_lyrics.barra_reveal_width = overlay_lyrics.width
        overlay_lyrics.modo_reveal_anterior = overlay_reproductor_modo
        overlay_lyrics._entrar_o_cambiar_fullscreen_sin_reveal(true)
    }

    function salir_fullscreen_reproductor(conservarLyrics) {
        var conservar = conservarLyrics === undefined ? lyrics_visible : !!conservarLyrics
        if (!reproduccion_expandida_visible)
            return
        cerrar_colas_reproductor()
        reproduccion_expandida_visible = false
        lyrics_visible = conservar
        if (conservar)
            overlay_lyrics._conservar_barra_visible_temporalmente()
        _restaurar_ventana_post_fullscreen()
    }

    function cerrar_colas_reproductor() {
        if (barra_principal)
            barra_principal.cerrar_cola()
        if (barra_lyrics)
            barra_lyrics.cerrar_cola()
    }

    function activar_atajos_reproduccion() {
        atajos_reproduccion_activos = true
    }

    function _hay_foco_en_texto() {
        var item = activeFocusItem
        if (!item)
            return false
        var nombreTipo = String(item).toLowerCase()
        return nombreTipo.indexOf("textinput") >= 0
                || nombreTipo.indexOf("textfield") >= 0
                || nombreTipo.indexOf("spinbox") >= 0
    }

    function _atajos_habilitados() {
        return atajos_reproduccion_activos && !_hay_foco_en_texto()
    }

    function _barra_activa() {
        return (overlay_lyrics.visible && overlay_lyrics.barra_visible) ? barra_lyrics : barra_principal
    }

    function alternar_cola_desde_atajo() {
        var barra = _barra_activa()
        if (barra)
            barra.alternar_cola()
    }

    function alternar_repeticion_desde_atajo() {
        var barra = _barra_activa()
        if (barra)
            barra.alternar_repeticion()
    }

    function ajustar_volumen(delta) {
        reproductor.set_volumen(Math.max(0, Math.min(100, reproductor.volumen + delta)))
    }

    function abrir_artista_desde_detalle(artista_id) {
        vista_activa = "biblioteca"
        _marcar_vista_visitada("biblioteca")
        biblioteca.abrir_artista(artista_id)
        Qt.callLater(function() {
            if (loader_biblioteca.item) {
                if (loader_biblioteca.item.abrir_artista_id) {
                    loader_biblioteca.item.abrir_artista_id(artista_id)
                } else {
                    loader_biblioteca.item.artista_activo = biblioteca.artista_detalle
                    loader_biblioteca.item.modo_vista = "artistas"
                    loader_biblioteca.item.detalle_artista_abierto = true
                    loader_biblioteca.item.detalle_abierto = false
                }
            }
        })
    }

    function abrir_album_desde_detalle(album_id) {
        vista_activa = "biblioteca"
        _marcar_vista_visitada("biblioteca")
        biblioteca.abrir_album(album_id)
        Qt.callLater(function() {
            if (loader_biblioteca.item) {
                if (loader_biblioteca.item.abrir_album_id) {
                    loader_biblioteca.item.abrir_album_id(album_id)
                } else {
                    loader_biblioteca.item.album_activo = biblioteca.album_detalle
                    loader_biblioteca.item.modo_vista = "albums"
                    loader_biblioteca.item.detalle_abierto = true
                    loader_biblioteca.item.detalle_artista_abierto = false
                }
            }
        })
    }

    function abrir_playlist_desde_inicio(playlist_id) {
        if (!playlist_id) return
        _playlistPendienteId = playlist_id
        vista_activa = "playlists"
        _marcar_vista_visitada("playlists")
        playlists.abrir_playlist(playlist_id)
        // If loader already has an item, navigate immediately
        if (loader_playlists.item && loader_playlists.item.abrir_playlist_id) {
            loader_playlists.item.abrir_playlist_id(playlist_id)
            _playlistPendienteId = 0
        }
        // Otherwise, onItemChanged on loader_playlists handles it when loader finishes
    }

    function abrir_pista_activa_en_biblioteca() {
        var pista = reproductor.pista_activa || {}
        if (!pista)
            return
        var resultado = biblioteca.abrir_album_desde_pista(pista)
        if (!resultado || !resultado.ok) {
            mostrar_toast_global(resultado && resultado.mensaje ? resultado.mensaje : "No se pudo abrir el album", "warning")
            return
        }
        if (resultado.fallback && resultado.mensaje)
            mostrar_toast_global(resultado.mensaje, "info")
        vista_activa = "biblioteca"
        _marcar_vista_visitada("biblioteca")
        Qt.callLater(function() {
            if (loader_biblioteca.item) {
                if (loader_biblioteca.item.abrir_album_id) {
                    loader_biblioteca.item.abrir_album_id(biblioteca.album_detalle.id)
                } else {
                    loader_biblioteca.item.album_activo = biblioteca.album_detalle
                    loader_biblioteca.item.modo_vista = "albums"
                    loader_biblioteca.item.detalle_abierto = true
                    loader_biblioteca.item.detalle_artista_abierto = false
                }
            }
        })
    }

    function abrir_artista_activo_en_biblioteca() {
        var pista = reproductor.pista_activa || {}
        if (!pista)
            return
        var resultado = biblioteca.abrir_artista_desde_pista(pista)
        if (!resultado || !resultado.ok) {
            mostrar_toast_global(resultado && resultado.mensaje ? resultado.mensaje : "No se pudo abrir el artista", "warning")
            return
        }
        if (resultado.fallback && resultado.mensaje)
            mostrar_toast_global(resultado.mensaje, "info")
        vista_activa = "biblioteca"
        _marcar_vista_visitada("biblioteca")
        Qt.callLater(function() {
            if (loader_biblioteca.item) {
                if (loader_biblioteca.item.abrir_artista_id) {
                    loader_biblioteca.item.abrir_artista_id(biblioteca.artista_detalle.id)
                } else {
                    loader_biblioteca.item.artista_activo = biblioteca.artista_detalle
                    loader_biblioteca.item.modo_vista = "artistas"
                    loader_biblioteca.item.detalle_artista_abierto = true
                    loader_biblioteca.item.detalle_abierto = false
                }
            }
        })
    }

    function abrir_album_activo_en_biblioteca() {
        abrir_pista_activa_en_biblioteca()
    }


    Connections {
        target: configuracion
        function onConfiguracionCambiada() {
            ventana_principal.escala_ui = _resolver_escala_ui()
            ventana_principal.fuente_ui = configuracion.obtener("ui_font_family") || "Inter"
        }
    }

    Connections {
        target: importacion
        function onImportacionFin() { refrescar_datos_ui() }
        function onImportacionCancelada() { refrescar_datos_ui() }
    }

    Connections {
        target: reproductor
        function onAvisoReproductor(aviso) {
            ventana_principal.manejar_aviso_reproductor(aviso)
        }
    }

    Shortcut {
        sequences: [StandardKey.Cancel]
        onActivated: {
            if (ventana_principal.reproduccion_expandida_visible) {
                ventana_principal.salir_fullscreen_reproductor(ventana_principal.lyrics_visible)
                return
            }
            if (ventana_principal.lyrics_visible)
                ventana_principal.lyrics_visible = false
        }
    }

    Shortcut { sequence: "Space"; enabled: ventana_principal._atajos_habilitados(); onActivated: reproductor.pausar_reanudar() }
    Shortcut { sequence: "Left"; enabled: ventana_principal._atajos_habilitados(); onActivated: reproductor.anterior() }
    Shortcut { sequence: "Right"; enabled: ventana_principal._atajos_habilitados(); onActivated: reproductor.siguiente() }
    Shortcut { sequence: "S"; enabled: ventana_principal._atajos_habilitados(); onActivated: reproductor.set_aleatorio(!reproductor.aleatorio) }
    Shortcut { sequence: "R"; enabled: ventana_principal._atajos_habilitados(); onActivated: ventana_principal.alternar_repeticion_desde_atajo() }
    Shortcut { sequence: "L"; enabled: ventana_principal._atajos_habilitados(); onActivated: ventana_principal.alternar_vista_lyrics() }
    Shortcut { sequence: "Ctrl+Q"; enabled: ventana_principal._atajos_habilitados(); onActivated: ventana_principal.alternar_cola_desde_atajo() }
    Shortcut { sequence: "Ctrl+M"; enabled: ventana_principal._atajos_habilitados(); onActivated: ventana_principal.alternar_modo_mini_reproductor() }
    Shortcut { sequence: "F"; enabled: ventana_principal._atajos_habilitados(); onActivated: ventana_principal.alternar_visualizacion_ampliada() }
    Shortcut { sequence: "+"; enabled: ventana_principal._atajos_habilitados(); onActivated: ventana_principal.ajustar_volumen(5) }
    Shortcut { sequence: "-"; enabled: ventana_principal._atajos_habilitados(); onActivated: ventana_principal.ajustar_volumen(-5) }

    Shortcut { sequence: "Media Play"; enabled: ventana_principal._atajos_habilitados(); onActivated: reproductor.pausar_reanudar() }
    Shortcut { sequence: "Media Pause"; enabled: ventana_principal._atajos_habilitados(); onActivated: reproductor.pausar_reanudar() }
    Shortcut { sequence: "Media Toggle Play/Pause"; enabled: ventana_principal._atajos_habilitados(); onActivated: reproductor.pausar_reanudar() }
    Shortcut { sequence: "Media Previous"; enabled: ventana_principal._atajos_habilitados(); onActivated: reproductor.anterior() }
    Shortcut { sequence: "Media Next"; enabled: ventana_principal._atajos_habilitados(); onActivated: reproductor.siguiente() }
    Shortcut { sequence: "Media Stop"; enabled: ventana_principal._atajos_habilitados(); onActivated: reproductor.detener() }
    Shortcut { sequence: "Volume Up"; enabled: ventana_principal._atajos_habilitados(); onActivated: ventana_principal.ajustar_volumen(5) }
    Shortcut { sequence: "Volume Down"; enabled: ventana_principal._atajos_habilitados(); onActivated: ventana_principal.ajustar_volumen(-5) }

    onVista_activaChanged: _marcar_vista_visitada(vista_activa)

    Component.onCompleted: {
        temaUi.recargar_desde_config()
        refrescar_datos_ui()
        reproductor.recargar_cola()
        reproductor.reenviar_avisos_retenidos()
        if ((configuracion.obtener("ui_mode") || "simple") !== "pro") {
            vista_activa = "inicio"
        }
    }

    Item {
        id: capa_overlays_globales
        anchors.fill: parent
        z: Math.max(
               ventana_principal.z_capa_lyrics,
               ventana_principal.overlay_fullscreen_info_visible ? ventana_principal.z_capa_fullscreen_info : -1,
               ventana_principal.overlay_fullscreen_lyrics_visible ? ventana_principal.z_capa_fullscreen_lyrics : -1
           )

        Rectangle {
            id: overlay_lyrics
            anchors.fill: parent
            visible: ventana_principal.overlay_lyrics_visible
                     || ventana_principal.overlay_fullscreen_info_visible
                     || ventana_principal.overlay_fullscreen_lyrics_visible
            z: ventana_principal.overlay_fullscreen_lyrics_visible
               ? ventana_principal.z_capa_fullscreen_lyrics
               : (ventana_principal.overlay_fullscreen_info_visible
                  ? ventana_principal.z_capa_fullscreen_info
                  : ventana_principal.z_capa_lyrics)
            color: tema.fondo
            clip: true
            property bool barra_hover: false
            property bool barra_visible: false
            property real barra_reveal_width: 0.0
            property real ultimo_mouse_y: -1
            property string modo_reveal_anterior: "none"
            readonly property string overlay_modo: ventana_principal.overlay_reproductor_modo
            readonly property bool overlay_en_fullscreen: overlay_modo === "fullscreen_info" || overlay_modo === "fullscreen_lyrics"
            readonly property real ancho_nav_overlay: Math.max(0, nav_lateral.width * ventana_principal.escala_ui)
            readonly property real ancho_barra_inicial: overlay_en_fullscreen
                                                         ? width
                                                         : Math.max(Math.min(width, 320), Math.max(0, width - ancho_nav_overlay))
            readonly property real ancho_barra_objetivo: width
            readonly property real barra_base_y: Math.max(0, height - ventana_principal.altura_barra_reproduccion)
            readonly property real barra_offset_y: barra_visible
                                                     ? 0
                                                     : Math.min(20, Math.max(12, ventana_principal.altura_barra_reproduccion * 0.22))
            readonly property real fade_reveal_width: Math.min(108, Math.max(52, width * 0.085))
            readonly property real zona_segura_barra: Math.max(148, ventana_principal.altura_barra_reproduccion + 24)

            function _modo_es_fullscreen(modo) {
                return modo === "fullscreen_info" || modo === "fullscreen_lyrics"
            }

            function _entrar_overlay_normal_con_reveal() {
                barra_hover = false
                barra_visible = false
                ultimo_mouse_y = -1
                barra_reveal_width = ancho_barra_inicial
                modo_reveal_anterior = overlay_modo
                Qt.callLater(function() {
                    if (overlay_lyrics.visible && !overlay_lyrics.overlay_en_fullscreen)
                        overlay_lyrics.barra_reveal_width = overlay_lyrics.ancho_barra_objetivo
                })
                auto_ocultar_barra.restart()
            }

            function _entrar_o_cambiar_fullscreen_sin_reveal(mostrarBarra) {
                barra_reveal_width = ancho_barra_objetivo
                modo_reveal_anterior = overlay_modo
                if (mostrarBarra) {
                    barra_hover = false
                    barra_visible = true
                    ultimo_mouse_y = -1
                    auto_ocultar_barra.restart()
                }
            }

            function _conservar_barra_visible_temporalmente() {
                if (!visible)
                    return
                barra_reveal_width = ancho_barra_objetivo
                barra_visible = true
                auto_ocultar_barra.restart()
            }

            function _salir_overlay() {
                barra_hover = false
                barra_visible = false
                ultimo_mouse_y = -1
                modo_reveal_anterior = "none"
                barra_reveal_width = 0
                auto_ocultar_barra.stop()
            }

            function _actualizar_barra_overlay_por_modo(forzarReveal) {
                if (!visible || overlay_modo === "none") {
                    _salir_overlay()
                    return
                }
                if (overlay_en_fullscreen) {
                    _entrar_o_cambiar_fullscreen_sin_reveal(forzarReveal)
                    return
                }
                if (forzarReveal)
                    _entrar_overlay_normal_con_reveal()
                else
                    barra_reveal_width = ancho_barra_objetivo
                modo_reveal_anterior = overlay_modo
            }

            function _mouse_en_zona_segura_barra() {
                return visible && ultimo_mouse_y >= 0 && ultimo_mouse_y >= (height - zona_segura_barra)
            }

            function _puede_ocultar_barra() {
                return visible
                        && barra_visible
                        && !barra_hover
                        && !barra_lyrics.cola_visible
                        && !_mouse_en_zona_segura_barra()
            }

            function _reportar_mouse(yPos) {
                if (!visible)
                    return
                ultimo_mouse_y = yPos
                if (_mouse_en_zona_segura_barra()) {
                    barra_visible = true
                    auto_ocultar_barra.stop()
                } else if (!barra_hover) {
                    auto_ocultar_barra.restart()
                }
            }

            onVisibleChanged: {
                if (visible) {
                    _actualizar_barra_overlay_por_modo(true)
                } else {
                    _salir_overlay()
                }
            }

            onOverlay_modoChanged: {
                ventana_principal.cerrar_colas_reproductor()
                if (_modo_es_fullscreen(modo_reveal_anterior) && _modo_es_fullscreen(overlay_modo)) {
                    _entrar_o_cambiar_fullscreen_sin_reveal(false)
                } else {
                    _actualizar_barra_overlay_por_modo(false)
                }
            }
            onWidthChanged: {
                if (overlay_en_fullscreen)
                    _entrar_o_cambiar_fullscreen_sin_reveal(false)
                else
                    _actualizar_barra_overlay_por_modo(false)
            }

            Behavior on barra_reveal_width {
                NumberAnimation { duration: 240; easing.type: Easing.OutCubic }
            }

            Timer {
                id: auto_ocultar_barra
                interval: 1900
                repeat: false
                onTriggered: {
                    if (overlay_lyrics._puede_ocultar_barra())
                        overlay_lyrics.barra_visible = false
                }
            }

            Loader {
                anchors.fill: parent
                anchors.bottomMargin: 0
                active: overlay_lyrics.visible
                sourceComponent: (ventana_principal.overlay_lyrics_visible || ventana_principal.overlay_fullscreen_lyrics_visible)
                                 ? comp_lyrics_solo
                                 : comp_reproduccion_expandida
            }

            Component {
                id: comp_lyrics_solo
                Vistas.VistaLyrics {
                    anchors.fill: parent
                    shell: ventana_principal
                }
            }

            Component {
                id: comp_reproduccion_expandida
                Vistas.VistaReproduccionExpandida {
                    anchors.fill: parent
                    shell: ventana_principal
                }
            }

            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.NoButton
                hoverEnabled: true
                propagateComposedEvents: true
                onPositionChanged: function(mouse) {
                    overlay_lyrics._reportar_mouse(mouse.y)
                }
                onExited: {
                    overlay_lyrics.ultimo_mouse_y = -1
                    if (!overlay_lyrics.barra_hover)
                        auto_ocultar_barra.restart()
                }
            }

            Item {
                id: barra_lyrics_cortina
                anchors.right: parent.right
                y: overlay_lyrics.barra_base_y + overlay_lyrics.barra_offset_y
                width: parent.width
                height: ventana_principal.altura_barra_reproduccion
                z: 2
                visible: overlay_lyrics.visible
                opacity: overlay_lyrics.barra_visible ? 1.0 : 0.0
                clip: true
                Behavior on y { NumberAnimation { duration: 190; easing.type: Easing.OutCubic } }
                Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutQuad } }

                Rectangle {
                    anchors.fill: parent
                    color: tema.fondoElevado
                }
            }

            Item {
                id: barra_lyrics_wrapper
                anchors.horizontalCenter: parent.horizontalCenter
                y: barra_lyrics_cortina.y
                width: overlay_lyrics.barra_reveal_width
                height: ventana_principal.altura_barra_reproduccion
                z: 3
                visible: overlay_lyrics.visible
                opacity: barra_lyrics_cortina.opacity
                clip: true
                Behavior on width { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
                Behavior on y { NumberAnimation { duration: 190; easing.type: Easing.OutCubic } }
                Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutQuad } }

                Componentes.BarraReproduccion {
                    id: barra_lyrics
                    shell: ventana_principal
                    capa_cola_z: ventana_principal.z_capa_cola
                    animacion_fase: ventana_principal.animacion_reproductor_fase
                    animacion_origen_x: 0
                    animacion_ancho_mundo: overlay_lyrics.width
                    anchors.fill: parent

                    MouseArea {
                        anchors.fill: parent
                        acceptedButtons: Qt.NoButton
                        hoverEnabled: true
                        onEntered: {
                            overlay_lyrics.barra_hover = true
                            overlay_lyrics.barra_visible = true
                            overlay_lyrics.ultimo_mouse_y = barra_lyrics_wrapper.y + mouseY
                            auto_ocultar_barra.stop()
                        }
                        onExited: {
                            overlay_lyrics.barra_hover = false
                            if (!barra_lyrics.cola_visible)
                                auto_ocultar_barra.restart()
                        }
                        onPositionChanged: function(mouse) {
                            overlay_lyrics._reportar_mouse(barra_lyrics_wrapper.y + mouse.y)
                        }
                    }
                }
            }

            Rectangle {
                id: barra_lyrics_fade_izquierdo
                y: barra_lyrics_cortina.y
                x: barra_lyrics_wrapper.x - (width * 0.72)
                width: overlay_lyrics.fade_reveal_width
                height: barra_lyrics_cortina.height
                z: 4
                visible: overlay_lyrics.visible && overlay_lyrics.barra_reveal_width < (overlay_lyrics.width - 1)
                opacity: barra_lyrics_cortina.opacity * Math.min(1.0, (1.0 - (overlay_lyrics.barra_reveal_width / Math.max(1, overlay_lyrics.width))) * 2.6)
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: Qt.rgba(tema.fondoElevado.r, tema.fondoElevado.g, tema.fondoElevado.b, 0.0) }
                    GradientStop { position: 0.54; color: Qt.rgba(tema.fondoElevado.r, tema.fondoElevado.g, tema.fondoElevado.b, 0.94) }
                    GradientStop { position: 1.0; color: Qt.rgba(tema.fondoElevado.r, tema.fondoElevado.g, tema.fondoElevado.b, 0.0) }
                }
                Behavior on opacity { NumberAnimation { duration: 160; easing.type: Easing.OutQuad } }
            }

            Rectangle {
                id: barra_lyrics_fade_derecho
                y: barra_lyrics_cortina.y
                x: barra_lyrics_wrapper.x + barra_lyrics_wrapper.width - (width * 0.28)
                width: overlay_lyrics.fade_reveal_width
                height: barra_lyrics_cortina.height
                z: 4
                visible: barra_lyrics_fade_izquierdo.visible
                opacity: barra_lyrics_fade_izquierdo.opacity
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: Qt.rgba(tema.fondoElevado.r, tema.fondoElevado.g, tema.fondoElevado.b, 0.0) }
                    GradientStop { position: 0.46; color: Qt.rgba(tema.fondoElevado.r, tema.fondoElevado.g, tema.fondoElevado.b, 0.94) }
                    GradientStop { position: 1.0; color: Qt.rgba(tema.fondoElevado.r, tema.fondoElevado.g, tema.fondoElevado.b, 0.0) }
                }
                Behavior on opacity { NumberAnimation { duration: 160; easing.type: Easing.OutQuad } }
            }
        }
    }

    Item {
        id: capa_toasts_globales
        anchors.fill: parent
        z: ventana_principal.z_capa_toasts

        Rectangle {
            id: alerta_error_global
            anchors.top: parent.top
            anchors.topMargin: Componentes.UiTokens.spacing16
            anchors.horizontalCenter: parent.horizontalCenter
            width: Math.min(parent.width - Componentes.UiTokens.spacing24 * 2, 620)
            height: Componentes.UiTokens.controlHeightLg
            radius: Componentes.UiTokens.radiusMd
            color: Qt.rgba(tema.peligro.r, tema.peligro.g, tema.peligro.b, 0.14)
            border.width: 1
            border.color: Qt.rgba(tema.peligro.r, tema.peligro.g, tema.peligro.b, 0.42)
            visible: ventana_principal.ultimo_error_global !== ""

            Componentes.AppText {
                anchors.left: parent.left
                anchors.right: cerrar_alerta.left
                anchors.leftMargin: Componentes.UiTokens.spacing12
                anchors.rightMargin: Componentes.UiTokens.spacing8
                anchors.verticalCenter: parent.verticalCenter
                text: ventana_principal.ultimo_error_global
                color: tema.texto
                font.pixelSize: Componentes.UiTokens.fontSizeMd
                elide: Text.ElideRight
            }

            Componentes.AppText {
                id: cerrar_alerta
                anchors.right: parent.right
                anchors.rightMargin: Componentes.UiTokens.spacing12
                anchors.verticalCenter: parent.verticalCenter
                text: "Cerrar"
                color: tema.texto
                font.pixelSize: Componentes.UiTokens.fontSizeSm
                font.bold: true
            }

            MouseArea {
                anchors.fill: cerrar_alerta
                cursorShape: Qt.PointingHandCursor
                onClicked: ventana_principal.ultimo_error_global = ""
            }
        }

        // ── Toast global ────────────────────────────────────────────────
        //
        // Reglas de posicionamiento:
        //   - Modo normal (barra reproductor abajo): toast por encima de la barra
        //     con un colchon de 16 px.
        //   - Modo fullscreen con barra revelada (overlay_lyrics.barra_visible):
        //     toast por encima del area de la barra revelada para no taparla.
        //   - Modo fullscreen sin barra: toast cerca del borde inferior con un
        //     margen relativo al alto de la ventana (no hardcodeado).
        //   - z por encima de TODOS los overlays (fullscreen, cola, lyrics) para
        //     que el feedback se perciba.
        //
        // El margen se calcula con respecto al tamano de la barra del
        // reproductor (escala con DPI/altura porque usa UiTokens) y nunca
        // queda pegado al fondo.
        Componentes.ToastMessage {
            id: toast_global
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: {
                var pad = Componentes.UiTokens.spacing16
                if (ventana_principal.barra_reproduccion_visible) {
                    return ventana_principal.altura_barra_reproduccion + pad
                }
                if (ventana_principal.barra_overlay_visible) {
                    return ventana_principal.altura_barra_reproduccion + pad
                }
                // Fullscreen sin barra revelada: dejamos espacio para el indicador
                // hover-to-reveal sin pegar al fondo. ~6% de la altura, mínimo 32.
                return Math.max(32, Math.round(ventana_principal.height * 0.06))
            }
            foregroundColor: tema.texto
            z: ventana_principal.z_capa_toasts
        }
    }

    Dialog {
        id: dialog_error_reproductor
        parent: Overlay.overlay
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape
        standardButtons: Dialog.Ok
        title: ventana_principal.alerta_reproductor_critica.titulo || "Error del reproductor"
        width: Math.min(560, ventana_principal.width - Componentes.UiTokens.spacing24 * 2)
        x: Math.round((parent.width - width) / 2)
        y: Math.round((parent.height - height) / 2)
        padding: Componentes.UiTokens.spacing16

        background: Rectangle {
            radius: Componentes.UiTokens.radiusMd
            color: tema.fondoElevado
            border.width: 1
            border.color: Qt.rgba(tema.peligro.r, tema.peligro.g, tema.peligro.b, 0.45)
        }

        contentItem: ColumnLayout {
            spacing: Componentes.UiTokens.spacing10

            Componentes.AppText {
                Layout.fillWidth: true
                text: ventana_principal.alerta_reproductor_critica.mensaje || ""
                color: tema.texto
                font.pixelSize: Componentes.UiTokens.fontSizeMd
                wrapMode: Text.WordWrap
            }

            Repeater {
                model: ventana_principal.alerta_reproductor_critica.soluciones || []
                delegate: Componentes.AppText {
                    Layout.fillWidth: true
                    text: "- " + String(modelData || "")
                    color: tema.textoSec
                    font.pixelSize: Componentes.UiTokens.fontSizeSm
                    wrapMode: Text.WordWrap
                }
            }
        }
    }

    Window {
        id: mini_window
        visible: ventana_principal.mini_reproductor_activo
        width: ancho_fijo_mini
        height: alto_fijo_mini
        minimumWidth: ancho_fijo_mini
        minimumHeight: alto_fijo_mini
        maximumWidth: ancho_fijo_mini
        maximumHeight: alto_fijo_mini
        title: "NB Sound · Mini reproductor"
        color: "transparent"
        flags: Qt.Tool | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint
        modality: Qt.NonModal
        transientParent: null

        readonly property int ancho_fijo_mini: 430
        readonly property int alto_fijo_mini: 246
        property bool posicion_mini_definida: false
        readonly property var pistaMini: reproductor.pista_visual || ({})
        readonly property var moodMini: reproductor.mood_visual || ({})
        readonly property bool hayPistaActivaMini: _hayPistaActiva(reproductor.pista_activa || ({}))
        readonly property bool hayPistaMini: _hayPistaActiva(pistaMini)
        readonly property bool puedeReproducirMini: hayPistaMini || reproductor.cola.total > 0
        readonly property bool duracionMiniConocida: hayPistaActivaMini && _numeroSeguro(reproductor.duracion_seg) > 0
        readonly property string tituloMini: hayPistaMini ? (_textoSeguro(pistaMini.titulo) || _textoSeguro(reproductor.titulo_activo) || "Pista sin título") : "Sin reproducción activa"
        readonly property string artistaMini: hayPistaMini ? (_textoSeguro(pistaMini.artista_nombre) || _textoSeguro(pistaMini.artista) || _textoSeguro(reproductor.artista_activo) || "Artista desconocido") : "Selecciona una pista desde biblioteca"
        readonly property string albumMini: hayPistaMini ? (_textoSeguro(pistaMini.album_titulo) || _textoSeguro(pistaMini.album) || _textoSeguro(reproductor.album_activo)) : ""
        readonly property string portadaMini: pistaMini.portada_ruta ? UiUtils.toMediaSource(pistaMini.portada_ruta) : ""
        readonly property string iconoPlayMini: !puedeReproducirMini ? "assets/icons/idle.svg" : (reproductor.reproduciendo ? "assets/icons/pause.svg" : "assets/icons/play.svg")
        readonly property bool controles_visibles: !hayPistaMini || hover_mini.hovered
        readonly property int ancho_lateral_controles_mini: 92
        readonly property int ancho_slider_volumen_mini: 42
        property real tam_portada_mini: controles_visibles ? 112 : 164
        property real titulo_mini_size: controles_visibles ? 17 : 22
        property real artista_mini_size: controles_visibles ? 12 : 15
        property real album_mini_size: controles_visibles ? 11 : 13
        property real alto_controles_mini: controles_visibles ? 78 : 0
        property bool arrastre_manual_mini: false

        Behavior on tam_portada_mini { NumberAnimation { duration: Componentes.UiTokens.durationBase; easing.type: Easing.OutQuad } }
        Behavior on titulo_mini_size { NumberAnimation { duration: Componentes.UiTokens.durationBase; easing.type: Easing.OutQuad } }
        Behavior on artista_mini_size { NumberAnimation { duration: Componentes.UiTokens.durationBase; easing.type: Easing.OutQuad } }
        Behavior on album_mini_size { NumberAnimation { duration: Componentes.UiTokens.durationBase; easing.type: Easing.OutQuad } }
        Behavior on alto_controles_mini { NumberAnimation { duration: Componentes.UiTokens.durationBase; easing.type: Easing.OutQuad } }

        function _textoSeguro(valor) {
            if (valor === undefined || valor === null)
                return ""
            return String(valor).trim()
        }

        function _hayPistaActiva(pista) {
            return !!pista && !!_textoSeguro(pista.ruta_archivo)
        }

        function _numeroSeguro(valor) {
            var numero = Number(valor)
            return isFinite(numero) ? numero : 0
        }

        function _ratioSeguro(valor) {
            return Math.max(0, Math.min(1, _numeroSeguro(valor)))
        }

        function _colorMood(luminosidad, alpha) {
            var h = _ratioSeguro(moodMini.h)
            var s = Math.max(0.28, Math.min(0.58, _numeroSeguro(moodMini.s) + 0.08))
            var l = Math.max(0.08, Math.min(0.24, luminosidad))
            return Qt.hsla(h, s, l, alpha)
        }

        function _pantallaX() {
            return Screen.virtualX || 0
        }

        function _pantallaY() {
            return Screen.virtualY || 0
        }

        function _pantallaAncho() {
            return Screen.desktopAvailableWidth || Screen.width || 1280
        }

        function _pantallaAlto() {
            return Screen.desktopAvailableHeight || Screen.height || 720
        }

        function _esta_dentro_de_pantalla() {
            var sx = _pantallaX()
            var sy = _pantallaY()
            var sw = _pantallaAncho()
            var sh = _pantallaAlto()
            return x + 80 > sx && y + 60 > sy && x < sx + sw - 40 && y < sy + sh - 40
        }

        function _posicionar_inferior_derecha() {
            var margen = Componentes.UiTokens.spacing20
            x = _pantallaX() + Math.max(0, _pantallaAncho() - width - margen)
            y = _pantallaY() + Math.max(0, _pantallaAlto() - height - margen)
            posicion_mini_definida = true
        }

        function _limitar_mini_a_pantalla() {
            var sx = _pantallaX()
            var sy = _pantallaY()
            var maxX = Math.max(sx, sx + _pantallaAncho() - width)
            var maxY = Math.max(sy, sy + _pantallaAlto() - height)
            x = Math.max(sx, Math.min(x, maxX))
            y = Math.max(sy, Math.min(y, maxY))
            posicion_mini_definida = true
        }

        function _preparar_arrastre_manual_mini() {
            arrastre_manual_mini = true
            drag_proxy_mini.ignorarCambios = true
            drag_proxy_mini.x = 0
            drag_proxy_mini.y = 0
            drag_proxy_mini.ultimoX = 0
            drag_proxy_mini.ultimoY = 0
            drag_proxy_mini.ignorarCambios = false
        }

        function _iniciar_arrastre_mini() {
            posicion_mini_definida = true
            arrastre_manual_mini = false
            if (typeof mini_window.startSystemMove === "function") {
                mini_window.startSystemMove()
                return
            }
            _preparar_arrastre_manual_mini()
        }

        function _finalizar_arrastre_mini() {
            arrastre_manual_mini = false
            posicion_mini_definida = true
        }

        function preparar_apertura() {
            if (!posicion_mini_definida || !_esta_dentro_de_pantalla())
                _posicionar_inferior_derecha()
            _limitar_mini_a_pantalla()
            raise()
            requestActivate()
        }

        onVisibleChanged: {
            if (visible)
                preparar_apertura()
        }

        onClosing: function(close) {
            close.accepted = false
            ventana_principal.cerrar_mini_reproductor()
        }

        Shortcut {
            sequence: "Esc"
            enabled: mini_window.visible
            onActivated: ventana_principal.cerrar_mini_reproductor()
        }

        Rectangle {
            anchors.fill: parent
            radius: Componentes.UiTokens.radiusLg
            color: tema.fondo
            border.color: Qt.rgba(tema.texto.r, tema.texto.g, tema.texto.b, 0.18)
            border.width: 1
            clip: true

            HoverHandler {
                id: hover_mini
                acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
            }

            Rectangle {
                anchors.fill: parent
                color: mini_window._colorMood(0.13, 0.58)
            }

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: parent.height * 0.58
                color: mini_window._colorMood(0.20, 0.24)
            }

            Item {
                id: drag_proxy_mini
                width: 1
                height: 1
                opacity: 0
                property real ultimoX: 0
                property real ultimoY: 0
                property bool ignorarCambios: false
                onXChanged: {
                    if (!mini_window.arrastre_manual_mini || ignorarCambios)
                        return
                    mini_window.x += x - ultimoX
                    ultimoX = x
                    mini_window.posicion_mini_definida = true
                }
                onYChanged: {
                    if (!mini_window.arrastre_manual_mini || ignorarCambios)
                        return
                    mini_window.y += y - ultimoY
                    ultimoY = y
                    mini_window.posicion_mini_definida = true
                }
            }

            Item {
                id: asa_drag_visual_mini
                width: 64
                height: 22
                anchors.top: parent.top
                anchors.topMargin: Componentes.UiTokens.spacing6
                anchors.horizontalCenter: parent.horizontalCenter
                z: 6
                opacity: asa_drag_mini.containsMouse || asa_drag_mini.pressed ? 0.95 : 0.54

                Behavior on opacity { NumberAnimation { duration: Componentes.UiTokens.durationBase } }
                SequentialAnimation on scale {
                    running: !asa_drag_mini.pressed
                    loops: Animation.Infinite
                    NumberAnimation { to: 1.04; duration: 1200; easing.type: Easing.InOutSine }
                    NumberAnimation { to: 1.0; duration: 1200; easing.type: Easing.InOutSine }
                }

                Image {
                    anchors.centerIn: parent
                    width: 30
                    height: 18
                    source: "assets/icons/drag-handle.svg"
                    sourceSize.width: 60
                    sourceSize.height: 36
                    smooth: true
                    opacity: 0.92
                }

                MouseArea {
                    id: asa_drag_mini
                    anchors.fill: parent
                    hoverEnabled: true
                    acceptedButtons: Qt.LeftButton
                    cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                    drag.target: drag_proxy_mini
                    drag.axis: Drag.XAndYAxis
                    drag.minimumX: -10000
                    drag.maximumX: 10000
                    drag.minimumY: -10000
                    drag.maximumY: 10000
                    drag.smoothed: false

                    onPressed: function(mouse) {
                        mini_window._iniciar_arrastre_mini()
                        mouse.accepted = true
                    }
                    onReleased: mini_window._finalizar_arrastre_mini()
                    onCanceled: mini_window._finalizar_arrastre_mini()
                }
            }

            MiniIconButton {
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.topMargin: Componentes.UiTokens.spacing6
                anchors.rightMargin: Componentes.UiTokens.spacing8
                z: 7
                iconSource: "assets/icons/close.svg"
                buttonSize: 26
                iconSize: 13
                flatChrome: true
                opacity: mini_window.controles_visibles ? 1 : 0
                enabled: mini_window.controles_visibles
                onClicked: ventana_principal.cerrar_mini_reproductor()
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.leftMargin: Componentes.UiTokens.spacing14
                anchors.rightMargin: Componentes.UiTokens.spacing14
                anchors.topMargin: Componentes.UiTokens.spacing24
                anchors.bottomMargin: Componentes.UiTokens.spacing12
                spacing: mini_window.controles_visibles ? Componentes.UiTokens.spacing8 : Componentes.UiTokens.spacing4

                RowLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.alignment: Qt.AlignVCenter
                    spacing: mini_window.controles_visibles ? Componentes.UiTokens.spacing14 : Componentes.UiTokens.spacing20

                    Rectangle {
                        id: portada_mini_marco
                        Layout.preferredWidth: mini_window.tam_portada_mini
                        Layout.preferredHeight: mini_window.tam_portada_mini
                        Layout.alignment: Qt.AlignVCenter
                        radius: Componentes.UiTokens.radiusMd
                        clip: true
                        color: UiUtils.veloClaro(0.08)
                        border.color: UiUtils.veloClaro(0.14)
                        border.width: 1

                        Image {
                            id: portada_mini_imagen
                            anchors.fill: parent
                            source: mini_window.portadaMini
                            visible: mini_window.portadaMini !== "" && status === Image.Ready
                            fillMode: Image.PreserveAspectCrop
                            asynchronous: true
                            sourceSize.width: 256
                            sourceSize.height: 256
                            smooth: true
                        }

                        Rectangle {
                            anchors.fill: parent
                            visible: !portada_mini_imagen.visible
                            color: UiUtils.veloClaro(0.07)

                            Image {
                                anchors.centerIn: parent
                                width: 34
                                height: 34
                                source: "assets/icons/idle.svg"
                                opacity: 0.82
                                sourceSize.width: 68
                                sourceSize.height: 68
                                smooth: true
                            }
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: mini_window.tam_portada_mini
                        Layout.alignment: Qt.AlignVCenter
                        spacing: Componentes.UiTokens.spacing4

                        Item { Layout.fillHeight: true }

                        Componentes.AppText {
                            Layout.fillWidth: true
                            text: mini_window.tituloMini
                            color: tema.textoInmersivo
                            font.pixelSize: mini_window.titulo_mini_size
                            font.bold: true
                            maximumLineCount: 2
                            wrapMode: Text.Wrap
                            elide: Text.ElideRight
                            font.letterSpacing: 0
                        }

                        Componentes.AppText {
                            Layout.fillWidth: true
                            text: mini_window.artistaMini
                            color: UiUtils.veloClaro(0.76)
                            font.pixelSize: mini_window.artista_mini_size
                            maximumLineCount: 1
                            elide: Text.ElideRight
                            font.letterSpacing: 0
                        }

                        Componentes.AppText {
                            Layout.fillWidth: true
                            visible: text !== ""
                            text: mini_window.albumMini
                            color: UiUtils.veloClaro(0.54)
                            font.pixelSize: mini_window.album_mini_size
                            maximumLineCount: 1
                            elide: Text.ElideRight
                            font.letterSpacing: 0
                        }

                        Item { Layout.fillHeight: true }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: mini_window.alto_controles_mini
                    spacing: Componentes.UiTokens.spacing6
                    opacity: mini_window.controles_visibles ? 1 : 0
                    clip: true
                    enabled: opacity > 0.5

                    Behavior on opacity { NumberAnimation { duration: Componentes.UiTokens.durationBase } }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Componentes.UiTokens.spacing6

                        Componentes.AppText {
                            text: mini_window.duracionMiniConocida ? reproductor.formatear_tiempo(reproductor.posicion_seg) : "--:--"
                            color: UiUtils.veloClaro(0.64)
                            font.pixelSize: Componentes.UiTokens.fontSizeXs
                            Layout.preferredWidth: 38
                            horizontalAlignment: Text.AlignRight
                            font.letterSpacing: 0
                        }

                        Componentes.SliderLine {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 24
                            tema: ventana_principal.tema
                            ratio: mini_window._ratioSeguro(reproductor.progreso_ratio)
                            live: false
                            visualHeight: 4
                            handleBaseSize: 8
                            handleActiveSize: 12
                            enabled: mini_window.duracionMiniConocida
                            onCommitted: function(ratio) {
                                reproductor.buscar_posicion(ratio * reproductor.duracion_seg)
                            }
                        }

                        Componentes.AppText {
                            text: mini_window.duracionMiniConocida ? reproductor.formatear_tiempo(reproductor.duracion_seg) : "--:--"
                            color: UiUtils.veloClaro(0.64)
                            font.pixelSize: Componentes.UiTokens.fontSizeXs
                            Layout.preferredWidth: 38
                            horizontalAlignment: Text.AlignLeft
                            font.letterSpacing: 0
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        Layout.preferredHeight: 44
                        spacing: Componentes.UiTokens.spacing8

                        Item {
                            Layout.preferredWidth: mini_window.ancho_lateral_controles_mini
                            Layout.preferredHeight: 40
                            Layout.alignment: Qt.AlignVCenter

                            MiniIconButton {
                                anchors.left: parent.left
                                anchors.verticalCenter: parent.verticalCenter
                                iconSource: "assets/icons/surprise.svg"
                                activo: reproductor.sorpresa_activa
                                onClicked: reproductor.sorprenderme()
                            }
                        }

                        Item {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 40
                            Layout.alignment: Qt.AlignVCenter

                            Row {
                                anchors.centerIn: parent
                                spacing: Componentes.UiTokens.spacing8

                                MiniIconButton {
                                    iconSource: "assets/icons/prev.svg"
                                    enabled: mini_window.puedeReproducirMini
                                    onClicked: reproductor.anterior()
                                }
                                MiniIconButton {
                                    iconSource: mini_window.iconoPlayMini
                                    primary: true
                                    buttonSize: 32
                                    iconSize: 15
                                    enabled: mini_window.puedeReproducirMini
                                    onClicked: reproductor.pausar_reanudar()
                                }
                                MiniIconButton {
                                    iconSource: "assets/icons/next.svg"
                                    enabled: mini_window.puedeReproducirMini
                                    onClicked: reproductor.siguiente()
                                }
                            }
                        }

                        Item {
                            Layout.preferredWidth: mini_window.ancho_lateral_controles_mini
                            Layout.preferredHeight: 40
                            Layout.alignment: Qt.AlignVCenter

                            Row {
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: Componentes.UiTokens.spacing6

                                Image {
                                    width: 16
                                    height: 16
                                    anchors.verticalCenter: parent.verticalCenter
                                    source: "assets/icons/volume.svg"
                                    opacity: reproductor.volumen > 0 ? 0.9 : 0.42
                                    sourceSize.width: 32
                                    sourceSize.height: 32
                                    smooth: true
                                }

                                Componentes.SliderLine {
                                    width: mini_window.ancho_slider_volumen_mini
                                    height: 24
                                    anchors.verticalCenter: parent.verticalCenter
                                    tema: ventana_principal.tema
                                    ratio: mini_window._ratioSeguro(reproductor.volumen / 100)
                                    visualHeight: 4
                                    handleBaseSize: 8
                                    handleActiveSize: 12
                                    enabled: true
                                    onMoved: function(ratio) {
                                        reproductor.set_volumen(Math.round(ratio * 100))
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        component MiniIconButton: Button {
            id: boton_mini
            property string iconSource: ""
            property bool primary: false
            property bool flatChrome: false
            property bool activo: false
            property real buttonSize: primary ? 40 : 32
            property real iconSize: primary ? 18 : 15

            function _fondo() {
                if (!enabled)
                    return UiUtils.veloClaro(0.06)
                if (primary)
                    return down || hovered ? tema.acentoFuerte : tema.acento
                if (down)
                    return Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.24)
                if (activo)
                    return Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.18)
                if (hovered)
                    return UiUtils.veloClaro(flatChrome ? 0.12 : 0.16)
                return flatChrome ? "transparent" : UiUtils.veloClaro(0.08)
            }

            function _colorIcono() {
                if (!enabled)
                    return UiUtils.veloClaro(0.36)
                if (primary)
                    return tema.fondo
                if (activo || down || hovered)
                    return tema.texto
                return UiUtils.veloClaro(0.76)
            }

            text: ""
            display: AbstractButton.IconOnly
            padding: 0
            hoverEnabled: true
            focusPolicy: Qt.TabFocus
            implicitWidth: buttonSize
            implicitHeight: buttonSize
            Layout.preferredWidth: buttonSize
            Layout.preferredHeight: buttonSize
            opacity: enabled ? 1.0 : 0.42
            scale: down && enabled ? 0.95 : 1.0
            icon.source: iconSource
            icon.width: iconSize
            icon.height: iconSize
            icon.color: _colorIcono()

            Behavior on scale { NumberAnimation { duration: Componentes.UiTokens.durationFast } }
            Behavior on opacity { NumberAnimation { duration: Componentes.UiTokens.durationBase } }

            background: Rectangle {
                radius: Componentes.UiTokens.radiusSm
                color: boton_mini._fondo()
                border.color: boton_mini.activo ? tema.acento : (boton_mini.hovered && !boton_mini.primary ? UiUtils.veloClaro(0.14) : "transparent")
                border.width: (boton_mini.activo || (boton_mini.hovered && !boton_mini.primary)) ? 1 : 0

                Behavior on color { ColorAnimation { duration: Componentes.UiTokens.durationBase } }
                Behavior on border.color { ColorAnimation { duration: Componentes.UiTokens.durationBase } }
            }
        }
    }


}
