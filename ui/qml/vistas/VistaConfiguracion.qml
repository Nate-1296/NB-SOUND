import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import QtQuick.Effects
import Qt5Compat.GraphicalEffects
import "../componentes"

Rectangle {
    id: raiz
    objectName: "vista_configuracion"
    property var shell: null
    readonly property var tema: shell ? shell.tema : temaUi
    color: tema.fondo

    property string seccion_activa: "basica"
    property string modoUi: configuracion.obtener("ui_mode") || "simple"
    readonly property int contentMaxWidth: 1080
    readonly property int sectionSpacing: UiTokens.spacing24
    readonly property int horizontalPadding: raiz.width >= 1200 ? 44 : (raiz.width >= 860 ? 32 : UiTokens.spacing20)
    readonly property bool mediumWidth: raiz.width >= 920
    readonly property bool compactWidth: raiz.width < 760
    readonly property bool esPro: modoUi === "pro"
    readonly property var basicaKeys: [
        "dir_entrada", "dir_biblioteca", "dir_cuarentena", "dir_revision",
        "dir_logs", "dir_procesados"
    ]

    // Contadores de revisión para forzar re-evaluación de bindings con objetos JS
    property int _basicaRev: 0
    property int _avanzadaRev: 0
    property int _personalRev: 0

    property var basicaDraft: ({})
    property var avanzadaDraft: ({})
    property var rutasErrores: ({})
    property bool _draftsInicializados: false

    property var fontOptions: []
    readonly property var scaleOptions: ["100", "125", "150", "175", "200"]
    property string fuenteUi: shell ? shell.fuente_ui : (configuracion.obtener("ui_font_family") || "Inter")

    function clonarDraft(origen) {
        const copia = {}
        const base = origen || {}
        for (const clave in base) copia[clave] = base[clave]
        return copia
    }

    function sincronizarModoUi() {
        modoUi = configuracion.obtener("ui_mode") || "simple"
        if (modoUi !== "pro" && seccion_activa === "avanzada") {
            seccion_activa = "basica"
        }
    }

    function setBasicaValue(clave, valor) {
        const texto = String(valor === undefined || valor === null ? "" : valor)
        const draft = clonarDraft(basicaDraft)
        if (String(draft[clave] || "") === texto) return
        draft[clave] = texto
        basicaDraft = draft
        _basicaRev++
    }

    function setAvanzadaValue(clave, valor) {
        const texto = String(valor === undefined || valor === null ? "" : valor)
        const draft = clonarDraft(avanzadaDraft)
        if (String(draft[clave] || "") === texto) return
        draft[clave] = texto
        avanzadaDraft = draft
        _avanzadaRev++
    }

    function setAvanzadaValues(valores) {
        const draft = clonarDraft(avanzadaDraft)
        let cambio = false
        for (const clave in valores) {
            const texto = String(valores[clave] === undefined || valores[clave] === null ? "" : valores[clave])
            if (String(draft[clave] || "") !== texto) {
                draft[clave] = texto
                cambio = true
            }
        }
        if (!cambio) return
        avanzadaDraft = draft
        _avanzadaRev++
    }

    function setDraftValue(draftObj, clave, valor) {
        if (draftObj === basicaDraft) {
            setBasicaValue(clave, valor)
        } else if (draftObj === avanzadaDraft) {
            setAvanzadaValue(clave, valor)
        } else {
            console.warn("Draft de configuración no reconocido para", clave)
        }
    }

    function construirFontOptions() {
        // Selección curada: amplia, legible y sin fuentes de iconos/símbolos.
        // Solo se muestran familias realmente disponibles para Qt en el sistema/app.
        const detectadas = (configuracion.fuentes_disponibles && configuracion.fuentes_disponibles.length > 0)
            ? configuracion.fuentes_disponibles
            : Qt.fontFamilies()

        const preferidas = [
            // UI modernas / limpias
            "Inter", "Roboto", "Noto Sans", "Open Sans", "Lato", "Montserrat",
            "Source Sans 3", "Source Sans Pro", "IBM Plex Sans", "Fira Sans", "Ubuntu",
            "Cantarell", "Segoe UI", "SF Pro Text", "Helvetica Neue", "Arial",

            // Humanistas / lectura larga
            "Aptos", "Calibri", "Carlito", "Corbel", "Trebuchet MS", "Verdana",
            "DejaVu Sans", "Liberation Sans", "Nimbus Sans", "PT Sans",

            // Geométricas / display moderado
            "Poppins", "Nunito", "Nunito Sans", "Raleway", "Quicksand", "Manrope",
            "Rubik", "Work Sans", "DM Sans", "Urbanist",

            // Serif clásicas y editoriales
            "Noto Serif", "Source Serif 4", "Source Serif Pro", "IBM Plex Serif",
            "Merriweather", "Lora", "Georgia", "Cambria", "Caladea", "Times New Roman",
            "Liberation Serif", "DejaVu Serif", "Nimbus Roman",

            // Mono legibles para estética técnica
            "JetBrains Mono", "Fira Code", "Cascadia Code", "Cascadia Mono",
            "Source Code Pro", "IBM Plex Mono", "Roboto Mono", "Ubuntu Mono",
            "Noto Sans Mono", "DejaVu Sans Mono", "Liberation Mono", "Consolas"
        ]

        const bloqueadas = [
            "emoji", "symbol", "symbols", "dingbats", "webdings", "wingdings",
            "icons", "icon", "fontawesome", "font awesome", "material icons",
            "bootstrap-icons", "codicon", "octicons", "devicons", "nerd font",
            "weather icons", "noto color emoji", "noto emoji", "seguiemj", "seguisym"
        ]

        const porNombre = {}
        for (let i = 0; i < detectadas.length; i++) {
            const nombre = String(detectadas[i] || "").trim()
            if (nombre !== "") porNombre[nombre.toLowerCase()] = nombre
        }

        const vistos = {}
        const salida = []
        const maxFuentes = 30

        function esValida(nombre) {
            const limpio = String(nombre || "").trim()
            if (limpio === "") return false
            const lower = limpio.toLowerCase()
            for (let i = 0; i < bloqueadas.length; i++) {
                if (lower.indexOf(bloqueadas[i]) >= 0) return false
            }
            return true
        }

        function agregar(nombre) {
            const limpio = String(nombre || "").trim()
            if (!esValida(limpio)) return
            const key = limpio.toLowerCase()
            if (vistos[key]) return
            vistos[key] = true
            salida.push(limpio)
        }

        // Primero: selección curada, pero solo si está instalada/disponible.
        for (let i = 0; i < preferidas.length && salida.length < maxFuentes; i++) {
            const real = porNombre[preferidas[i].toLowerCase()]
            if (real) agregar(real)
        }

        // Después: completar con otras familias del sistema que pasen el filtro.
        const restantes = detectadas.slice().sort(function(a, b) {
            return String(a).localeCompare(String(b))
        })
        for (let j = 0; j < restantes.length && salida.length < maxFuentes; j++) {
            agregar(restantes[j])
        }

        // Fallback defensivo para que la UI nunca quede sin opciones.
        if (salida.length === 0) {
            agregar("Inter")
            agregar("Noto Sans")
            agregar("Arial")
        }

        return salida
    }

    function initDrafts() {
        basicaDraft = {
            "dir_entrada": configuracion.obtener("dir_entrada"),
            "dir_biblioteca": configuracion.obtener("dir_biblioteca"),
            "dir_revision": configuracion.obtener("dir_revision"),
            "dir_cuarentena": configuracion.obtener("dir_cuarentena"),
            "dir_logs": configuracion.obtener("dir_logs"),
            "dir_procesados": configuracion.obtener("dir_procesados"),
            "dir_assets": configuracion.obtener("dir_assets"),
            "dir_cache": configuracion.obtener("dir_cache"),
            "dir_temp": configuracion.obtener("dir_temp"),
            "dir_manifests": configuracion.obtener("dir_manifests"),
            "enable_acoustid": configuracion.obtener("enable_acoustid") || "1",
            "acoustid_key": configuracion.obtener("acoustid_key"),
            "enable_shazam": configuracion.obtener("enable_shazam") || "1"
        }
        avanzadaDraft = {
            "enable_ia_tiebreak": configuracion.obtener("enable_ia_tiebreak") || "1",
            "anthropic_key": configuracion.obtener("anthropic_key"),
            "openai_key": configuracion.obtener("openai_key"),
            "ia_proveedor": configuracion.obtener("ia_proveedor") || "No",
            "shazam_timeout_seg": configuracion.obtener("shazam_timeout_seg") || "12",
            "shazam_min_duracion_seg": configuracion.obtener("shazam_min_duracion_seg") || "20",
            "ia_tiebreak_min_gap": configuracion.obtener("ia_tiebreak_min_gap") || "0.12",
            "ia_max_tokens": configuracion.obtener("ia_max_tokens") || "512",
            "ia_timeout_seg": configuracion.obtener("ia_timeout_seg") || "20",
            "skip_already_processed": configuracion.obtener("skip_already_processed") || "0",
            "init_component_max_retries": configuracion.obtener("init_component_max_retries") || "2",
            "init_component_retry_backoff_seg": configuracion.obtener("init_component_retry_backoff_seg") || "0.7",
            "enable_deduplication": configuracion.obtener("enable_deduplication") || "1",
            "enable_semantic_deduplication": configuracion.obtener("enable_semantic_deduplication") || "1",
            "duplicate_policy": configuracion.obtener("duplicate_policy") || "replace_if_better",
            "duplicate_better_min_delta": configuracion.obtener("duplicate_better_min_delta") || "0.08",
            "enable_assets_pipeline": configuracion.obtener("enable_assets_pipeline") || "1",
            "enable_cover_art_archive": configuracion.obtener("enable_cover_art_archive") || "1",
            "enable_theaudiodb_artist_images": configuracion.obtener("enable_theaudiodb_artist_images") || "1",
            "enable_itunes_cover_fallback": configuracion.obtener("enable_itunes_cover_fallback") || "1",
            "enable_deezer_artist_images": configuracion.obtener("enable_deezer_artist_images") || "1",
            "enable_wikipedia_artist_images": configuracion.obtener("enable_wikipedia_artist_images") || "1",
            "enable_itunes_artist_images": configuracion.obtener("enable_itunes_artist_images") || "1",
            "theaudiodb_api_key": configuracion.obtener("theaudiodb_api_key") || "123",
            "assets_timeout_seg": configuracion.obtener("assets_timeout_seg") || "10",
            "assets_max_retries": configuracion.obtener("assets_max_retries") || "2",
            "assets_retry_backoff_seg": configuracion.obtener("assets_retry_backoff_seg") || "0.8",
            "assets_cache_ttl_seg": configuracion.obtener("assets_cache_ttl_seg") || "259200",
            "assets_negative_cache_ttl_seg": configuracion.obtener("assets_negative_cache_ttl_seg") || "21600",
            "assets_min_resolution": configuracion.obtener("assets_min_resolution") || "250",
            "assets_hd_max_image_bytes": configuracion.obtener("assets_hd_max_image_bytes") || "25000000",
            "enable_external_enrichment": configuracion.obtener("enable_external_enrichment") || "1",
            "enable_lyrics_enrichment": configuracion.obtener("enable_lyrics_enrichment") || "1",
            "enable_lrclib": configuracion.obtener("enable_lrclib") || "1",
            "enable_lyrics_ovh": configuracion.obtener("enable_lyrics_ovh") || "1",
            "lyrics_timeout_seg": configuracion.obtener("lyrics_timeout_seg") || "8",
            "lyrics_max_retries": configuracion.obtener("lyrics_max_retries") || "1",
            "lyrics_retry_backoff_seg": configuracion.obtener("lyrics_retry_backoff_seg") || "0.8",
            "lyrics_suggest_limit": configuracion.obtener("lyrics_suggest_limit") || "3",
            "enable_second_stage_resolution": configuracion.obtener("enable_second_stage_resolution") || "1",
            "second_stage_max_candidates": configuracion.obtener("second_stage_max_candidates") || "5",
            "second_stage_min_evidence": configuracion.obtener("second_stage_min_evidence") || "0.86",
            "second_stage_min_gap": configuracion.obtener("second_stage_min_gap") || "0.12",
            "second_stage_cause_enabled": configuracion.obtener("second_stage_cause_enabled") || "1",
            "enable_third_stage_resolution": configuracion.obtener("enable_third_stage_resolution") || "1",
            "third_stage_min_evidence": configuracion.obtener("third_stage_min_evidence") || "0.9",
            "third_stage_min_gap": configuracion.obtener("third_stage_min_gap") || "0.14",
            "enable_ia_discography": configuracion.obtener("enable_ia_discography") || "1",
            "discography_ia_min_confidence": configuracion.obtener("discography_ia_min_confidence") || "0.9",
            "enable_overrides": configuracion.obtener("enable_overrides") || "1",
            "manifest_schema_version": configuracion.obtener("manifest_schema_version") || "1",
            "nb_sound_progress_mode": configuracion.obtener("nb_sound_progress_mode") || "auto",
            "nb_sound_progress_interval_sec": configuracion.obtener("nb_sound_progress_interval_sec") || "2.0",
            "sidecar_future_timeout_seg": configuracion.obtener("sidecar_future_timeout_seg") || "90.0",
            "sidecar_wait_heartbeat_seg": configuracion.obtener("sidecar_wait_heartbeat_seg") || "2.0",
            "enable_audio_features": configuracion.obtener("enable_audio_features") || "1",
            "audio_features_mode": configuracion.obtener("audio_features_mode") || "light",
            "audio_features_analyze_on_import": configuracion.obtener("audio_features_analyze_on_import") || "1",
            "audio_features_background": configuracion.obtener("audio_features_background") || "1",
            "audio_features_max_workers": configuracion.obtener("audio_features_max_workers") || "1",
            "audio_features_analyze_full_track": configuracion.obtener("audio_features_analyze_full_track") || "0",
            "audio_features_sample_strategy": configuracion.obtener("audio_features_sample_strategy") || "smart_segments",
            "audio_features_segment_seconds": configuracion.obtener("audio_features_segment_seconds") || "90",
            "audio_features_reanalyze_on_version_change": configuracion.obtener("audio_features_reanalyze_on_version_change") || "1",
            "audio_features_fail_silently": configuracion.obtener("audio_features_fail_silently") || "1",
            "enable_audio_intelligence_deep": configuracion.obtener("enable_audio_intelligence_deep") || "0",
            "audio_intelligence_backend": configuracion.obtener("audio_intelligence_backend") || "none",
            "enable_audio_mood_models": configuracion.obtener("enable_audio_mood_models") || "0",
            "enable_audio_embeddings": configuracion.obtener("enable_audio_embeddings") || "0",
            "enable_audio_tagging_models": configuracion.obtener("enable_audio_tagging_models") || "0",
            "audio_intelligence_analyze_on_import": configuracion.obtener("audio_intelligence_analyze_on_import") || "0",
            "audio_intelligence_analyze_after_import_background": configuracion.obtener("audio_intelligence_analyze_after_import_background") || "1",
            "audio_intelligence_resume_pending_on_startup": configuracion.obtener("audio_intelligence_resume_pending_on_startup") || "1",
            "audio_intelligence_background_autostart": configuracion.obtener("audio_intelligence_background_autostart") || "1",
            "audio_intelligence_background": configuracion.obtener("audio_intelligence_background") || "1",
            "audio_intelligence_max_workers": configuracion.obtener("audio_intelligence_max_workers") || "1",
            "audio_intelligence_background_batch_size": configuracion.obtener("audio_intelligence_background_batch_size") || "1",
            "audio_intelligence_background_idle_delay_sec": configuracion.obtener("audio_intelligence_background_idle_delay_sec") || "2",
            "audio_intelligence_background_max_runtime_min": configuracion.obtener("audio_intelligence_background_max_runtime_min") || "0",
            "audio_intelligence_model_dir": configuracion.obtener("audio_intelligence_model_dir") || "",
            "audio_intelligence_allow_model_downloads": configuracion.obtener("audio_intelligence_allow_model_downloads") || "0",
            "audio_intelligence_sample_strategy": configuracion.obtener("audio_intelligence_sample_strategy") || "smart_segments",
            "audio_intelligence_segment_seconds": configuracion.obtener("audio_intelligence_segment_seconds") || "120",
            "audio_intelligence_reanalyze_on_model_change": configuracion.obtener("audio_intelligence_reanalyze_on_model_change") || "1",
            "audio_intelligence_retry_failed": configuracion.obtener("audio_intelligence_retry_failed") || "0",
            "audio_intelligence_max_attempts": configuracion.obtener("audio_intelligence_max_attempts") || "1",
            "audio_intelligence_cancel_discard_outputs": configuracion.obtener("audio_intelligence_cancel_discard_outputs") || "0",
            "audio_intelligence_fail_silently": configuracion.obtener("audio_intelligence_fail_silently") || "1",
            "enable_music_discovery": configuracion.obtener("enable_music_discovery") || "1",
            "music_discovery_use_audio_features": configuracion.obtener("music_discovery_use_audio_features") || "1",
            "music_discovery_use_deep_features": configuracion.obtener("music_discovery_use_deep_features") || "1",
            "music_discovery_min_confidence": configuracion.obtener("music_discovery_min_confidence") || "0.35",
            "music_discovery_default_limit": configuracion.obtener("music_discovery_default_limit") || "25",
            "music_discovery_explain_results": configuracion.obtener("music_discovery_explain_results") || "1"
        }
        const accept = parseFloat(configuracion.obtener("score_accept") || "0.82")
        const review = parseFloat(configuracion.obtener("score_review") || "0.55")
        let precisionMode = "equilibrado"
        if (accept >= 0.86 && review >= 0.60) {
            precisionMode = "conservador"
        } else if (accept <= 0.78 && review <= 0.50) {
            precisionMode = "flexible"
        }
        basicaDraft = Object.assign({}, basicaDraft, {"precision_mode": precisionMode})
        // Forzar re-evaluación de todos los bindings dependientes de los drafts
        _basicaRev++
        _avanzadaRev++
        _personalRev++
        _draftsInicializados = true
        actualizarValidacionRutas()
    }

    function actualizarValidacionRutas() {
        if (!_draftsInicializados) return
        const resultado = configuracion.validar_rutas_basica(basicaDraft)
        rutasErrores = resultado.erroresPorClave || {}
        _basicaRev++
    }

    function basicaCompleta() {
        for (let i = 0; i < basicaKeys.length; i++) {
            const clave = basicaKeys[i]
            if (!basicaDraft[clave] || String(basicaDraft[clave]).trim() === "") {
                return false
            }
        }
        return true
    }

    function esNumeroValido(val, min, max) {
        const n = parseFloat(val)
        if (isNaN(n)) return false
        if (min !== undefined && n < min) return false
        if (max !== undefined && n > max) return false
        return true
    }

    function esEnteroValido(val, min) {
        const n = parseInt(val, 10)
        if (isNaN(n) || String(n) !== String(val).trim()) return false
        if (min !== undefined && n < min) return false
        return true
    }

    function avanzadaValida() {
        const d = avanzadaDraft
        if (!esNumeroValido(d["ia_tiebreak_min_gap"], 0, 1)) return false
        if (!esEnteroValido(d["ia_max_tokens"], 1)) return false
        if (!esNumeroValido(d["ia_timeout_seg"], 1)) return false
        if (!esNumeroValido(d["shazam_timeout_seg"], 1)) return false
        if (!esEnteroValido(d["shazam_min_duracion_seg"], 1)) return false
        if (!esEnteroValido(d["init_component_max_retries"], 0)) return false
        if (!esNumeroValido(d["init_component_retry_backoff_seg"], 0.1)) return false
        if (!esNumeroValido(d["duplicate_better_min_delta"], 0, 1)) return false
        if (!esEnteroValido(d["assets_max_retries"], 0)) return false
        if (!esNumeroValido(d["assets_timeout_seg"], 1)) return false
        if (!esNumeroValido(d["assets_cache_ttl_seg"], 1)) return false
        if (!esNumeroValido(d["assets_negative_cache_ttl_seg"], 1)) return false
        if (!esEnteroValido(d["assets_min_resolution"], 1)) return false
        if (!esEnteroValido(d["assets_hd_max_image_bytes"], 1)) return false
        if (!esNumeroValido(d["lyrics_timeout_seg"], 2)) return false
        if (!esEnteroValido(d["lyrics_max_retries"], 0)) return false
        if (!esNumeroValido(d["lyrics_retry_backoff_seg"], 0.1)) return false
        if (!esEnteroValido(d["lyrics_suggest_limit"], 0)) return false
        if (!esNumeroValido(d["second_stage_min_evidence"], 0, 1)) return false
        if (!esNumeroValido(d["second_stage_min_gap"], 0, 1)) return false
        if (!esEnteroValido(d["second_stage_max_candidates"], 1)) return false
        if (!esNumeroValido(d["third_stage_min_evidence"], 0, 1)) return false
        if (!esNumeroValido(d["third_stage_min_gap"], 0, 1)) return false
        if (!esNumeroValido(d["discography_ia_min_confidence"], 0, 1)) return false
        if (!esEnteroValido(d["manifest_schema_version"], 1)) return false
        if (["auto", "tty", "log", "quiet"].indexOf(String(d["nb_sound_progress_mode"] || "")) < 0) return false
        if (!esNumeroValido(d["nb_sound_progress_interval_sec"], 0.25, 60)) return false
        if (!esNumeroValido(d["sidecar_future_timeout_seg"], 5, 3600)) return false
        if (!esNumeroValido(d["sidecar_wait_heartbeat_seg"], 0.25, 60)) return false
        if (!esEnteroValido(d["audio_features_max_workers"], 1)) return false
        if (!esEnteroValido(d["audio_features_segment_seconds"], 1)) return false
        if (!esEnteroValido(d["audio_intelligence_max_workers"], 1)) return false
        if (!esEnteroValido(d["audio_intelligence_background_batch_size"], 1)) return false
        if (!esNumeroValido(d["audio_intelligence_background_idle_delay_sec"], 0, 3600)) return false
        if (!esEnteroValido(d["audio_intelligence_background_max_runtime_min"], 0)) return false
        if (!esEnteroValido(d["audio_intelligence_segment_seconds"], 1)) return false
        if (!esEnteroValido(d["audio_intelligence_max_attempts"], 1)) return false
        if (!esNumeroValido(d["music_discovery_min_confidence"], 0, 1)) return false
        if (!esEnteroValido(d["music_discovery_default_limit"], 1)) return false
        return true
    }

    function iaSeNormalizara() {
        const d = avanzadaDraft
        const usaIa = d["enable_ia_tiebreak"] === "1" || d["enable_ia_discography"] === "1"
        if (!usaIa) return false
        if (d["ia_proveedor"] === "OpenAI" && String(d["openai_key"] || "").trim() !== "") return false
        if (d["ia_proveedor"] === "Anthropic" && String(d["anthropic_key"] || "").trim() !== "") return false
        return true
    }

    function saveBasica() {
        const resultado = configuracion.guardar_basica(basicaDraft)
        if (resultado.ok) {
            initDrafts()
            mostrarPopupEstado("Configuración básica guardada", "Se guardaron rutas, AcoustID, Shazam y modo de precisión.", false)
        } else {
            mostrarPopupEstado("No se pudo guardar", resultado.mensaje || "Revisa las rutas obligatorias e inténtalo de nuevo.", true)
        }
    }

    function saveAvanzada() {
        const resultado = configuracion.guardar_avanzada(avanzadaDraft)
        if (resultado.ok) initDrafts()
        const mensajeOk = resultado.ia_normalizada
            ? "Los parámetros técnicos se guardaron. La IA quedó desactivada porque faltaba proveedor o API key válida."
            : "Los parámetros técnicos se guardaron correctamente."
        mostrarPopupEstado(
            resultado.ok ? "Configuración avanzada guardada" : "No se pudo guardar",
            resultado.ok
            ? mensajeOk
            : (resultado.mensaje || "Revisa los valores e inténtalo de nuevo."),
            !resultado.ok
        )
    }

    function mostrarPopupEstado(titulo, mensaje, esError) {
        popupBasicaInfo.titulo = titulo
        popupBasicaInfo.mensaje = mensaje
        popupBasicaInfo.esError = esError
        popupBasicaInfo.open()
    }

    function defaultsBasica() {
        basicaDraft = configuracion.valores_predeterminados_modulo("basica")
        _basicaRev++
        actualizarValidacionRutas()
        mostrarPopupEstado(
            "Valores predeterminados cargados",
            "Se cargaron en el formulario. Pulsa Guardar configuración para persistirlos; si sales sin guardar, se descartan.",
            false
        )
    }
    function defaultsAvanzada() {
        avanzadaDraft = configuracion.valores_predeterminados_modulo("avanzada")
        _avanzadaRev++
        mostrarPopupEstado(
            "Valores predeterminados cargados",
            "Se cargaron los valores técnicos en el formulario. Pulsa Guardar configuración para persistirlos.",
            false
        )
    }
    onVisibleChanged: {
        sincronizarModoUi()
        if (visible || _draftsInicializados) {
            initDrafts()
        }
    }

    onEsProChanged: {
        if (!esPro && seccion_activa === "avanzada") {
            seccion_activa = "basica"
        }
    }

    Component.onCompleted: {
        sincronizarModoUi()
        fontOptions = construirFontOptions()
        initDrafts()
    }

    Connections {
        target: configuracion
        function onConfiguracionCambiada() {
            sincronizarModoUi()
            fuenteUi = shell ? shell.fuente_ui : (configuracion.obtener("ui_font_family") || "Inter")
            fontOptions = construirFontOptions()
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // CONTENIDO PRINCIPAL
    // ─────────────────────────────────────────────────────────────────────────
    ScrollView {
        id: configScroll
        objectName: "config_scroll"
        anchors.fill: parent
        contentWidth: availableWidth
        contentHeight: configContent.implicitHeight
        clip: true
        ScrollBar.vertical: AppScrollBar {
            parent: configScroll
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            z: 20
            tema: raiz.tema
            policy: configScroll.contentHeight > configScroll.height + 2 ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
        }

        ColumnLayout {
            id: configContent
            width: raiz.width
            spacing: 0

            // Título de página
            Item {
                Layout.fillWidth: true
                height: 88
                AppText {
                    anchors { left: parent.left; leftMargin: horizontalPadding; bottom: parent.bottom; bottomMargin: UiTokens.spacing16 }
                    text: "Configuración"
                    font.pixelSize: 28
                    font.weight: Font.DemiBold
                    color: tema.texto
                }
            }

            // Barra de pestañas
            Rectangle {
                Layout.leftMargin: horizontalPadding
                Layout.rightMargin: horizontalPadding
                Layout.bottomMargin: UiTokens.spacing24
                Layout.maximumWidth: contentMaxWidth
                Layout.alignment: Qt.AlignHCenter
                Layout.fillWidth: true
                implicitHeight: 52
                radius: UiTokens.radiusLg
                color: tema.superficie
                border.color: tema.borde
                border.width: 1

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: UiTokens.spacing6
                    spacing: UiTokens.spacing6
                    Tab { objectName: "tab_config_basica"; Layout.fillWidth: true; texto: "Básica"; activo: seccion_activa === "basica"; onClicked: seccion_activa = "basica" }
                    Tab { objectName: "tab_config_avanzada"; visible: esPro; Layout.fillWidth: visible; texto: "Avanzada"; activo: seccion_activa === "avanzada"; onClicked: seccion_activa = "avanzada" }
                    Tab { objectName: "tab_config_personalizacion"; Layout.fillWidth: true; texto: "Personalización"; activo: seccion_activa === "personalizacion"; onClicked: seccion_activa = "personalizacion" }
                }
            }

            // ─────────────────────────────────────────────────────────────────
            // SECCIÓN BÁSICA
            // ─────────────────────────────────────────────────────────────────
            ColumnLayout {
                visible: seccion_activa === "basica"
                Layout.fillWidth: true
                Layout.leftMargin: horizontalPadding
                Layout.rightMargin: horizontalPadding
                Layout.maximumWidth: contentMaxWidth
                Layout.alignment: Qt.AlignHCenter
                spacing: sectionSpacing

                // Header de la sección básica
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: headerBasicaLayout.implicitHeight + 32
                    radius: 16
                    color: tema.superficie
                    border.color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.18)
                    border.width: 1

                    RowLayout {
                        id: headerBasicaLayout
                        anchors.fill: parent
                        anchors.margins: UiTokens.spacing16
                        spacing: UiTokens.spacing14

                        Rectangle {
                            width: 48; height: 48; radius: 12
                            color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.12)
                            border.color: tema.acento; border.width: 1
                            Image {
                                id: iconBasicaHeader
                                anchors { centerIn: parent; fill: parent; margins: UiTokens.spacing10 }
                                source: "../assets/icons/folder.svg"
                                fillMode: Image.PreserveAspectFit
                                smooth: true; visible: false
                            }
                            ColorOverlay { anchors.fill: iconBasicaHeader; source: iconBasicaHeader; color: tema.acento; visible: GraphicsInfo.api !== GraphicsInfo.Software }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: UiTokens.spacing4
                            AppText { text: "Configuración básica de rutas"; font.pixelSize: UiTokens.fontSize2xl; font.weight: Font.DemiBold; color: tema.texto }
                            AppText {
                                text: "Los cambios de esta sección solo se aplican al guardar. Si sales sin guardar, se descartan y vuelve lo persistido."
                                font.pixelSize: UiTokens.fontSizeMd; color: tema.textoMuted; wrapMode: Text.WordWrap; Layout.fillWidth: true
                            }
                        }

                        Rectangle {
                            Layout.alignment: Qt.AlignTop
                            radius: UiTokens.radiusLg
                            color: Qt.rgba(
                                (basicaCompleta() ? tema.exito : tema.acento).r,
                                (basicaCompleta() ? tema.exito : tema.acento).g,
                                (basicaCompleta() ? tema.exito : tema.acento).b,
                                0.14
                            )
                            border.color: basicaCompleta() ? tema.exito : tema.acento
                            border.width: 1
                            implicitWidth: progresoBasica.implicitWidth + 16
                            implicitHeight: progresoBasica.implicitHeight + 10
                            AppText {
                                id: progresoBasica
                                anchors.centerIn: parent
                                text: basicaCompleta() ? "Configuración completa" : "Faltan rutas obligatorias"
                                font.pixelSize: UiTokens.fontSizeSm; font.weight: Font.DemiBold
                                color: basicaCompleta() ? tema.exito : tema.acento
                            }
                        }
                    }
                }

                SectionHeading {
                    titulo: "Carpetas principales"
                    descripcion: "Rutas críticas para el flujo principal de importación y organización."
                }
                GridLayout {
                    id: gridRutasPrincipales
                    Layout.fillWidth: true
                    columnSpacing: 14; rowSpacing: 14
                    columns: width >= 980 ? 2 : 1
                    RutaCard { etiqueta: "Carpeta de entrada"; clave: "dir_entrada"; descripcion: "Archivos por procesar. Ejemplo: /home/usuario/Música/entrada/"; draftObj: basicaDraft; columnas: gridRutasPrincipales.columns; obligatoria: true; erroresObj: rutasErrores; onChanged: function(clave, valor) { setBasicaValue(clave, valor); actualizarValidacionRutas() } }
                    RutaCard { etiqueta: "Carpeta de biblioteca"; clave: "dir_biblioteca"; descripcion: "Destino final por artista/álbum. Ejemplo: /home/usuario/Música/biblioteca/"; draftObj: basicaDraft; columnas: gridRutasPrincipales.columns; obligatoria: true; erroresObj: rutasErrores; onChanged: function(clave, valor) { setBasicaValue(clave, valor); actualizarValidacionRutas() } }
                    RutaCard { etiqueta: "Carpeta de cuarentena"; clave: "dir_cuarentena"; descripcion: "Casos no recuperables automáticamente. Ejemplo: /home/usuario/Música/cuarentena/"; draftObj: basicaDraft; columnas: gridRutasPrincipales.columns; obligatoria: true; erroresObj: rutasErrores; onChanged: function(clave, valor) { setBasicaValue(clave, valor); actualizarValidacionRutas() } }
                    RutaCard { etiqueta: "Carpeta de revisión"; clave: "dir_revision"; descripcion: "Casos que requieren decisión manual. Ejemplo: /home/usuario/Música/revision/"; draftObj: basicaDraft; columnas: gridRutasPrincipales.columns; obligatoria: true; erroresObj: rutasErrores; onChanged: function(clave, valor) { setBasicaValue(clave, valor); actualizarValidacionRutas() } }
                    RutaCard { etiqueta: "Carpeta de logs"; clave: "dir_logs"; descripcion: "Historial técnico y auditoría de corridas. Ejemplo: /home/usuario/Música/logs/"; draftObj: basicaDraft; columnas: gridRutasPrincipales.columns; obligatoria: true; erroresObj: rutasErrores; onChanged: function(clave, valor) { setBasicaValue(clave, valor); actualizarValidacionRutas() } }
                    RutaCard { etiqueta: "Carpeta de procesados"; clave: "dir_procesados"; descripcion: "Originales ya importados para evitar reingreso. Ejemplo: /home/usuario/Música/procesados/"; draftObj: basicaDraft; columnas: gridRutasPrincipales.columns; obligatoria: true; erroresObj: rutasErrores; onChanged: function(clave, valor) { setBasicaValue(clave, valor); actualizarValidacionRutas() } }
                }

                SectionHeading {
                    titulo: "Carpetas opcionales (con fallback automático)"
                    descripcion: "Puedes dejarlas vacías para usar rutas automáticas recomendadas por el sistema."
                }
                GridLayout {
                    id: gridRutasOpcionales
                    Layout.fillWidth: true
                    columnSpacing: 14; rowSpacing: 14
                    columns: width >= 980 ? 2 : 1
                    RutaCard { etiqueta: "Assets"; clave: "dir_assets"; descripcion: "Portadas e imágenes de artista."; ejemplo: configuracion.fallback_ruta("dir_assets"); draftObj: basicaDraft; columnas: gridRutasOpcionales.columns; obligatoria: false; erroresObj: rutasErrores; onChanged: function(clave, valor) { setBasicaValue(clave, valor); actualizarValidacionRutas() } }
                    RutaCard { etiqueta: "Caché"; clave: "dir_cache"; descripcion: "Resultados temporales de proveedores."; ejemplo: configuracion.fallback_ruta("dir_cache"); draftObj: basicaDraft; columnas: gridRutasOpcionales.columns; obligatoria: false; erroresObj: rutasErrores; onChanged: function(clave, valor) { setBasicaValue(clave, valor); actualizarValidacionRutas() } }
                    RutaCard { etiqueta: "Temporales"; clave: "dir_temp"; descripcion: "Archivos temporales de trabajo."; ejemplo: configuracion.fallback_ruta("dir_temp"); draftObj: basicaDraft; columnas: gridRutasOpcionales.columns; obligatoria: false; erroresObj: rutasErrores; onChanged: function(clave, valor) { setBasicaValue(clave, valor); actualizarValidacionRutas() } }
                    RutaCard { etiqueta: "Manifiestos"; clave: "dir_manifests"; descripcion: "Índices canónicos de track/álbum/artista."; ejemplo: configuracion.fallback_ruta("dir_manifests"); draftObj: basicaDraft; columnas: gridRutasOpcionales.columns; obligatoria: false; erroresObj: rutasErrores; onChanged: function(clave, valor) { setBasicaValue(clave, valor); actualizarValidacionRutas() } }
                }

                GrupoConfig {
                    titulo: "Identificación y resolución"
                    descripcion: "Elige las fuentes principales. La IA se configura solo en Avanzada para no mezclar lo básico con proveedores de pago."
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: UiTokens.spacing12
                        ToggleCampo {
                            objectName: "config_acoustid_toggle"
                            label: "Usar AcoustID (fingerprint de audio)"
                            checkedValue: { _basicaRev; return basicaDraft["enable_acoustid"] === "1" }
                            onChangedValue: function(v) { setBasicaValue("enable_acoustid", v ? "1" : "0") }
                        }
                        CampoTextoPassword {
                            objectName: "config_acoustid_key"
                            visible: { _basicaRev; return basicaDraft["enable_acoustid"] === "1" }
                            etiqueta: "API key de AcoustID"
                            descripcion: "Clave usada para consultar huellas acústicas. Si dejas el campo vacío, AcoustID no podrá resolver contra su servicio externo."
                            clave: "acoustid_key"; draftObj: basicaDraft
                            scope: "basica"
                            habilitado: { _basicaRev; return basicaDraft["enable_acoustid"] === "1" }
                        }
                        ToggleCampo {
                            objectName: "config_shazam_toggle"
                            label: "Usar Shazam (reconocimiento de audio)"
                            checkedValue: { _basicaRev; return basicaDraft["enable_shazam"] === "1" }
                            onChangedValue: function(v) { setBasicaValue("enable_shazam", v ? "1" : "0") }
                        }
                    }
                }

                GrupoConfig {
                    titulo: "Modo general de precisión"
                    descripcion: "Estrategia global de aceptación sin necesidad de tocar parámetros técnicos individuales."
                    ColumnLayout {
                        spacing: UiTokens.spacing10
                        Flow {
                            Layout.fillWidth: true
                            spacing: UiTokens.spacing12
                            PillOption {
                                objectName: "config_precision_conservador"
                                texto: "Conservador"
                                activo: { _basicaRev; return basicaDraft["precision_mode"] === "conservador" }
                                onClicked: setBasicaValue("precision_mode", "conservador")
                            }
                            PillOption {
                                objectName: "config_precision_equilibrado"
                                texto: "Equilibrado"
                                activo: { _basicaRev; return basicaDraft["precision_mode"] === "equilibrado" }
                                onClicked: setBasicaValue("precision_mode", "equilibrado")
                            }
                            PillOption {
                                objectName: "config_precision_flexible"
                                texto: "Flexible"
                                activo: { _basicaRev; return basicaDraft["precision_mode"] === "flexible" }
                                onClicked: setBasicaValue("precision_mode", "flexible")
                            }
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            radius: UiTokens.radiusMd
                            color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.06)
                            border.color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.18)
                            border.width: 1
                            implicitHeight: precisionDesc.implicitHeight + 20
                            AppText {
                                id: precisionDesc
                                anchors { left: parent.left; right: parent.right; top: parent.top; margins: UiTokens.spacing12 }
                                text: {
                                    _basicaRev
                                    if (basicaDraft["precision_mode"] === "conservador")
                                        return "Conservador: acepta menos automáticamente y manda más casos a revisión manual. Recomendado cuando la colección tiene muchos duplicados o ediciones especiales."
                                    if (basicaDraft["precision_mode"] === "flexible")
                                        return "Flexible: acepta más automáticamente y reduce derivaciones a revisión. Útil para colecciones grandes con archivos bien etiquetados."
                                    return "Equilibrado: modo recomendado por defecto. Balance entre precisión y volumen de procesamiento."
                                }
                                color: tema.textoSec; font.pixelSize: UiTokens.fontSizeMd; wrapMode: Text.WordWrap
                            }
                        }
                    }
                }

                FooterModulo {
                    objectPrefix: "basica"
                    Layout.alignment: Qt.AlignHCenter
                    deshabilitarGuardar: { _basicaRev; return !basicaCompleta() || Object.keys(rutasErrores || {}).length > 0 }
                    onGuardar: saveBasica()
                    onPredeterminados: defaultsBasica()
                }
            }

            // ─────────────────────────────────────────────────────────────────
            // SECCIÓN AVANZADA
            // ─────────────────────────────────────────────────────────────────
            ColumnLayout {
                visible: esPro && seccion_activa === "avanzada"
                Layout.fillWidth: true
                Layout.leftMargin: horizontalPadding
                Layout.rightMargin: horizontalPadding
                Layout.maximumWidth: contentMaxWidth
                Layout.alignment: Qt.AlignHCenter
                spacing: sectionSpacing

                // Header avanzada (mismo estilo que básica)
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: headerAvanzadaLayout.implicitHeight + 32
                    radius: 16
                    color: tema.superficie
                    border.color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.16)
                    border.width: 1

                    RowLayout {
                        id: headerAvanzadaLayout
                        anchors.fill: parent
                        anchors.margins: UiTokens.spacing16
                        spacing: UiTokens.spacing14

                        Rectangle {
                            width: 48; height: 48; radius: 12
                            color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.12)
                            border.color: tema.acento; border.width: 1
                            Image {
                                id: iconAvanzadaHeader
                                anchors { centerIn: parent; fill: parent; margins: UiTokens.spacing10 }
                                source: "../assets/icons/settings.svg"
                                fillMode: Image.PreserveAspectFit
                                smooth: true; visible: false
                            }
                            ColorOverlay { anchors.fill: iconAvanzadaHeader; source: iconAvanzadaHeader; color: tema.acento; visible: GraphicsInfo.api !== GraphicsInfo.Software }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: UiTokens.spacing4
                            AppText { text: "Configuración avanzada"; font.pixelSize: UiTokens.fontSize2xl; font.weight: Font.DemiBold; color: tema.texto }
                            AppText {
                                text: "Modo Pro. Los cambios técnicos solo se aplican al guardar; si sales sin guardar, se descartan."
                                font.pixelSize: UiTokens.fontSizeMd; color: tema.textoMuted; wrapMode: Text.WordWrap; Layout.fillWidth: true
                            }
                        }

                        Rectangle {
                            Layout.alignment: Qt.AlignTop
                            radius: UiTokens.radiusLg
                            color: Qt.rgba(
                                (avanzadaValida() && !iaSeNormalizara() ? tema.exito : tema.advertencia).r,
                                (avanzadaValida() && !iaSeNormalizara() ? tema.exito : tema.advertencia).g,
                                (avanzadaValida() && !iaSeNormalizara() ? tema.exito : tema.advertencia).b,
                                0.14
                            )
                            border.color: avanzadaValida() && !iaSeNormalizara() ? tema.exito : tema.advertencia
                            border.width: 1
                            implicitWidth: estadoAvanzada.implicitWidth + 16
                            implicitHeight: estadoAvanzada.implicitHeight + 10
                            AppText {
                                id: estadoAvanzada
                                anchors.centerIn: parent
                                text: {
                                    _avanzadaRev
                                    if (!avanzadaValida()) return "Hay valores inválidos"
                                    if (iaSeNormalizara()) return "IA se desactivará al guardar"
                                    return "Valores válidos"
                                }
                                font.pixelSize: UiTokens.fontSizeSm; font.weight: Font.DemiBold
                                color: avanzadaValida() && !iaSeNormalizara() ? tema.exito : tema.advertencia
                            }
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 14

                    // ── INTEGRACIONES ─────────────────────────────────────
                    GrupoConfig {
                        titulo: "Identificación técnica"
                        descripcion: "Parámetros finos de fuentes ya activadas en Configuración básica y desempate por IA."
                        Layout.fillWidth: true

                        ColumnLayout {
                            spacing: UiTokens.spacing14

                            GrupoConfig {
                                titulo: "Shazam"
                                descripcion: "Ajusta límites de red para Shazam. La activación principal vive en Básica."
                                ColumnLayout {
                                    spacing: UiTokens.spacing10
                                    GridLayout {
                                        Layout.fillWidth: true
                                        columns: mediumWidth ? 2 : 1
                                        columnSpacing: 12; rowSpacing: 10
                                        CampoTexto {
                                            etiqueta: "Timeout (segundos)"
                                            descripcion: "Tiempo máximo de espera por respuesta."
                                            clave: "shazam_timeout_seg"; draftObj: avanzadaDraft
                                            validador: "positivo"
                                            habilitado: { _avanzadaRev; return configuracion.obtener("enable_shazam") === "1" }
                                        }
                                        CampoTexto {
                                            etiqueta: "Duración mínima de audio (segundos)"
                                            descripcion: "Archivos más cortos se omiten en Shazam."
                                            clave: "shazam_min_duracion_seg"; draftObj: avanzadaDraft
                                            validador: "entero_positivo"
                                            habilitado: { _avanzadaRev; return configuracion.obtener("enable_shazam") === "1" }
                                        }
                                    }
                                }
                            }

                            GrupoConfig {
                                titulo: "Desempate por IA"
                                descripcion: "Se activa solo cuando dos candidatos tienen puntajes muy próximos. Requiere API key válida."
                                ColumnLayout {
                                    spacing: UiTokens.spacing10
                                    ToggleCampo {
                                        objectName: "config_ia_tiebreak_toggle"
                                        label: "Habilitar desempate por IA"
                                        checkedValue: { _avanzadaRev; return avanzadaDraft["enable_ia_tiebreak"] === "1" }
                                        onChangedValue: function(v) {
                                            if (v) {
                                                setAvanzadaValue("enable_ia_tiebreak", "1")
                                            } else {
                                                setAvanzadaValues({
                                                    "enable_ia_tiebreak": "0",
                                                    "ia_proveedor": "No"
                                                })
                                            }
                                        }
                                    }
                                    ColumnLayout {
                                        visible: { _avanzadaRev; return avanzadaDraft["enable_ia_tiebreak"] === "1" }
                                        enabled: avanzadaDraft["enable_ia_tiebreak"] === "1"
                                        Layout.fillWidth: true
                                        spacing: UiTokens.spacing8
                                        AppText { text: "Proveedor de Inteligencia Artificial"; color: tema.texto; font.pixelSize: UiTokens.fontSizeBase }
                                        Flow {
                                            Layout.fillWidth: true
                                            spacing: UiTokens.spacing10
                                            PillOption {
                                                objectName: "config_ia_proveedor_no"
                                                texto: "Ninguno"
                                                activo: { _avanzadaRev; return avanzadaDraft["ia_proveedor"] === "No" }
                                                onClicked: setAvanzadaValue("ia_proveedor", "No")
                                            }
                                            PillOption {
                                                objectName: "config_ia_proveedor_openai"
                                                texto: "OpenAI"
                                                activo: { _avanzadaRev; return avanzadaDraft["ia_proveedor"] === "OpenAI" }
                                                onClicked: setAvanzadaValue("ia_proveedor", "OpenAI")
                                            }
                                            PillOption {
                                                objectName: "config_ia_proveedor_anthropic"
                                                texto: "Anthropic"
                                                activo: { _avanzadaRev; return avanzadaDraft["ia_proveedor"] === "Anthropic" }
                                                onClicked: setAvanzadaValue("ia_proveedor", "Anthropic")
                                            }
                                        }
                                    }
                                    CampoTextoPassword {
                                        objectName: "config_openai_key"
                                        visible: { _avanzadaRev; return avanzadaDraft["enable_ia_tiebreak"] === "1" && avanzadaDraft["ia_proveedor"] === "OpenAI" }
                                        etiqueta: "API key OpenAI"
                                        descripcion: "Requerida si el proveedor es OpenAI."
                                        clave: "openai_key"; draftObj: avanzadaDraft
                                        habilitado: { _avanzadaRev; return avanzadaDraft["enable_ia_tiebreak"] === "1" && avanzadaDraft["ia_proveedor"] === "OpenAI" }
                                    }
                                    CampoTextoPassword {
                                        objectName: "config_anthropic_key"
                                        visible: { _avanzadaRev; return avanzadaDraft["enable_ia_tiebreak"] === "1" && avanzadaDraft["ia_proveedor"] === "Anthropic" }
                                        etiqueta: "API key Anthropic"
                                        descripcion: "Requerida si el proveedor es Anthropic."
                                        clave: "anthropic_key"; draftObj: avanzadaDraft
                                        habilitado: { _avanzadaRev; return avanzadaDraft["enable_ia_tiebreak"] === "1" && avanzadaDraft["ia_proveedor"] === "Anthropic" }
                                    }
                                    GridLayout {
                                        Layout.fillWidth: true
                                        columns: mediumWidth ? 3 : 1
                                        columnSpacing: 12; rowSpacing: 10
                                        CampoTexto {
                                            objectName: "config_ia_tiebreak_min_gap"
                                            etiqueta: "Gap mínimo (0.0 – 1.0)"
                                            descripcion: "Diferencia mínima entre candidatos para activar IA."
                                            clave: "ia_tiebreak_min_gap"; draftObj: avanzadaDraft
                                            validador: "score"
                                            habilitado: { _avanzadaRev; return avanzadaDraft["enable_ia_tiebreak"] === "1" }
                                        }
                                        CampoTexto {
                                            objectName: "config_ia_max_tokens"
                                            etiqueta: "Máximo de tokens"
                                            descripcion: "Límite de tokens por llamada a la IA."
                                            clave: "ia_max_tokens"; draftObj: avanzadaDraft
                                            validador: "entero_positivo"
                                            habilitado: { _avanzadaRev; return avanzadaDraft["enable_ia_tiebreak"] === "1" }
                                        }
                                        CampoTexto {
                                            objectName: "config_ia_timeout_seg"
                                            etiqueta: "Timeout IA (segundos)"
                                            descripcion: "Tiempo máximo de espera de respuesta de la IA."
                                            clave: "ia_timeout_seg"; draftObj: avanzadaDraft
                                            validador: "positivo"
                                            habilitado: { _avanzadaRev; return avanzadaDraft["enable_ia_tiebreak"] === "1" }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // ── PIPELINE ──────────────────────────────────────────
                    GrupoConfig {
                        titulo: "Comportamiento del pipeline"
                        descripcion: "Controla cómo se procesan los archivos en cada corrida."
                        Layout.fillWidth: true

                        ColumnLayout {
                            spacing: UiTokens.spacing10
                            ToggleCampo {
                                label: "Omitir archivos ya procesados en corridas anteriores"
                                checkedValue: { _avanzadaRev; return avanzadaDraft["skip_already_processed"] === "1" }
                                onChangedValue: function(v) { setAvanzadaValue("skip_already_processed", v ? "1" : "0") }
                            }
                            GridLayout {
                                visible: { _avanzadaRev; return avanzadaDraft["enable_second_stage_resolution"] === "1" }
                                Layout.fillWidth: true
                                columns: mediumWidth ? 2 : 1
                                columnSpacing: 12; rowSpacing: 10
                                CampoTexto {
                                    etiqueta: "Reintentos al inicializar componentes"
                                    descripcion: "Intentos adicionales para preparar servicios internos antes de fallar."
                                    clave: "init_component_max_retries"; draftObj: avanzadaDraft
                                    validador: "entero_no_negativo"
                                }
                                CampoTexto {
                                    etiqueta: "Backoff de inicialización (seg)"
                                    descripcion: "Espera base entre reintentos de inicialización."
                                    clave: "init_component_retry_backoff_seg"; draftObj: avanzadaDraft
                                    validador: "positivo"
                                }
                            }
                        }
                    }

                    // ── DUPLICADOS ────────────────────────────────────────
                    GrupoConfig {
                        titulo: "Gestión de duplicados"
                        descripcion: "Cómo detectar y resolver tracks duplicados en la biblioteca."
                        Layout.fillWidth: true

                        ColumnLayout {
                            spacing: UiTokens.spacing10
                            ToggleCampo {
                                label: "Activar detección de duplicados exactos"
                                checkedValue: { _avanzadaRev; return avanzadaDraft["enable_deduplication"] === "1" }
                                onChangedValue: function(v) { setAvanzadaValue("enable_deduplication", v ? "1" : "0") }
                            }
                            ToggleCampo {
                                label: "Activar deduplicación semántica (mismo álbum/artista)"
                                checkedValue: { _avanzadaRev; return avanzadaDraft["enable_semantic_deduplication"] === "1" }
                                habilitado: { _avanzadaRev; return avanzadaDraft["enable_deduplication"] === "1" }
                                onChangedValue: function(v) { setAvanzadaValue("enable_semantic_deduplication", v ? "1" : "0") }
                            }
                            ColumnLayout {
                                visible: { _avanzadaRev; return avanzadaDraft["enable_deduplication"] === "1" }
                                Layout.fillWidth: true
                                spacing: UiTokens.spacing8
                                AppText { text: "Política ante duplicado"; color: tema.texto; font.pixelSize: UiTokens.fontSizeBase }
                                Flow {
                                    Layout.fillWidth: true
                                    spacing: UiTokens.spacing10
                                    PillOption {
                                        objectName: "config_duplicate_policy_replace_if_better"
                                        texto: "Reemplazar si es mejor"
                                        activo: { _avanzadaRev; return avanzadaDraft["duplicate_policy"] === "replace_if_better" }
                                        onClicked: setAvanzadaValue("duplicate_policy", "replace_if_better")
                                    }
                                    PillOption {
                                        objectName: "config_duplicate_policy_prefer_new_if_quality_higher"
                                        texto: "Preferir nuevo si calidad es mayor"
                                        activo: { _avanzadaRev; return avanzadaDraft["duplicate_policy"] === "prefer_new_if_quality_higher" }
                                        onClicked: setAvanzadaValue("duplicate_policy", "prefer_new_if_quality_higher")
                                    }
                                }
                            }
                            CampoTexto {
                                visible: { _avanzadaRev; return avanzadaDraft["enable_deduplication"] === "1" }
                                etiqueta: "Delta mínimo de mejora (0.0 – 1.0)"
                                descripcion: "Diferencia mínima de calidad requerida para reemplazar un duplicado existente."
                                clave: "duplicate_better_min_delta"; draftObj: avanzadaDraft
                                validador: "score"
                            }
                        }
                    }

                    // ── ASSETS MULTIMEDIA ─────────────────────────────────
                    GrupoConfig {
                        titulo: "Assets multimedia (portadas e imágenes)"
                        descripcion: "Descarga automática de portadas de álbumes e imágenes de artistas desde múltiples fuentes."
                        Layout.fillWidth: true

                        ColumnLayout {
                            spacing: UiTokens.spacing10

                            ToggleCampo {
                                label: "Activar pipeline de assets multimedia"
                                checkedValue: { _avanzadaRev; return avanzadaDraft["enable_assets_pipeline"] === "1" }
                                onChangedValue: function(v) { setAvanzadaValue("enable_assets_pipeline", v ? "1" : "0") }
                            }

                            Rectangle {
                                visible: { _avanzadaRev; return avanzadaDraft["enable_assets_pipeline"] === "1" }
                                Layout.fillWidth: true
                                radius: UiTokens.radiusMd
                                color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.04)
                                border.color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.6)
                                border.width: 1
                                implicitHeight: fuentesAssets.implicitHeight + 24
                                opacity: { _avanzadaRev; return avanzadaDraft["enable_assets_pipeline"] === "1" ? 1.0 : 0.4 }
                                Behavior on opacity { NumberAnimation { duration: 180 } }

                                ColumnLayout {
                                    id: fuentesAssets
                                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: UiTokens.spacing12 }
                                    spacing: UiTokens.spacing8

                                    AppText { text: "Fuentes de imágenes"; font.pixelSize: UiTokens.fontSizeMd; font.weight: Font.DemiBold; color: tema.textoSec }

                                    ToggleCampo {
                                        label: "Cover Art Archive (portadas de álbumes)"
                                        checkedValue: { _avanzadaRev; return avanzadaDraft["enable_cover_art_archive"] === "1" }
                                        habilitado: { _avanzadaRev; return avanzadaDraft["enable_assets_pipeline"] === "1" }
                                        onChangedValue: function(v) { setAvanzadaValue("enable_cover_art_archive", v ? "1" : "0") }
                                    }
                                    ToggleCampo {
                                        label: "Fallback de portada via iTunes"
                                        checkedValue: { _avanzadaRev; return avanzadaDraft["enable_itunes_cover_fallback"] === "1" }
                                        habilitado: { _avanzadaRev; return avanzadaDraft["enable_assets_pipeline"] === "1" }
                                        onChangedValue: function(v) { setAvanzadaValue("enable_itunes_cover_fallback", v ? "1" : "0") }
                                    }
                                    ToggleCampo {
                                        label: "TheAudioDB — imágenes de artistas"
                                        checkedValue: { _avanzadaRev; return avanzadaDraft["enable_theaudiodb_artist_images"] === "1" }
                                        habilitado: { _avanzadaRev; return avanzadaDraft["enable_assets_pipeline"] === "1" }
                                        onChangedValue: function(v) { setAvanzadaValue("enable_theaudiodb_artist_images", v ? "1" : "0") }
                                    }
                                    CampoTextoPassword {
                                        etiqueta: "API key TheAudioDB"
                                        descripcion: "Requerida para imágenes de artistas desde TheAudioDB."
                                        clave: "theaudiodb_api_key"; draftObj: avanzadaDraft
                                        habilitado: { _avanzadaRev; return avanzadaDraft["enable_assets_pipeline"] === "1" && avanzadaDraft["enable_theaudiodb_artist_images"] === "1" }
                                    }
                                    ToggleCampo {
                                        label: "Deezer — imágenes de artistas"
                                        checkedValue: { _avanzadaRev; return avanzadaDraft["enable_deezer_artist_images"] === "1" }
                                        habilitado: { _avanzadaRev; return avanzadaDraft["enable_assets_pipeline"] === "1" }
                                        onChangedValue: function(v) { setAvanzadaValue("enable_deezer_artist_images", v ? "1" : "0") }
                                    }
                                    ToggleCampo {
                                        label: "Wikipedia — imágenes de artistas"
                                        checkedValue: { _avanzadaRev; return avanzadaDraft["enable_wikipedia_artist_images"] === "1" }
                                        habilitado: { _avanzadaRev; return avanzadaDraft["enable_assets_pipeline"] === "1" }
                                        onChangedValue: function(v) { setAvanzadaValue("enable_wikipedia_artist_images", v ? "1" : "0") }
                                    }
                                    ToggleCampo {
                                        label: "iTunes — imágenes de artistas"
                                        checkedValue: { _avanzadaRev; return avanzadaDraft["enable_itunes_artist_images"] === "1" }
                                        habilitado: { _avanzadaRev; return avanzadaDraft["enable_assets_pipeline"] === "1" }
                                        onChangedValue: function(v) { setAvanzadaValue("enable_itunes_artist_images", v ? "1" : "0") }
                                    }
                                }
                            }

                            SectionHeading {
                                visible: { _avanzadaRev; return avanzadaDraft["enable_assets_pipeline"] === "1" }
                                titulo: "Parámetros de descarga"
                                descripcion: ""
                            }
                            GridLayout {
                                visible: { _avanzadaRev; return avanzadaDraft["enable_assets_pipeline"] === "1" }
                                Layout.fillWidth: true
                                columns: mediumWidth ? 3 : 1
                                columnSpacing: 12; rowSpacing: 10
                                CampoTexto {
                                    etiqueta: "Timeout (segundos)"
                                    descripcion: "Tiempo máximo por solicitud."
                                    clave: "assets_timeout_seg"; draftObj: avanzadaDraft
                                    validador: "positivo"
                                    habilitado: { _avanzadaRev; return avanzadaDraft["enable_assets_pipeline"] === "1" }
                                }
                                CampoTexto {
                                    etiqueta: "Reintentos máximos"
                                    descripcion: "Intentos antes de marcar como fallido."
                                    clave: "assets_max_retries"; draftObj: avanzadaDraft
                                    validador: "entero_no_negativo"
                                    habilitado: { _avanzadaRev; return avanzadaDraft["enable_assets_pipeline"] === "1" }
                                }
                                CampoTexto {
                                    etiqueta: "Backoff entre reintentos (seg)"
                                    descripcion: "Espera entre reintento y reintento."
                                    clave: "assets_retry_backoff_seg"; draftObj: avanzadaDraft
                                    validador: "positivo"
                                    habilitado: { _avanzadaRev; return avanzadaDraft["enable_assets_pipeline"] === "1" }
                                }
                                CampoTexto {
                                    etiqueta: "TTL caché positiva (seg)"
                                    descripcion: "Cuánto tiempo guardar resultados exitosos."
                                    clave: "assets_cache_ttl_seg"; draftObj: avanzadaDraft
                                    validador: "positivo"
                                    habilitado: { _avanzadaRev; return avanzadaDraft["enable_assets_pipeline"] === "1" }
                                }
                                CampoTexto {
                                    etiqueta: "TTL caché negativa (seg)"
                                    descripcion: "Cuánto tiempo recordar que un recurso no existe."
                                    clave: "assets_negative_cache_ttl_seg"; draftObj: avanzadaDraft
                                    validador: "positivo"
                                    habilitado: { _avanzadaRev; return avanzadaDraft["enable_assets_pipeline"] === "1" }
                                }
                                CampoTexto {
                                    etiqueta: "Resolución mínima (px)"
                                    descripcion: "Imágenes menores a este tamaño se descartan."
                                    clave: "assets_min_resolution"; draftObj: avanzadaDraft
                                    validador: "entero_positivo"
                                    habilitado: { _avanzadaRev; return avanzadaDraft["enable_assets_pipeline"] === "1" }
                                }
                                CampoTexto {
                                    etiqueta: "Máximo HD por imagen (bytes)"
                                    descripcion: "Límite de descarga para assets HD validados."
                                    clave: "assets_hd_max_image_bytes"; draftObj: avanzadaDraft
                                    validador: "entero_positivo"
                                    habilitado: { _avanzadaRev; return avanzadaDraft["enable_assets_pipeline"] === "1" }
                                }
                            }
                        }
                    }

                    // ── LETRAS ───────────────────────────────────────────
                    GrupoConfig {
                        titulo: "Letras y enriquecimiento"
                        descripcion: "Controla la búsqueda externa de letras y sus reintentos controlados."
                        Layout.fillWidth: true

                        ColumnLayout {
                            spacing: UiTokens.spacing10
                            ToggleCampo {
                                label: "Habilitar enriquecimiento externo"
                                checkedValue: { _avanzadaRev; return avanzadaDraft["enable_external_enrichment"] === "1" }
                                onChangedValue: function(v) { setAvanzadaValue("enable_external_enrichment", v ? "1" : "0") }
                            }
                            ToggleCampo {
                                visible: { _avanzadaRev; return avanzadaDraft["enable_external_enrichment"] === "1" }
                                label: "Buscar letras automáticamente"
                                checkedValue: { _avanzadaRev; return avanzadaDraft["enable_lyrics_enrichment"] === "1" }
                                habilitado: { _avanzadaRev; return avanzadaDraft["enable_external_enrichment"] === "1" }
                                onChangedValue: function(v) { setAvanzadaValue("enable_lyrics_enrichment", v ? "1" : "0") }
                            }
                            GridLayout {
                                visible: { _avanzadaRev; return avanzadaDraft["enable_external_enrichment"] === "1" && avanzadaDraft["enable_lyrics_enrichment"] === "1" }
                                Layout.fillWidth: true
                                columns: mediumWidth ? 2 : 1
                                columnSpacing: 12; rowSpacing: 10
                                ToggleCampo {
                                    label: "LRCLIB"
                                    checkedValue: { _avanzadaRev; return avanzadaDraft["enable_lrclib"] === "1" }
                                    habilitado: { _avanzadaRev; return avanzadaDraft["enable_external_enrichment"] === "1" && avanzadaDraft["enable_lyrics_enrichment"] === "1" }
                                    onChangedValue: function(v) { setAvanzadaValue("enable_lrclib", v ? "1" : "0") }
                                }
                                ToggleCampo {
                                    label: "lyrics.ovh"
                                    checkedValue: { _avanzadaRev; return avanzadaDraft["enable_lyrics_ovh"] === "1" }
                                    habilitado: { _avanzadaRev; return avanzadaDraft["enable_external_enrichment"] === "1" && avanzadaDraft["enable_lyrics_enrichment"] === "1" }
                                    onChangedValue: function(v) { setAvanzadaValue("enable_lyrics_ovh", v ? "1" : "0") }
                                }
                                CampoTexto {
                                    etiqueta: "Timeout letras (segundos)"
                                    descripcion: "Tiempo máximo por solicitud."
                                    clave: "lyrics_timeout_seg"; draftObj: avanzadaDraft
                                    validador: "positivo"
                                    habilitado: { _avanzadaRev; return avanzadaDraft["enable_external_enrichment"] === "1" && avanzadaDraft["enable_lyrics_enrichment"] === "1" }
                                }
                                CampoTexto {
                                    etiqueta: "Reintentos letras"
                                    descripcion: "Intentos adicionales ante errores temporales."
                                    clave: "lyrics_max_retries"; draftObj: avanzadaDraft
                                    validador: "entero_no_negativo"
                                    habilitado: { _avanzadaRev; return avanzadaDraft["enable_external_enrichment"] === "1" && avanzadaDraft["enable_lyrics_enrichment"] === "1" }
                                }
                                CampoTexto {
                                    etiqueta: "Backoff letras (seg)"
                                    descripcion: "Espera entre reintentos."
                                    clave: "lyrics_retry_backoff_seg"; draftObj: avanzadaDraft
                                    validador: "positivo"
                                    habilitado: { _avanzadaRev; return avanzadaDraft["enable_external_enrichment"] === "1" && avanzadaDraft["enable_lyrics_enrichment"] === "1" }
                                }
                                CampoTexto {
                                    etiqueta: "Candidatos suggest"
                                    descripcion: "Máximo de candidatos de lyrics.ovh/suggest."
                                    clave: "lyrics_suggest_limit"; draftObj: avanzadaDraft
                                    validador: "entero_no_negativo"
                                    habilitado: { _avanzadaRev; return avanzadaDraft["enable_external_enrichment"] === "1" && avanzadaDraft["enable_lyrics_enrichment"] === "1" && avanzadaDraft["enable_lyrics_ovh"] === "1" }
                                }
                            }
                        }
                    }

                    // ── SEGUNDA FASE ──────────────────────────────────────
                    GrupoConfig {
                        titulo: "Segunda fase de resolución"
                        descripcion: "Analiza candidatos adicionales para mejorar la tasa de aceptación en casos inciertos de la primera fase."
                        Layout.fillWidth: true

                        ColumnLayout {
                            spacing: UiTokens.spacing10
                            ToggleCampo {
                                label: "Habilitar segunda fase de resolución"
                                checkedValue: { _avanzadaRev; return avanzadaDraft["enable_second_stage_resolution"] === "1" }
                                onChangedValue: function(v) { setAvanzadaValue("enable_second_stage_resolution", v ? "1" : "0") }
                            }
                            GridLayout {
                                Layout.fillWidth: true
                                columns: mediumWidth ? 3 : 1
                                columnSpacing: 12; rowSpacing: 10
                                CampoTexto {
                                    etiqueta: "Máximo de candidatos"
                                    descripcion: "Cuántos candidatos alternativos se evalúan."
                                    clave: "second_stage_max_candidates"; draftObj: avanzadaDraft
                                    validador: "entero_positivo"
                                }
                                CampoTexto {
                                    etiqueta: "Evidencia mínima (0.0 – 1.0)"
                                    descripcion: "Score mínimo para aceptar en esta fase."
                                    clave: "second_stage_min_evidence"; draftObj: avanzadaDraft
                                    validador: "score"
                                }
                                CampoTexto {
                                    etiqueta: "Gap mínimo (0.0 – 1.0)"
                                    descripcion: "Diferencia mínima frente al segundo candidato."
                                    clave: "second_stage_min_gap"; draftObj: avanzadaDraft
                                    validador: "score"
                                }
                            }
                            ToggleCampo {
                                visible: { _avanzadaRev; return avanzadaDraft["enable_second_stage_resolution"] === "1" }
                                label: "Registrar causa de decisión en los logs"
                                checkedValue: { _avanzadaRev; return avanzadaDraft["second_stage_cause_enabled"] === "1" }
                                onChangedValue: function(v) { setAvanzadaValue("second_stage_cause_enabled", v ? "1" : "0") }
                            }
                        }
                    }

                    // ── TERCERA FASE ──────────────────────────────────────
                    GrupoConfig {
                        titulo: "Tercera fase de resolución"
                        descripcion: "Capa adicional de alta confianza para tracks que requieren confirmación extra antes de aceptarse."
                        Layout.fillWidth: true

                        ColumnLayout {
                            spacing: UiTokens.spacing10
                            ToggleCampo {
                                label: "Habilitar tercera fase de resolución"
                                checkedValue: { _avanzadaRev; return avanzadaDraft["enable_third_stage_resolution"] === "1" }
                                onChangedValue: function(v) { setAvanzadaValue("enable_third_stage_resolution", v ? "1" : "0") }
                            }
                            GridLayout {
                                visible: { _avanzadaRev; return avanzadaDraft["enable_third_stage_resolution"] === "1" }
                                Layout.fillWidth: true
                                columns: mediumWidth ? 2 : 1
                                columnSpacing: 12; rowSpacing: 10
                                CampoTexto {
                                    etiqueta: "Evidencia mínima (0.0 – 1.0)"
                                    descripcion: "Umbral más estricto que la segunda fase."
                                    clave: "third_stage_min_evidence"; draftObj: avanzadaDraft
                                    validador: "score"
                                }
                                CampoTexto {
                                    etiqueta: "Gap mínimo (0.0 – 1.0)"
                                    descripcion: "Diferencia exigida respecto al siguiente candidato."
                                    clave: "third_stage_min_gap"; draftObj: avanzadaDraft
                                    validador: "score"
                                }
                            }
                        }
                    }

                    // ── DISCOGRAFÍA ASISTIDA ──────────────────────────────
                    GrupoConfig {
                        titulo: "Discografía asistida por IA"
                        descripcion: "Usa IA para inferir la discografía del artista y mejorar resolución de álbumes incompletos o poco conocidos."
                        Layout.fillWidth: true

                        ColumnLayout {
                            spacing: UiTokens.spacing10
                            ToggleCampo {
                                objectName: "config_ia_discography_toggle"
                                label: "Habilitar discografía asistida por IA"
                                checkedValue: { _avanzadaRev; return avanzadaDraft["enable_ia_discography"] === "1" }
                                onChangedValue: function(v) { setAvanzadaValue("enable_ia_discography", v ? "1" : "0") }
                            }
                            CampoTexto {
                                objectName: "config_discography_ia_min_confidence"
                                visible: { _avanzadaRev; return avanzadaDraft["enable_ia_discography"] === "1" }
                                etiqueta: "Confianza mínima (0.0 – 1.0)"
                                descripcion: "Nivel mínimo de confianza de la IA para aceptar una inferencia discográfica."
                                clave: "discography_ia_min_confidence"; draftObj: avanzadaDraft
                                validador: "score"
                            }
                        }
                    }

                    // ── PROGRESO Y SIDECARS ──────────────────────────────
                    GrupoConfig {
                        titulo: "Progreso y tareas secundarias"
                        descripcion: "Ajusta la salida de progreso y los límites de espera para assets, letras y manifiestos."
                        Layout.fillWidth: true

                        ColumnLayout {
                            spacing: UiTokens.spacing10
                            ColumnLayout {
                                objectName: "config_nb_sound_progress_mode"
                                Layout.fillWidth: true
                                spacing: UiTokens.spacing8
                                AppText {
                                    text: "Modo de progreso de terminal"
                                    font.pixelSize: UiTokens.fontSizeBase
                                    color: tema.texto
                                    Layout.fillWidth: true
                                    wrapMode: Text.WordWrap
                                }
                                AppText {
                                    text: "auto elige barra viva en TTY y snapshots en logs; quiet reduce la salida."
                                    font.pixelSize: UiTokens.fontSizeSm
                                    color: tema.textoMuted
                                    Layout.fillWidth: true
                                    wrapMode: Text.WordWrap
                                }
                                Flow {
                                    Layout.fillWidth: true
                                    spacing: UiTokens.spacing10
                                    PillOption {
                                        objectName: "config_nb_sound_progress_mode_auto"
                                        texto: "Auto"
                                        activo: { _avanzadaRev; return avanzadaDraft["nb_sound_progress_mode"] === "auto" }
                                        onClicked: setAvanzadaValue("nb_sound_progress_mode", "auto")
                                    }
                                    PillOption {
                                        objectName: "config_nb_sound_progress_mode_tty"
                                        texto: "TTY"
                                        activo: { _avanzadaRev; return avanzadaDraft["nb_sound_progress_mode"] === "tty" }
                                        onClicked: setAvanzadaValue("nb_sound_progress_mode", "tty")
                                    }
                                    PillOption {
                                        objectName: "config_nb_sound_progress_mode_log"
                                        texto: "Log"
                                        activo: { _avanzadaRev; return avanzadaDraft["nb_sound_progress_mode"] === "log" }
                                        onClicked: setAvanzadaValue("nb_sound_progress_mode", "log")
                                    }
                                    PillOption {
                                        objectName: "config_nb_sound_progress_mode_quiet"
                                        texto: "Quiet"
                                        activo: { _avanzadaRev; return avanzadaDraft["nb_sound_progress_mode"] === "quiet" }
                                        onClicked: setAvanzadaValue("nb_sound_progress_mode", "quiet")
                                    }
                                }
                            }
                            GridLayout {
                                Layout.fillWidth: true
                                columns: mediumWidth ? 3 : 1
                                columnSpacing: 12; rowSpacing: 10
                                CampoTexto {
                                    etiqueta: "Intervalo de progreso (seg)"
                                    descripcion: "Frecuencia de snapshots cuando no hay barra interactiva."
                                    clave: "nb_sound_progress_interval_sec"; draftObj: avanzadaDraft
                                    validador: "positivo"
                                }
                                CampoTexto {
                                    etiqueta: "Timeout de sidecar (seg)"
                                    descripcion: "Tiempo máximo para una tarea secundaria antes de degradar."
                                    clave: "sidecar_future_timeout_seg"; draftObj: avanzadaDraft
                                    validador: "positivo"
                                }
                                CampoTexto {
                                    etiqueta: "Heartbeat sidecar (seg)"
                                    descripcion: "Frecuencia del pulso mientras se espera a tareas secundarias."
                                    clave: "sidecar_wait_heartbeat_seg"; draftObj: avanzadaDraft
                                    validador: "positivo"
                                }
                            }
                        }
                    }

                    // ── ANÁLISIS MUSICAL INTELIGENTE ─────────────────────
                    GrupoConfig {
                        titulo: "Análisis musical inteligente"
                        descripcion: "Audio Features y Audio Intelligence local. Esta sección NO usa IA externa de desempate (Anthropic/OpenAI)."
                        Layout.fillWidth: true
                        ColumnLayout {
                            spacing: UiTokens.spacing10
                            SectionHeading {
                                titulo: "Audio Features"
                                descripcion: "Análisis liviano para BPM, energía, vibes y discovery básico."
                            }
                            ToggleCampo {
                                label: "Habilitar Audio Features"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["enable_audio_features"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("enable_audio_features", v ? "1" : "0") }
                            }
                            Flow {
                                spacing: UiTokens.spacing10
                                PillOption {
                                    texto: "Light"
                                    activo: _avanzadaRev >= 0 && avanzadaDraft["audio_features_mode"] === "light"
                                    onClicked: setAvanzadaValue("audio_features_mode", "light")
                                }
                                PillOption {
                                    texto: "Standard"
                                    activo: _avanzadaRev >= 0 && avanzadaDraft["audio_features_mode"] === "standard"
                                    onClicked: setAvanzadaValue("audio_features_mode", "standard")
                                }
                            }
                            GridLayout {
                                Layout.fillWidth: true
                                columns: mediumWidth ? 3 : 1
                                columnSpacing: 12; rowSpacing: 10
                                CampoTexto { etiqueta: "Workers Audio Features"; clave: "audio_features_max_workers"; draftObj: avanzadaDraft; validador: "entero_positivo" }
                                CampoTexto { etiqueta: "Segmento (seg)"; clave: "audio_features_segment_seconds"; draftObj: avanzadaDraft; validador: "entero_positivo" }
                                CampoTexto { etiqueta: "Estrategia de muestra"; descripcion: "smart_segments | first_segment | middle_segment | full_track"; clave: "audio_features_sample_strategy"; draftObj: avanzadaDraft }
                            }
                            ToggleCampo {
                                label: "Analizar al importar"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["audio_features_analyze_on_import"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("audio_features_analyze_on_import", v ? "1" : "0") }
                            }
                            ToggleCampo {
                                label: "Background Audio Features"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["audio_features_background"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("audio_features_background", v ? "1" : "0") }
                            }
                            ToggleCampo {
                                label: "Analizar pista completa"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["audio_features_analyze_full_track"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("audio_features_analyze_full_track", v ? "1" : "0") }
                            }
                            ToggleCampo {
                                label: "Reanalizar por cambio de versión"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["audio_features_reanalyze_on_version_change"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("audio_features_reanalyze_on_version_change", v ? "1" : "0") }
                            }
                            ToggleCampo {
                                label: "No interrumpir importación si falla"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["audio_features_fail_silently"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("audio_features_fail_silently", v ? "1" : "0") }
                            }
                            // Fase 3: grupo "Deep Background" — oculto en plataformas sin
                            // análisis profundo (Windows: essentia-tensorflow sin wheel funcional).
                            // La lógica Python deep se conserva; solo se condiciona la UI.
                            ColumnLayout {
                                id: deepBackgroundGroup
                                Layout.fillWidth: true
                                spacing: UiTokens.spacing10
                                visible: deepAnalyticsDisponible

                            Rectangle {
                                Layout.fillWidth: true; radius: UiTokens.radiusSm; color: Qt.rgba(tema.advertencia.r, tema.advertencia.g, tema.advertencia.b, 0.08); border.color: Qt.rgba(tema.advertencia.r, tema.advertencia.g, tema.advertencia.b, 0.3); border.width: 1
                                implicitHeight: warnDeep.implicitHeight + 16
                                AppText { id: warnDeep; anchors.fill: parent; anchors.margins: UiTokens.spacing8; wrapMode: Text.WordWrap; color: tema.textoSec; font.pixelSize: UiTokens.fontSizeMd; text: "Audio Intelligence profunda es opcional. Para importaciones masivas usa background; el modo al importar es síncrono/legacy y puede bloquear." }
                            }
                            SectionHeading {
                                titulo: "Deep Background"
                                descripcion: "Cola persistente en SQLite para Essentia TensorFlow, reanudable desde UI o CLI."
                            }
                            ToggleCampo {
                                label: "Habilitar Audio Intelligence profunda"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["enable_audio_intelligence_deep"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("enable_audio_intelligence_deep", v ? "1" : "0") }
                            }
                            Flow {
                                spacing: UiTokens.spacing10
                                PillOption {
                                    texto: "None"
                                    activo: _avanzadaRev >= 0 && avanzadaDraft["audio_intelligence_backend"] === "none"
                                    onClicked: setAvanzadaValue("audio_intelligence_backend", "none")
                                }
                                PillOption {
                                    texto: "Essentia TF"
                                    activo: _avanzadaRev >= 0 && avanzadaDraft["audio_intelligence_backend"] === "essentia_tensorflow"
                                    onClicked: setAvanzadaValue("audio_intelligence_backend", "essentia_tensorflow")
                                }
                            }
                            GridLayout {
                                Layout.fillWidth: true
                                columns: mediumWidth ? 3 : 1
                                columnSpacing: 12; rowSpacing: 10
                                CampoTexto { etiqueta: "Model dir deep"; clave: "audio_intelligence_model_dir"; draftObj: avanzadaDraft }
                                CampoTexto { etiqueta: "Workers deep"; clave: "audio_intelligence_max_workers"; draftObj: avanzadaDraft; validador: "entero_positivo" }
                                CampoTexto { etiqueta: "Batch background"; clave: "audio_intelligence_background_batch_size"; draftObj: avanzadaDraft; validador: "entero_positivo" }
                                CampoTexto { etiqueta: "Idle delay (seg)"; clave: "audio_intelligence_background_idle_delay_sec"; draftObj: avanzadaDraft }
                                CampoTexto { etiqueta: "Runtime máx (min)"; descripcion: "0 significa sin límite."; clave: "audio_intelligence_background_max_runtime_min"; draftObj: avanzadaDraft; validador: "entero_no_negativo" }
                                CampoTexto { etiqueta: "Intentos máximos"; clave: "audio_intelligence_max_attempts"; draftObj: avanzadaDraft; validador: "entero_positivo" }
                                CampoTexto { etiqueta: "Segmento deep (seg)"; clave: "audio_intelligence_segment_seconds"; draftObj: avanzadaDraft; validador: "entero_positivo" }
                                CampoTexto { etiqueta: "Estrategia deep"; descripcion: "smart_segments | first_segment | middle_segment | full_track"; clave: "audio_intelligence_sample_strategy"; draftObj: avanzadaDraft }
                            }
                            ToggleCampo {
                                label: "Habilitar modelos de mood"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["enable_audio_mood_models"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("enable_audio_mood_models", v ? "1" : "0") }
                            }
                            ToggleCampo {
                                label: "Habilitar embeddings"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["enable_audio_embeddings"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("enable_audio_embeddings", v ? "1" : "0") }
                            }
                            ToggleCampo {
                                label: "Habilitar auto-tagging/genre"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["enable_audio_tagging_models"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("enable_audio_tagging_models", v ? "1" : "0") }
                            }
                            ToggleCampo {
                                label: "Deep al importar (legacy bloqueante)"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["audio_intelligence_analyze_on_import"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("audio_intelligence_analyze_on_import", v ? "1" : "0") }
                            }
                            ToggleCampo {
                                label: "Encolar deep tras importar"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["audio_intelligence_analyze_after_import_background"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("audio_intelligence_analyze_after_import_background", v ? "1" : "0") }
                            }
                            ToggleCampo {
                                label: "Background deep"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["audio_intelligence_background"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("audio_intelligence_background", v ? "1" : "0") }
                            }
                            ToggleCampo {
                                label: "Autostart background"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["audio_intelligence_background_autostart"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("audio_intelligence_background_autostart", v ? "1" : "0") }
                            }
                            ToggleCampo {
                                label: "Reanudar pendientes al iniciar"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["audio_intelligence_resume_pending_on_startup"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("audio_intelligence_resume_pending_on_startup", v ? "1" : "0") }
                            }
                            ToggleCampo {
                                label: "Permitir descargas de modelos"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["audio_intelligence_allow_model_downloads"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("audio_intelligence_allow_model_downloads", v ? "1" : "0") }
                            }
                            ToggleCampo {
                                label: "Reanalizar si cambia el modelo"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["audio_intelligence_reanalyze_on_model_change"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("audio_intelligence_reanalyze_on_model_change", v ? "1" : "0") }
                            }
                            ToggleCampo {
                                label: "Reintentar fallidas automáticamente"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["audio_intelligence_retry_failed"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("audio_intelligence_retry_failed", v ? "1" : "0") }
                            }
                            ToggleCampo {
                                label: "Descartar outputs al cancelar por defecto"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["audio_intelligence_cancel_discard_outputs"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("audio_intelligence_cancel_discard_outputs", v ? "1" : "0") }
                            }
                            ToggleCampo {
                                label: "No interrumpir si deep falla"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["audio_intelligence_fail_silently"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("audio_intelligence_fail_silently", v ? "1" : "0") }
                            }
                            } // fin grupo Deep Background (visible: deepAnalyticsDisponible)

                            SectionHeading {
                                titulo: "Music Discovery"
                                descripcion: "Consulta natural sobre señales basic y deep listas."
                            }
                            ToggleCampo {
                                label: "Music Discovery habilitado"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["enable_music_discovery"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("enable_music_discovery", v ? "1" : "0") }
                            }
                            ToggleCampo {
                                label: "Usar Audio Features en discovery"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["music_discovery_use_audio_features"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("music_discovery_use_audio_features", v ? "1" : "0") }
                            }
                            ToggleCampo {
                                label: "Usar features deep en discovery"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["music_discovery_use_deep_features"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("music_discovery_use_deep_features", v ? "1" : "0") }
                            }
                            ToggleCampo {
                                label: "Explicar resultados"
                                checkedValue: _avanzadaRev >= 0 && avanzadaDraft["music_discovery_explain_results"] === "1"
                                onChangedValue: function(v) { setAvanzadaValue("music_discovery_explain_results", v ? "1" : "0") }
                            }
                            GridLayout {
                                Layout.fillWidth: true
                                columns: mediumWidth ? 2 : 1
                                columnSpacing: 12; rowSpacing: 10
                                CampoTexto { etiqueta: "Confidence mínima discovery"; clave: "music_discovery_min_confidence"; draftObj: avanzadaDraft; validador: "score" }
                                CampoTexto { etiqueta: "Límite por defecto"; clave: "music_discovery_default_limit"; draftObj: avanzadaDraft; validador: "entero_positivo" }
                            }
                        }
                    }

                    // ── MANIFIESTOS ───────────────────────────────────────
                    GrupoConfig {
                        titulo: "Manifiestos y overrides"
                        descripcion: "Los manifiestos son índices canónicos del estado de la biblioteca. Los overrides permiten correcciones manuales persistentes."
                        Layout.fillWidth: true

                        ColumnLayout {
                            spacing: UiTokens.spacing10
                            ToggleCampo {
                                label: "Permitir overrides manuales en manifiestos"
                                checkedValue: { _avanzadaRev; return avanzadaDraft["enable_overrides"] === "1" }
                                onChangedValue: function(v) { setAvanzadaValue("enable_overrides", v ? "1" : "0") }
                            }
                            CampoTexto {
                                etiqueta: "Versión de schema de manifiestos"
                                descripcion: "Versión del formato de los archivos de manifiesto. No cambiar salvo indicación explícita."
                                clave: "manifest_schema_version"; draftObj: avanzadaDraft
                                validador: "entero_positivo"
                            }
                        }
                    }
                }

                FooterModulo {
                    objectPrefix: "avanzada"
                    Layout.alignment: Qt.AlignHCenter
                    deshabilitarGuardar: { _avanzadaRev; return !avanzadaValida() }
                    onGuardar: saveAvanzada()
                    onPredeterminados: defaultsAvanzada()
                }
            }

            // ─────────────────────────────────────────────────────────────────
            // SECCIÓN PERSONALIZACIÓN
            // ─────────────────────────────────────────────────────────────────
            ColumnLayout {
                objectName: "config_personalizacion"
                visible: seccion_activa === "personalizacion"
                Layout.fillWidth: true
                Layout.leftMargin: horizontalPadding
                Layout.rightMargin: horizontalPadding
                Layout.maximumWidth: contentMaxWidth
                Layout.alignment: Qt.AlignHCenter
                spacing: 18

                // Header personalización
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: headerPersonalLayout.implicitHeight + 32
                    radius: 16
                    color: tema.superficie
                    border.color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.16)
                    border.width: 1

                    RowLayout {
                        id: headerPersonalLayout
                        anchors.fill: parent
                        anchors.margins: UiTokens.spacing16
                        spacing: UiTokens.spacing14

                        Rectangle {
                            width: 48; height: 48; radius: 12
                            color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.12)
                            border.color: tema.acento; border.width: 1
                            AppText { anchors.centerIn: parent; text: "✦"; font.pixelSize: 22; color: tema.acento }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: UiTokens.spacing4
                            AppText { text: "Personalización"; font.pixelSize: UiTokens.fontSize2xl; font.weight: Font.DemiBold; color: tema.texto }
                            AppText {
                                text: "Ajusta tema, tipografía, escala y opciones del reproductor. Esta sección se guarda al instante."
                                font.pixelSize: UiTokens.fontSizeMd; color: tema.textoMuted; wrapMode: Text.WordWrap; Layout.fillWidth: true
                            }
                        }
                    }
                }

                // ── Ecualizador y opciones del reproductor global ──────────
                // Aplica SOLO al reproductor general (no al DJ Privado). Se
                // guarda al instante en config_ui vía el modelo `reproductor`.
                GrupoConfig {
                    objectName: "config_personalizacion_ecualizador"
                    titulo: "Ecualizador del reproductor"
                    descripcion: "Afecta solo al reproductor general (no al DJ Privado). Los cambios se aplican y guardan al instante."

                    // Activar / desactivar el ecualizador
                    ToggleCampo {
                        objectName: "config_eq_activo"
                        label: "Ecualizador"
                        checkedValue: reproductor.eq_activo
                        onChangedValue: reproductor.set_ecualizador_activo(value)
                    }

                    // Preajustes (18 presets de VLC) + "Personalizado"
                    AppText {
                        text: "Preajustes"
                        font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.DemiBold
                        color: reproductor.eq_activo ? tema.texto : tema.textoMuted
                        opacity: reproductor.eq_activo ? 1.0 : 0.55
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: UiTokens.spacing8
                        opacity: reproductor.eq_activo ? 1.0 : 0.45
                        Repeater {
                            model: reproductor.eq_presets_nombres
                            delegate: PillOption {
                                required property int index
                                required property var modelData
                                objectName: "config_eq_preset_" + index
                                texto: modelData
                                activo: reproductor.eq_preset === index
                                onClicked: { if (reproductor.eq_activo) reproductor.aplicar_ecualizador_preset(index) }
                            }
                        }
                        // Indicador "Personalizado": se enciende al mover una banda.
                        PillOption {
                            objectName: "config_eq_preset_custom"
                            texto: "Personalizado"
                            activo: reproductor.eq_preset === -1
                        }
                    }

                    // 10 bandas (sliders verticales) con scroll horizontal en
                    // anchos reducidos. Se atenúan/deshabilitan con el EQ apagado.
                    Flickable {
                        Layout.fillWidth: true
                        implicitHeight: bandasRow.implicitHeight
                        contentWidth: bandasRow.implicitWidth
                        contentHeight: bandasRow.implicitHeight
                        flickableDirection: Flickable.HorizontalFlick
                        boundsBehavior: Flickable.StopAtBounds
                        clip: true

                        Row {
                            id: bandasRow
                            spacing: UiTokens.spacing12
                            padding: 2
                            Repeater {
                                model: reproductor.eq_bandas_hz
                                delegate: EqBandaSlider {
                                    required property int index
                                    required property var modelData
                                    objectName: "config_eq_banda_" + index
                                    indice: index
                                    etiqueta: modelData >= 1000 ? (modelData / 1000) + "k" : ("" + modelData)
                                    valor: {
                                        var b = reproductor.eq_bandas
                                        return (b && b[index] !== undefined) ? b[index] : 0
                                    }
                                    minimo: reproductor.eq_amp_min
                                    maximo: reproductor.eq_amp_max
                                    habilitado: reproductor.eq_activo
                                    onCambiado: (db) => reproductor.set_ecualizador_banda(index, db)
                                }
                            }
                        }
                    }

                    // Preamplificación (slider horizontal reutilizando SliderLine)
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: UiTokens.spacing12
                        opacity: reproductor.eq_activo ? 1.0 : 0.45
                        AppText {
                            text: "Pre-amp"
                            font.pixelSize: UiTokens.fontSizeBase
                            color: tema.texto
                            Layout.preferredWidth: 70
                        }
                        SliderLine {
                            id: preampSlider
                            objectName: "config_eq_preamp"
                            Layout.fillWidth: true
                            enabled: reproductor.eq_activo
                            live: true
                            readonly property real _rango: reproductor.eq_preamp_max - reproductor.eq_preamp_min
                            ratio: _rango > 0 ? (reproductor.eq_preamp - reproductor.eq_preamp_min) / _rango : 0
                            onMoved: (r) => reproductor.set_ecualizador_preamp(
                                reproductor.eq_preamp_min + r * _rango)
                        }
                        AppText {
                            text: (reproductor.eq_preamp > 0 ? "+" : "") + Math.round(reproductor.eq_preamp) + " dB"
                            font.pixelSize: UiTokens.fontSizeSm; color: tema.textoMuted
                            Layout.preferredWidth: 54
                            horizontalAlignment: Text.AlignRight
                        }
                    }

                    // Estabilizar volumen (normvol, per-media en el global)
                    ToggleCampo {
                        objectName: "config_audio_normalizar"
                        label: "Estabilizar volumen"
                        checkedValue: reproductor.normalizar_volumen
                        onChangedValue: reproductor.set_normalizar_volumen(value)
                    }
                    AppText {
                        Layout.fillWidth: true
                        text: "Nivela el volumen entre pistas. Al cambiarlo, el audio se reinicia un instante en la pista actual."
                        font.pixelSize: UiTokens.fontSizeSm; color: tema.textoMuted
                        wrapMode: Text.WordWrap
                    }
                }

                GrupoConfig {
                    objectName: "config_personalizacion_fuentes"
                    titulo: "Tipografía de la interfaz"
                    descripcion: "Afecta todos los textos de la aplicación (los cambios se autoguardan al instante)."

                    GridLayout {
                        Layout.fillWidth: true
                        columns: compactWidth ? 2 : (mediumWidth ? 3 : 2)
                        columnSpacing: 10
                        rowSpacing: 10

                        Repeater {
                            model: fontOptions
                            delegate: Rectangle {
                                required property var modelData
                                objectName: "config_font_option_" + String(modelData).replace(/[^A-Za-z0-9_]/g, "_")
                                Layout.fillWidth: true
                                height: 75
                                radius: 12
                                
                                readonly property bool esFontActiva: { _personalRev; return configuracion.obtener("ui_font_family") === modelData }
                                color: esFontActiva ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.14) : (fArea.containsMouse ? tema.hover : tema.superficieAlt)
                                border.color: esFontActiva ? tema.acento : tema.borde
                                border.width: esFontActiva ? 2 : 1
                                
                                Behavior on color { ColorAnimation { duration: 150 } }
                                Behavior on border.color { ColorAnimation { duration: 150 } }

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: UiTokens.spacing14
                                    spacing: UiTokens.spacing12
                                    AppText {
                                        text: "Aa"
                                        font.family: modelData
                                        font.pixelSize: 28
                                        color: tema.texto
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: UiTokens.spacing2
                                        AppText {
                                            text: modelData
                                            font.family: modelData
                                            color: tema.texto; font.pixelSize: UiTokens.fontSizeLg; font.weight: esFontActiva ? Font.DemiBold : Font.Normal
                                            elide: Text.ElideRight; Layout.fillWidth: true
                                        }
                                        RowLayout {
                                            visible: esFontActiva
                                            spacing: UiTokens.spacing4
                                            Item {
                                                Layout.preferredWidth: 10
                                                Layout.preferredHeight: 10
                                                Layout.alignment: Qt.AlignVCenter
                                                Image {
                                                    id: _fontActChk
                                                    anchors.fill: parent
                                                    source: "../assets/icons/check.svg"
                                                    sourceSize.width: 20; sourceSize.height: 20
                                                    smooth: true; opacity: 0
                                                }
                                                MultiEffect {
                                                    anchors.fill: parent
                                                    source: _fontActChk
                                                    colorization: 1.0
                                                    colorizationColor: tema.acento
                                                }
                                            }
                                            AppText {
                                                text: "Activo"
                                                color: tema.acento; font.pixelSize: UiTokens.fontSizeXs; font.weight: Font.DemiBold
                                            }
                                        }
                                    }
                                }

                                MouseArea {
                                    id: fArea
                                    anchors.fill: parent
                                    hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        configuracion.guardar("ui_font_family", modelData)
                                        _personalRev++
                                    }
                                }
                            }
                        }
                    }
                }

                GrupoConfig {
                    objectName: "config_personalizacion_escala"
                    titulo: "Escala de la interfaz"
                    descripcion: "Ajusta el tamaño global de todos los elementos UI."
                    Flow {
                        Layout.fillWidth: true
                        spacing: UiTokens.spacing12
                        PillOption {
                            objectName: "config_escala_100"
                            texto: "100%"
                            activo: { _personalRev; return String(configuracion.obtener("ui_scale")) === "100" }
                            onClicked: { configuracion.guardar("ui_scale", "100"); _personalRev++ }
                        }
                        PillOption {
                            objectName: "config_escala_125"
                            texto: "125%"
                            activo: { _personalRev; return String(configuracion.obtener("ui_scale")) === "125" }
                            onClicked: { configuracion.guardar("ui_scale", "125"); _personalRev++ }
                        }
                        PillOption {
                            objectName: "config_escala_150"
                            texto: "150%"
                            activo: { _personalRev; return String(configuracion.obtener("ui_scale")) === "150" }
                            onClicked: { configuracion.guardar("ui_scale", "150"); _personalRev++ }
                        }
                        PillOption {
                            objectName: "config_escala_175"
                            texto: "175%"
                            activo: { _personalRev; return String(configuracion.obtener("ui_scale")) === "175" }
                            onClicked: { configuracion.guardar("ui_scale", "175"); _personalRev++ }
                        }
                        PillOption {
                            objectName: "config_escala_200"
                            texto: "200%"
                            activo: { _personalRev; return String(configuracion.obtener("ui_scale")) === "200" }
                            onClicked: { configuracion.guardar("ui_scale", "200"); _personalRev++ }
                        }
                    }
                }

                // ── Temas predeterminados ─────────────────────────────────
                GrupoConfig {
                    objectName: "config_personalizacion_temas"
                    titulo: "Tema de la interfaz"
                    descripcion: "Elige un tema visual. El cambio se aplica al instante sin necesidad de guardar."

                    GridLayout {
                        width: parent.width
                        columns: compactWidth ? 2 : (mediumWidth ? 3 : 2)
                        columnSpacing: 10
                        rowSpacing: 10

                        Repeater {
                            model: temaUi.temas_disponibles.filter(function(t) { return t.id !== "custom" })
                            delegate: Rectangle {
                                required property var modelData
                                objectName: "config_tema_" + String(modelData.id)

                                Layout.fillWidth: true
                                height: 70
                                radius: 12

                                readonly property bool esTemaActivo: temaUi.tema_id === modelData.id
                                readonly property color fondoPreview: modelData.fondo || tema.fondoElevado
                                readonly property color superficiePreview: modelData.superficie || fondoPreview
                                readonly property color superficieAltPreview: modelData.superficieAlt || superficiePreview
                                readonly property color bordePreview: modelData.borde || tema.borde
                                readonly property color acentoPreview: modelData.acento || tema.acento
                                readonly property color textoPreview: modelData.texto || tema.texto

                                color: esTemaActivo ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.14) : (tArea.containsMouse ? tema.hover : tema.superficieAlt)
                                border.color: esTemaActivo ? tema.acento : tema.borde
                                border.width: esTemaActivo ? 2 : 1

                                Behavior on color { ColorAnimation { duration: 150 } }
                                Behavior on border.color { ColorAnimation { duration: 150 } }
                                Behavior on border.width { NumberAnimation { duration: 150 } }

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: UiTokens.spacing12
                                    spacing: UiTokens.spacing10

                                    Rectangle {
                                        objectName: "config_tema_preview_" + String(modelData.id)
                                        width: 58; height: 42; radius: UiTokens.radiusMd
                                        color: fondoPreview
                                        border.color: bordePreview; border.width: 1
                                        Row {
                                            anchors.fill: parent
                                            anchors.margins: UiTokens.spacing6
                                            spacing: UiTokens.spacing4
                                            Rectangle { width: 10; height: parent.height; radius: 4; color: superficiePreview }
                                            Rectangle { width: 10; height: parent.height; radius: 4; color: superficieAltPreview }
                                            Rectangle { width: 10; height: parent.height; radius: 4; color: acentoPreview }
                                            Rectangle { width: 10; height: parent.height; radius: 4; color: textoPreview }
                                        }
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: UiTokens.spacing2
                                        AppText {
                                            text: modelData.nombre
                                            color: tema.texto; font.pixelSize: UiTokens.fontSizeMd; font.weight: Font.Medium
                                            elide: Text.ElideRight; Layout.fillWidth: true
                                        }
                                        RowLayout {
                                            visible: esTemaActivo
                                            spacing: UiTokens.spacing4
                                            Item {
                                                Layout.preferredWidth: 10
                                                Layout.preferredHeight: 10
                                                Layout.alignment: Qt.AlignVCenter
                                                Image {
                                                    id: _temaActChk
                                                    anchors.fill: parent
                                                    source: "../assets/icons/check.svg"
                                                    sourceSize.width: 20; sourceSize.height: 20
                                                    smooth: true; opacity: 0
                                                }
                                                MultiEffect {
                                                    anchors.fill: parent
                                                    source: _temaActChk
                                                    colorization: 1.0
                                                    colorizationColor: tema.acento
                                                }
                                            }
                                            AppText {
                                                text: "Activo"
                                                color: tema.acento; font.pixelSize: UiTokens.fontSizeXs; font.weight: Font.DemiBold
                                            }
                                        }
                                    }
                                }

                                MouseArea {
                                    id: tArea
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: temaUi.aplicar_tema(modelData.id)
                                }
                            }
                        }
                    }
                }
            }

            Item { Layout.fillWidth: true; height: 30 }
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // COMPONENTES
    // ─────────────────────────────────────────────────────────────────────────

    component FooterModulo: RowLayout {
        signal guardar()
        signal predeterminados()
        property string objectPrefix: ""
        property bool deshabilitarGuardar: false
        spacing: UiTokens.spacing12
        Layout.alignment: Qt.AlignHCenter
        Layout.topMargin: UiTokens.spacing8
        Layout.bottomMargin: UiTokens.spacing8
        BotonSecundario { objectName: objectPrefix + "_defaults_button"; texto: "Valores predeterminados"; onClicked: predeterminados() }
        BotonPrimario { objectName: objectPrefix + "_guardar_button"; texto: "Guardar configuración"; deshabilitado: deshabilitarGuardar; onClicked: guardar() }
    }

    component SectionHeading: ColumnLayout {
        property string titulo: ""
        property string descripcion: ""
        Layout.fillWidth: true
        spacing: UiTokens.spacing4
        AppText { text: titulo; color: tema.texto; font.pixelSize: UiTokens.fontSizeLg; font.weight: Font.DemiBold }
        AppText {
            text: descripcion; visible: descripcion !== ""
            color: tema.textoMuted; font.pixelSize: UiTokens.fontSizeMd
            wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
    }

    component Tab: Rectangle {
        id: tab_btn
        property string texto: ""
        property bool activo: false
        signal clicked()
        implicitHeight: 38
        radius: UiTokens.radiusMd
        color: activo ? tema.seleccion : (tabMa.containsMouse ? Qt.rgba(tema.hover.r, tema.hover.g, tema.hover.b, 0.6) : "transparent")
        border.color: activo ? tema.acento : "transparent"
        border.width: 1

        Behavior on color { ColorAnimation { duration: 150 } }

        AppText {
            anchors.centerIn: parent
            width: parent.width - 18
            text: parent.texto
            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
            font.pixelSize: UiTokens.fontSizeBase
            font.weight: parent.activo ? Font.DemiBold : Font.Normal
            color: parent.activo ? tema.texto : tema.textoSec

            Behavior on color { ColorAnimation { duration: 150 } }
        }
        MouseArea { id: tabMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: tab_btn.clicked() }
    }

    component RutaCard: Rectangle {
        id: rutaCard
        objectName: clave === "" ? "" : "config_ruta_" + clave
        property string etiqueta: ""
        property string clave: ""
        property string descripcion: ""
        property string ejemplo: "/home/usuario/Música/..."
        property var draftObj: ({})
        property var erroresObj: ({})
        property int columnas: 1
        property bool centrarEnDosColumnas: false
        property bool obligatoria: true
        readonly property string errorTexto: erroresObj && erroresObj[clave] ? String(erroresObj[clave]) : ""
        signal changed(string clave, string valor)

        radius: UiTokens.radiusLg
        color: tema.fondoElevado
        border.color: errorTexto !== "" ? Qt.rgba(tema.peligro.r, tema.peligro.g, tema.peligro.b, 0.75) : Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.9)
        border.width: 1
        Layout.fillWidth: true
        Layout.minimumWidth: 240
        Layout.maximumWidth: Number.POSITIVE_INFINITY
        Layout.preferredWidth: 300
        Layout.columnSpan: (columnas === 2 && centrarEnDosColumnas) ? 2 : 1
        Layout.alignment: (columnas === 2 && centrarEnDosColumnas) ? Qt.AlignHCenter : Qt.AlignLeft
        implicitHeight: contenidoRuta.implicitHeight + 22
        clip: true

        Behavior on border.color { ColorAnimation { duration: 180 } }
        Behavior on color { ColorAnimation { duration: 180 } }

        ColumnLayout {
            id: contenidoRuta
            anchors.fill: parent
            anchors.margins: UiTokens.spacing14
            spacing: 9

            RowLayout {
                Layout.fillWidth: true
                spacing: UiTokens.spacing10
                Rectangle {
                    width: 32; height: 32; radius: UiTokens.radiusSm
                    color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.10)
                    border.color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.20); border.width: 1
                    Image {
                        id: iconRutaCard
                        anchors { centerIn: parent; fill: parent; margins: UiTokens.spacing6 }
                        source: "../assets/icons/folder.svg"
                        fillMode: Image.PreserveAspectFit; smooth: true; visible: false
                    }
                    ColorOverlay { anchors.fill: iconRutaCard; source: iconRutaCard; color: tema.acento; visible: GraphicsInfo.api !== GraphicsInfo.Software }
                }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 3
                    AppText { text: etiqueta; font.pixelSize: UiTokens.fontSizeLg; font.weight: Font.DemiBold; color: tema.texto; Layout.fillWidth: true; elide: Text.ElideRight }
                    AppText { text: descripcion; font.pixelSize: UiTokens.fontSizeSm; color: tema.textoMuted; visible: descripcion !== ""; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                }
            }

            AppText {
                Layout.fillWidth: true
                text: obligatoria
                    ? "Ruta principal obligatoria"
                    : ((draftObj[clave] || "").trim() === ""
                        ? ("Opcional · fallback: " + ejemplo)
                        : "Ruta opcional personalizada")
                font.pixelSize: UiTokens.fontSizeXs; font.weight: Font.DemiBold
                color: obligatoria && (draftObj[clave] || "").trim() === "" ? tema.advertencia : tema.textoMuted
                wrapMode: Text.WordWrap
            }

            TextField {
                id: campoTextoRuta
                objectName: rutaCard.objectName === "" ? "" : rutaCard.objectName + "_input"
                Layout.fillWidth: true; Layout.minimumWidth: 0
                text: draftObj[clave] || ""
                onTextChanged: {
                    if (String(draftObj[clave] || "") !== text) {
                        rutaCard.changed(clave, text)
                    }
                }
                selectByMouse: true; clip: true
                color: tema.texto; font.family: raiz.fuenteUi; font.pixelSize: UiTokens.fontSizeMd
                leftPadding: 12; rightPadding: 12; topPadding: 10; bottomPadding: 10

                background: Rectangle {
                    id: bgRutaField
                    color: {
                        if (campoTextoRuta.activeFocus) return Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.08)
                        if (rutaHover.containsMouse) return Qt.rgba(tema.superficieAlt.r, tema.superficieAlt.g, tema.superficieAlt.b, 0.85)
                        return tema.superficieAlt
                    }
                    radius: UiTokens.radiusSm
                    border.color: rutaCard.errorTexto !== "" ? tema.peligro : (campoTextoRuta.activeFocus ? tema.acento : Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.5))
                    border.width: campoTextoRuta.activeFocus ? 1.5 : 1
                    Behavior on color { ColorAnimation { duration: 150 } }
                    Behavior on border.color { ColorAnimation { duration: 150 } }
                }

                MouseArea {
                    id: rutaHover
                    anchors.fill: parent
                    hoverEnabled: true; acceptedButtons: Qt.NoButton
                    cursorShape: Qt.IBeamCursor
                }
            }

            AppText {
                Layout.fillWidth: true
                visible: rutaCard.errorTexto !== ""
                text: rutaCard.errorTexto
                font.pixelSize: UiTokens.fontSizeSm
                color: tema.peligro
                wrapMode: Text.WordWrap
            }
        }

        states: [
            State {
                name: "hovered"
                when: cardMouse.containsMouse
                PropertyChanges {
                    target: rutaCard
                    border.color: rutaCard.errorTexto !== "" ? Qt.rgba(tema.peligro.r, tema.peligro.g, tema.peligro.b, 0.80) : Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.30)
                    color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.04)
                }
            },
            State {
                name: "normal"
                when: !cardMouse.containsMouse
            }
        ]

        MouseArea {
            id: cardMouse; anchors.fill: parent
            hoverEnabled: true; cursorShape: Qt.ArrowCursor; acceptedButtons: Qt.NoButton
        }
    }

    component GrupoConfig: ColumnLayout {
        property string titulo: ""
        property string descripcion: ""
        default property alias contenido: cont.data
        Layout.fillWidth: true
        spacing: UiTokens.spacing10
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: col_encab.implicitHeight + 36
            color: tema.superficie
            radius: UiTokens.radiusLg; border.color: tema.borde; border.width: 1
            ColumnLayout {
                id: col_encab
                anchors { fill: parent; margins: 18 }
                spacing: UiTokens.spacing10
                AppText { text: titulo; font.pixelSize: UiTokens.fontSizeXl; font.weight: Font.DemiBold; color: tema.texto }
                AppText { text: descripcion; font.pixelSize: UiTokens.fontSizeMd; color: tema.textoMuted; visible: descripcion !== ""; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                ColumnLayout {
                    id: cont
                    Layout.fillWidth: true
                    spacing: UiTokens.spacing12
                }
            }
        }
    }


    component CampoTexto: ColumnLayout {
        id: campoTextoRoot
        objectName: clave === "" ? "" : "config_campo_" + clave
        property string etiqueta: ""
        property string descripcion: ""
        property string clave: ""
        property var draftObj: ({})
        property bool habilitado: true
        property string scope: "avanzada"
        // Validadores: "", "score", "positivo", "entero_positivo", "entero_no_negativo"
        property string validador: ""

        Layout.fillWidth: true
        spacing: UiTokens.spacing4

        readonly property bool _tieneError: {
            if (!habilitado || validador === "") return false
            const v = String(draftObj[clave] || "").trim()
            if (v === "") return false
            if (validador === "score") {
                const n = parseFloat(v)
                return isNaN(n) || n < 0 || n > 1
            }
            if (validador === "positivo") {
                const n = parseFloat(v)
                return isNaN(n) || n <= 0
            }
            if (validador === "entero_positivo") {
                const n = parseInt(v, 10)
                return isNaN(n) || n <= 0 || String(n) !== v
            }
            if (validador === "entero_no_negativo") {
                const n = parseInt(v, 10)
                return isNaN(n) || n < 0 || String(n) !== v
            }
            return false
        }

        AppText {
            text: etiqueta; font.pixelSize: UiTokens.fontSizeBase
            color: habilitado ? (campoTextoRoot._tieneError ? tema.peligro : tema.texto) : tema.textoMuted
            Layout.fillWidth: true; wrapMode: Text.WordWrap
            Behavior on color { ColorAnimation { duration: 150 } }
        }

        AppText {
            visible: descripcion !== ""
            text: descripcion; font.pixelSize: UiTokens.fontSizeSm
            color: habilitado ? tema.textoMuted : Qt.rgba(tema.textoMuted.r, tema.textoMuted.g, tema.textoMuted.b, 0.5)
            Layout.fillWidth: true; wrapMode: Text.WordWrap
        }

        TextField {
            id: tfCampo
            objectName: campoTextoRoot.objectName === "" ? "" : campoTextoRoot.objectName + "_input"
            Layout.fillWidth: true; Layout.minimumWidth: 0
            implicitHeight: 40
            text: draftObj[clave] || ""
            enabled: habilitado
            onTextChanged: {
                if (String(draftObj[clave] || "") === text) return
                if (campoTextoRoot.scope === "basica") {
                    setBasicaValue(clave, text)
                } else if (campoTextoRoot.scope === "avanzada") {
                    setAvanzadaValue(clave, text)
                } else {
                    setDraftValue(draftObj, clave, text)
                }
            }
            selectByMouse: true; clip: true
            color: campoTextoRoot._tieneError ? tema.peligro : tema.texto
            opacity: habilitado ? 1.0 : 0.55
            font.family: raiz.fuenteUi
            font.pixelSize: UiTokens.fontSizeBase

            Behavior on color { ColorAnimation { duration: 150 } }
            Behavior on opacity { NumberAnimation { duration: 180 } }

            background: Rectangle {
                id: tfBg
                radius: UiTokens.radiusSm
                color: {
                    if (!habilitado) return tema.superficieAlt
                    if (tfCampo.activeFocus) return Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.08)
                    if (tfHov.containsMouse) return Qt.rgba(tema.superficieAlt.r, tema.superficieAlt.g, tema.superficieAlt.b, 0.7)
                    return tema.fondoElevado
                }
                border.width: tfCampo.activeFocus ? 1.5 : 1
                border.color: {
                    if (campoTextoRoot._tieneError) return tema.peligro
                    if (!habilitado) return Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.45)
                    if (tfCampo.activeFocus) return tema.acento
                    return tema.borde
                }
                Behavior on color { ColorAnimation { duration: 150 } }
                Behavior on border.color { ColorAnimation { duration: 150 } }
            }

            MouseArea {
                id: tfHov
                anchors.fill: parent
                hoverEnabled: true; acceptedButtons: Qt.NoButton
                cursorShape: habilitado ? Qt.IBeamCursor : Qt.ArrowCursor
            }
        }

        AppText {
            visible: campoTextoRoot._tieneError && habilitado
            text: {
                if (validador === "score") return "⚠ Valor entre 0.0 y 1.0"
                if (validador === "positivo") return "⚠ Debe ser un número mayor que 0"
                if (validador === "entero_positivo") return "⚠ Solo enteros positivos (≥ 1)"
                if (validador === "entero_no_negativo") return "⚠ Solo enteros no negativos (≥ 0)"
                return "⚠ Valor inválido"
            }
            font.pixelSize: UiTokens.fontSizeSm; color: tema.peligro
        }
    }

    component CampoTextoPassword: ColumnLayout {
        id: campoPass
        objectName: clave === "" ? "" : "config_password_" + clave
        property string etiqueta: ""
        property string descripcion: ""
        property string clave: ""
        property var draftObj: ({})
        property bool mostrar: false
        property bool habilitado: true
        property string scope: "avanzada"

        Layout.fillWidth: true
        spacing: UiTokens.spacing4

        AppText {
            text: etiqueta; font.pixelSize: UiTokens.fontSizeBase
            color: tema.texto
            Layout.fillWidth: true; wrapMode: Text.WordWrap
        }

        AppText {
            visible: descripcion !== ""
            text: descripcion; font.pixelSize: UiTokens.fontSizeSm
            color: tema.textoMuted
            Layout.fillWidth: true; wrapMode: Text.WordWrap
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: UiTokens.spacing8

            TextField {
                id: passField
                objectName: campoPass.objectName === "" ? "" : campoPass.objectName + "_input"
                Layout.fillWidth: true; Layout.minimumWidth: 0
                implicitHeight: 40
                text: draftObj[clave] || ""
                enabled: habilitado
                onTextChanged: {
                    if (String(draftObj[clave] || "") === text) return
                    if (campoPass.scope === "basica") {
                        setBasicaValue(clave, text)
                    } else if (campoPass.scope === "avanzada") {
                        setAvanzadaValue(clave, text)
                    } else {
                        setDraftValue(draftObj, clave, text)
                    }
                }
                echoMode: campoPass.mostrar ? TextInput.Normal : TextInput.Password
                selectByMouse: true; clip: true
                color: tema.texto; font.family: raiz.fuenteUi; font.pixelSize: UiTokens.fontSizeBase
                opacity: habilitado ? 1.0 : 0.55
                Behavior on opacity { NumberAnimation { duration: 180 } }

                background: Rectangle {
                    id: passBg
                    radius: UiTokens.radiusSm
                    color: {
                        if (!habilitado) return tema.superficieAlt
                        if (passField.activeFocus) return Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.08)
                        if (passHov.containsMouse) return Qt.rgba(tema.superficieAlt.r, tema.superficieAlt.g, tema.superficieAlt.b, 0.7)
                        return tema.fondoElevado
                    }
                    border.width: passField.activeFocus ? 1.5 : 1
                    border.color: {
                        if (!habilitado) return Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.45)
                        if (passField.activeFocus) return tema.acento
                        return tema.borde
                    }
                    Behavior on color { ColorAnimation { duration: 150 } }
                    Behavior on border.color { ColorAnimation { duration: 150 } }
                }

                MouseArea {
                    id: passHov
                    anchors.fill: parent
                    hoverEnabled: true; acceptedButtons: Qt.NoButton
                    cursorShape: habilitado ? Qt.IBeamCursor : Qt.ArrowCursor
                }
            }

            Rectangle {
                objectName: campoPass.objectName === "" ? "" : campoPass.objectName + "_reveal"
                width: 40; height: 40; radius: UiTokens.radiusSm
                color: eyeArea.containsMouse && habilitado
                    ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.12)
                    : tema.superficieAlt
                border.color: eyeArea.containsMouse && habilitado ? tema.acento : tema.borde
                border.width: 1
                opacity: habilitado ? 1.0 : 0.35
                Behavior on color { ColorAnimation { duration: 150 } }
                Behavior on border.color { ColorAnimation { duration: 150 } }

                Image {
                    id: eyeIcon
                    anchors.centerIn: parent
                    width: 18; height: 18
                    source: campoPass.mostrar ? "../assets/icons/eye-off.svg" : "../assets/icons/eye.svg"
                    smooth: true; visible: false
                }

                ColorOverlay {
                    anchors.fill: eyeIcon
                    source: eyeIcon
                    color: tema.texto
                    opacity: habilitado ? 0.9 : 0.6
                    visible: GraphicsInfo.api !== GraphicsInfo.Software
                    Behavior on color { ColorAnimation { duration: 150 } }
                }

                MouseArea {
                    id: eyeArea; anchors.fill: parent
                    enabled: habilitado; hoverEnabled: true
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: campoPass.mostrar = !campoPass.mostrar
                }
            }
        }
    }

    component ToggleCampo: Rectangle {
        id: toggleCampoRoot
        property string label: ""
        property bool checkedValue: false
        property bool habilitado: true
        signal changedValue(bool value)
        
        Layout.fillWidth: true
        implicitHeight: Math.max(48, togLayoutRow.implicitHeight + 16)
        radius: UiTokens.radiusMd
        color: checkedValue
            ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.10)
            : (togMa.containsMouse && habilitado ? tema.hover : tema.superficieAlt)
        border.color: checkedValue
            ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.24)
            : (togMa.containsMouse && habilitado ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.15) : tema.borde)
        border.width: 1
        opacity: habilitado ? 1.0 : 0.55

        Behavior on color { ColorAnimation { duration: 150 } }
        Behavior on border.color { ColorAnimation { duration: 150 } }
        Behavior on opacity { NumberAnimation { duration: 180 } }

        RowLayout {
            id: togLayoutRow
            anchors.fill: parent
            anchors.margins: UiTokens.spacing12
            spacing: UiTokens.spacing12
            Switch {
                objectName: toggleCampoRoot.objectName === "" ? "" : toggleCampoRoot.objectName + "_switch"
                checked: checkedValue
                enabled: habilitado
                onToggled: changedValue(checked)
                Layout.alignment: Qt.AlignVCenter
            }
            AppText {
                text: label; color: tema.texto; font.pixelSize: UiTokens.fontSizeBase
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                wrapMode: Text.WordWrap
            }
        }

        MouseArea {
            id: togMa; anchors.fill: parent
            enabled: habilitado
            hoverEnabled: true; acceptedButtons: Qt.NoButton
        }
    }

    component PillOption: Rectangle {
        property string texto: ""
        property bool activo: false
        signal clicked()
        
        implicitWidth: pillText.implicitWidth + 32
        height: 38
        radius: 19
        color: activo ? tema.acento : (pillMa.containsMouse ? tema.hover : tema.superficieAlt)
        border.color: activo ? tema.acento : (pillMa.containsMouse ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.45) : tema.borde)
        border.width: 1

        Behavior on color { ColorAnimation { duration: 180 } }
        Behavior on border.color { ColorAnimation { duration: 180 } }

        AppText {
            id: pillText
            anchors.centerIn: parent
            text: texto
            color: activo ? tema.textoSobreAcento : tema.textoSec
            font.pixelSize: UiTokens.fontSizeBase; font.weight: activo ? Font.DemiBold : Font.Normal
            
            Behavior on color { ColorAnimation { duration: 180 } }
        }

        MouseArea {
            id: pillMa; anchors.fill: parent
            hoverEnabled: true; cursorShape: Qt.PointingHandCursor
            onClicked: parent.clicked()
        }
    }

    // Slider vertical de una banda del ecualizador (dB). Etiqueta de frecuencia
    // debajo y valor en dB arriba. Emite `cambiado(db)` en vivo al arrastrar.
    component EqBandaSlider: Column {
        id: eqb
        property int indice: 0
        property real valor: 0
        property real minimo: -20
        property real maximo: 20
        property string etiqueta: ""
        property bool habilitado: true
        property int rielAlto: 132
        signal cambiado(real db)

        spacing: UiTokens.spacing6
        opacity: habilitado ? 1.0 : 0.4
        readonly property real _rango: maximo - minimo
        readonly property real _ratio: _rango > 0
            ? Math.max(0, Math.min(1, (valor - minimo) / _rango))
            : 0

        AppText {
            anchors.horizontalCenter: parent.horizontalCenter
            text: (eqb.valor > 0 ? "+" : "") + Math.round(eqb.valor)
            font.pixelSize: UiTokens.fontSizeXs
            color: tema.textoMuted
        }

        Item {
            id: hit
            width: 34
            height: eqb.rielAlto
            anchors.horizontalCenter: parent.horizontalCenter

            Rectangle {   // riel
                id: riel
                width: 6
                height: parent.height
                radius: 3
                anchors.horizontalCenter: parent.horizontalCenter
                color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.86)

                Rectangle {   // relleno desde la base
                    anchors.bottom: parent.bottom
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: parent.width
                    radius: parent.radius
                    height: parent.height * eqb._ratio
                    color: tema.acento
                }
            }

            Rectangle {   // tirador
                width: 14; height: 14; radius: 7
                anchors.horizontalCenter: parent.horizontalCenter
                color: tema.texto
                border.color: tema.acento; border.width: 2
                y: (1 - eqb._ratio) * (parent.height - height)
                Behavior on y {
                    enabled: !bandaMa.pressed
                    NumberAnimation { duration: UiTokens.durationFast; easing.type: Easing.OutQuad }
                }
            }

            MouseArea {
                id: bandaMa
                anchors.fill: parent
                enabled: eqb.habilitado
                preventStealing: true
                cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                function setFromY(yy) {
                    var r = 1 - Math.max(0, Math.min(1, yy / height))
                    eqb.cambiado(eqb.minimo + r * eqb._rango)
                }
                onPressed: (mouse) => setFromY(mouse.y)
                onPositionChanged: (mouse) => { if (pressed) setFromY(mouse.y) }
            }
        }

        AppText {
            anchors.horizontalCenter: parent.horizontalCenter
            text: eqb.etiqueta
            font.pixelSize: UiTokens.fontSizeXs
            color: tema.textoMuted
        }
    }

    component BotonPrimario: Rectangle {
        id: botonPrimarioRoot
        property string texto: ""
        property bool deshabilitado: false
        signal clicked()
        width: 220; height: 44
        radius: 22
        color: deshabilitado ? tema.superficie : (bpMa.containsMouse ? tema.acentoFuerte : tema.acento)
        border.color: deshabilitado ? tema.borde : "transparent"
        border.width: deshabilitado ? 1 : 0
        opacity: deshabilitado ? 0.45 : 1.0

        Behavior on color { ColorAnimation { duration: 180 } }
        Behavior on opacity { NumberAnimation { duration: 200 } }
        Behavior on scale { NumberAnimation { duration: 120 } }

        AppText {
            anchors.centerIn: parent
            text: texto
            color: deshabilitado ? tema.textoMuted : tema.fondo
            font.bold: true; font.pixelSize: UiTokens.fontSizeBase
            Behavior on color { ColorAnimation { duration: 180 } }
        }

        MouseArea {
            id: bpMa; anchors.fill: parent
            hoverEnabled: true; enabled: !botonPrimarioRoot.deshabilitado
            cursorShape: botonPrimarioRoot.deshabilitado ? Qt.ArrowCursor : Qt.PointingHandCursor
            onClicked: botonPrimarioRoot.clicked()

            SequentialAnimation {
                id: bpPressAnim
                NumberAnimation { target: botonPrimarioRoot; property: "scale"; to: 0.96; duration: 80 }
                NumberAnimation { target: botonPrimarioRoot; property: "scale"; to: 1.0; duration: 100 }
            }
            onPressed: { if (!botonPrimarioRoot.deshabilitado) bpPressAnim.start() }
        }
    }

    component BotonSecundario: Rectangle {
        id: botonSecundarioRoot
        property string texto: ""
        signal clicked()
        width: 220; height: 44
        radius: 22
        color: bsMa.containsMouse ? tema.hover : tema.superficieAlt
        border.color: bsMa.containsMouse ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.35) : tema.borde
        border.width: 1

        Behavior on color { ColorAnimation { duration: 180 } }
        Behavior on border.color { ColorAnimation { duration: 150 } }
        Behavior on scale { NumberAnimation { duration: 120 } }

        AppText {
            anchors.centerIn: parent; text: texto
            color: tema.texto; font.bold: true; font.pixelSize: UiTokens.fontSizeBase
        }

        MouseArea {
            id: bsMa; anchors.fill: parent
            hoverEnabled: true; cursorShape: Qt.PointingHandCursor
            onClicked: botonSecundarioRoot.clicked()

            SequentialAnimation {
                id: bsPressAnim
                NumberAnimation { target: botonSecundarioRoot; property: "scale"; to: 0.96; duration: 80 }
                NumberAnimation { target: botonSecundarioRoot; property: "scale"; to: 1.0; duration: 100 }
            }
            onPressed: bsPressAnim.start()
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // DIÁLOGOS Y POPUPS
    // ─────────────────────────────────────────────────────────────────────────

    Popup {
        id: popupBasicaInfo
        objectName: "popup_config_estado"
        property string titulo: ""
        property string mensaje: ""
        property bool esError: false
        readonly property int bordeAnchoActual: 1
        readonly property color bordeColorActual: esError ? tema.peligro : Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.48)
        modal: true; focus: true
        parent: raiz
        x: Math.round((raiz.width - width) / 2)
        y: Math.round((raiz.height - height) / 2)
        width: Math.min(720, raiz.width - 40)
        height: infoCol.implicitHeight + 36
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle {
            radius: 12; color: tema.superficie
            border.width: popupBasicaInfo.bordeAnchoActual
            border.color: popupBasicaInfo.bordeColorActual
        }
        contentItem: ColumnLayout {
            id: infoCol
            anchors.fill: parent; anchors.margins: 18
            spacing: UiTokens.spacing10
            AppText { text: popupBasicaInfo.titulo; font.pixelSize: UiTokens.fontSizeXl; font.weight: Font.DemiBold; color: tema.texto }
            AppText {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap; text: popupBasicaInfo.mensaje
                color: tema.textoSec; font.pixelSize: UiTokens.fontSizeBase
            }
            BotonPrimario { texto: "Entendido"; onClicked: popupBasicaInfo.close() }
        }
    }
}
