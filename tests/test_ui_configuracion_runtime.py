import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from db.conexion import cerrar_db, get_conexion, guardar_config, inicializar_db, obtener_config


_PERSISTENT_QML_RUNTIMES = []


def _recargar_settings():
    import config.settings as settings

    return importlib.reload(settings)


def _to_dict(value):
    if hasattr(value, "toVariant"):
        value = value.toVariant()
    return dict(value or {})


def _walk(obj, vistos=None):
    if vistos is None:
        vistos = set()
    marcador = id(obj)
    if marcador in vistos:
        return
    vistos.add(marcador)
    yield obj
    for child in obj.children():
        yield from _walk(child, vistos)
    if hasattr(obj, "childItems"):
        for child in obj.childItems():
            yield from _walk(child, vistos)


def _find(root, object_name: str):
    from PySide6.QtCore import QObject

    found = root.findChild(QObject, object_name)
    if found is not None:
        return found
    for obj in _walk(root):
        if obj.objectName() == object_name:
            return obj
    return None


def _wait(app, ms=120):
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    app.processEvents()


def _wait_until(app, condition, timeout_ms=2500, step_ms=50):
    elapsed = 0
    while elapsed <= timeout_ms:
        value = condition()
        if value:
            return value
        _wait(app, step_ms)
        elapsed += step_ms
    raise AssertionError("La condición QML no se cumplió a tiempo")


def _centro_item(runtime, item):
    from PySide6.QtCore import QPoint

    punto_global = item.mapToGlobal(
        float(item.property("width")) / 2.0,
        float(item.property("height")) / 2.0,
    )
    return runtime.root.mapFromGlobal(QPoint(round(punto_global.x()), round(punto_global.y())))


def _click_item(runtime, item):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    QTest.mouseClick(runtime.root, Qt.LeftButton, Qt.NoModifier, _centro_item(runtime, item))
    _wait(runtime.app, 180)


def _key_text(runtime, item, text):
    _click_item(runtime, item)
    item.setProperty("text", "")
    _wait(runtime.app, 80)
    item.setProperty("text", text)
    _wait(runtime.app, 180)


def _flickable_config(vista):
    scroll = _find(vista, "config_scroll")
    assert scroll is not None
    for obj in _walk(scroll):
        if "Flickable" in obj.metaObject().className() and obj.property("contentY") is not None:
            return obj
    raise AssertionError("No se encontró el Flickable interno de configuración")


def _ensure_visible(runtime, vista, item, target_y=360):
    flickable = _flickable_config(vista)
    for _ in range(4):
        punto = _centro_item(runtime, item)
        if 80 <= punto.y() <= runtime.root.property("height") - 160:
            return
        content_y = float(flickable.property("contentY") or 0)
        nuevo_y = max(0.0, content_y + punto.y() - target_y)
        flickable.setProperty("contentY", nuevo_y)
        _wait(runtime.app, 220)


def _image_color_buckets(image):
    assert not image.isNull()
    step_x = max(1, image.width() // 48)
    step_y = max(1, image.height() // 48)
    buckets = set()
    for x in range(0, image.width(), step_x):
        for y in range(0, image.height(), step_y):
            color = image.pixelColor(x, y)
            buckets.add((color.red() // 24, color.green() // 24, color.blue() // 24, color.alpha() // 24))
    return buckets


def _capturar_ventana(runtime):
    screen = runtime.app.primaryScreen()
    assert screen is not None
    pixmap = screen.grabWindow(int(runtime.root.winId()))
    image = pixmap.toImage()
    assert not image.isNull()
    return image


@pytest.fixture()
def qml_factory(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("QML_DISABLE_DISK_CACHE", "1")
    monkeypatch.setenv("QSG_RHI_BACKEND", "software")
    monkeypatch.setenv("USER_INPUT_DIR", str(tmp_path / "input"))
    monkeypatch.setenv("USER_LIBRARY_DIR", str(tmp_path / "library"))
    monkeypatch.setenv("USER_QUARANTINE_DIR", str(tmp_path / "quarantine"))
    monkeypatch.setenv("USER_REVIEW_DIR", str(tmp_path / "review"))
    monkeypatch.setenv("USER_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("USER_PROCESSED_DIR", str(tmp_path / "processed"))
    monkeypatch.setenv("USER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("USER_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("USER_ASSETS_DIR", str(tmp_path / "assets"))
    monkeypatch.setenv("USER_MANIFESTS_DIR", str(tmp_path / "manifests"))

    _recargar_settings()

    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtCore import QUrl
    import main_ui as main_ui_mod

    runtimes = []

    def _factory(nombre_db="config_runtime.db", *, pro=False, width=1280, height=800):
        for runtime in runtimes:
            runtime.root.setProperty("visible", False)
        cerrar_db()
        db_path = tmp_path / nombre_db
        inicializar_db(db_path)
        guardar_config("ui_mode", "pro" if pro else "simple")

        app = QGuiApplication.instance() or QGuiApplication([])
        engine = QQmlApplicationEngine()
        modelos = main_ui_mod.construir_modelos(app)
        modelos["configuracion"].guardar("ui_mode", "pro" if pro else "simple")
        main_ui_mod.exponer_modelos(engine, modelos)
        engine.addImportPath(str((Path("ui") / "qml").resolve()))
        engine.addImportPath(str((Path("ui") / "qml" / "componentes").resolve()))
        engine.addImportPath(str((Path("ui") / "qml" / "vistas").resolve()))
        engine.load(QUrl.fromLocalFile(str(main_ui_mod.ARCHIVO_QML.resolve())))
        assert engine.rootObjects(), "Principal.qml no cargó objetos raíz"

        root = engine.rootObjects()[0]
        root.setProperty("width", width)
        root.setProperty("height", height)
        _wait(app, 250)

        runtime = SimpleNamespace(app=app, engine=engine, modelos=modelos, root=root, db_path=db_path)
        runtimes.append(runtime)
        return runtime

    yield _factory

    for runtime in runtimes:
        runtime.root.setProperty("visible", False)
    _PERSISTENT_QML_RUNTIMES.extend(runtimes)
    cerrar_db()


def _abrir_configuracion(runtime):
    runtime.root.setProperty("vista_activa", "configuracion")
    esperado_pro = runtime.modelos["configuracion"].obtener("ui_mode") == "pro"

    def _vista_correcta():
        candidatos = []
        encontrado = _find(runtime.root, "vista_configuracion")
        if encontrado is not None:
            candidatos.append(encontrado)
        for obj in _walk(runtime.root):
            if obj.objectName() == "vista_configuracion" and obj not in candidatos:
                candidatos.append(obj)
        for candidato in candidatos:
            if bool(candidato.property("esPro")) == esperado_pro:
                return candidato
        return None

    return _wait_until(runtime.app, _vista_correcta)


def _abrir_importacion(runtime):
    runtime.root.setProperty("vista_activa", "importacion")
    esperado_pro = runtime.modelos["configuracion"].obtener("ui_mode") == "pro"

    def _vista_correcta():
        candidatos = []
        encontrado = _find(runtime.root, "vista_importacion")
        if encontrado is not None:
            candidatos.append(encontrado)
        for obj in _walk(runtime.root):
            if obj.objectName() == "vista_importacion" and obj not in candidatos:
                candidatos.append(obj)
        for candidato in candidatos:
            if bool(candidato.property("es_pro")) == esperado_pro:
                return candidato
        return None

    return _wait_until(runtime.app, _vista_correcta)


def test_qml_configuracion_modos_tabs_y_screenshots_no_vacios(qml_factory):
    runtime = qml_factory("simple_tabs.db")
    vista = _abrir_configuracion(runtime)

    assert vista.property("objectName") == "vista_configuracion"
    assert vista.property("esPro") is False
    assert _find(vista, "tab_config_basica").property("visible") is True
    assert _find(vista, "tab_config_personalizacion").property("visible") is True

    image = _capturar_ventana(runtime)
    assert image.width() >= 900
    assert image.height() >= 600
    assert len(_image_color_buckets(image)) >= 8

    runtime.root.setProperty("width", 900)
    runtime.root.setProperty("height", 600)
    _wait(runtime.app, 180)
    small = _capturar_ventana(runtime)
    assert small.width() >= 900
    assert small.height() >= 600
    assert len(_image_color_buckets(small)) >= 8

    runtime_pro = qml_factory("pro_tabs.db", pro=True)
    vista_pro = _abrir_configuracion(runtime_pro)
    assert vista_pro.property("esPro") is True
    assert _find(vista_pro, "tab_config_avanzada").property("visible") is True


def test_qml_cambio_a_simple_oculta_avanzada_y_vuelve_a_basica(qml_factory):
    runtime = qml_factory("config_toggle_mode.db", pro=True)
    vista = _abrir_configuracion(runtime)

    vista.setProperty("seccion_activa", "avanzada")
    _wait(runtime.app, 180)

    tab_avanzada = _find(vista, "tab_config_avanzada")
    assert vista.property("esPro") is True
    assert tab_avanzada is not None
    assert tab_avanzada.property("visible") is True

    runtime.modelos["configuracion"].guardar("ui_mode", "simple")

    _wait_until(
        runtime.app,
        lambda: vista.property("esPro") is False and vista.property("seccion_activa") == "basica",
    )

    assert _find(vista, "tab_config_avanzada").property("visible") is False
    assert _find(vista, "tab_config_basica").property("visible") is True
    assert _find(vista, "tab_config_personalizacion").property("visible") is True


def test_qml_importacion_simple_y_pro_screenshots_no_vacios(qml_factory):
    runtime = qml_factory("import_simple_visual.db", width=1180, height=760)
    vista = _abrir_importacion(runtime)

    assert vista.property("es_pro") is False
    assert _find(vista, "importacion_ruta_entrada_readonly") is not None
    image = _capturar_ventana(runtime)
    assert image.width() >= 900
    assert image.height() >= 600
    assert len(_image_color_buckets(image)) >= 8

    runtime_pro = qml_factory("import_pro_visual.db", pro=True, width=1280, height=800)
    vista_pro = _abrir_importacion(runtime_pro)

    assert vista_pro.property("es_pro") is True
    assert _find(vista_pro, "import_tab_importar") is not None
    for indice in (0, 1, 2):
        vista_pro.setProperty("seccion_activa", indice)
        _wait(runtime_pro.app, 180)
        image = _capturar_ventana(runtime_pro)
        assert image.width() >= 900
        assert image.height() >= 600
        assert len(_image_color_buckets(image)) >= 8

    assert _find(vista_pro, "filtros_revision_categoria") is not None
    assert _find(vista_pro, "filtros_revision_causa") is not None


def test_qml_importacion_no_emite_bindings_criticos_de_audio_deep(qml_factory):
    qtcore = pytest.importorskip("PySide6.QtCore")
    mensajes = []
    anterior = qtcore.qInstallMessageHandler(None)

    def handler(_mode, context, message):
        text = str(message)
        source = str(getattr(context, "file", "") or "")
        if "VistaImportacion.qml" in source or "VistaImportacion.qml" in text:
            if "audioDeep" in text or "Cannot call method" in text or "Cannot read property" in text:
                mensajes.append(text)

    qtcore.qInstallMessageHandler(handler)
    try:
        runtime = qml_factory("import_audio_deep_bindings.db", pro=True, width=1280, height=800)
        vista = _abrir_importacion(runtime)
        assert _find(vista, "importacion_audio_deep_panel") is not None
        assert _find(vista, "importacion_recovery_panel") is not None
        _wait(runtime.app, 250)
    finally:
        qtcore.qInstallMessageHandler(anterior)

    assert mensajes == []


def test_qml_defaults_basica_env_popup_y_db_sin_cambios(qml_factory, tmp_path, monkeypatch):
    with monkeypatch.context() as m:
        m.setenv("USER_INPUT_DIR", str(tmp_path / "env_entrada_qml"))
        m.setenv("ACOUSTID_API_KEY", "qml-acoustid")
        _recargar_settings()

        runtime = qml_factory("defaults_basica.db")
        vista = _abrir_configuracion(runtime)

        assert vista.metaObject().invokeMethod(vista, "defaultsBasica")
        _wait(runtime.app, 180)

        draft = _to_dict(vista.property("basicaDraft"))
        popup = _find(vista, "popup_config_estado")

        assert draft["dir_entrada"] == str((tmp_path / "env_entrada_qml").resolve())
        assert draft["acoustid_key"] == "qml-acoustid"
        assert popup.property("visible") is True
        assert popup.property("titulo") == "Valores predeterminados cargados"
        assert "Guardar configuración" in popup.property("mensaje")
        assert popup.property("bordeAnchoActual") == 1
        assert get_conexion().execute(
            "SELECT 1 FROM config_ui WHERE clave IN ('dir_entrada', 'acoustid_key')"
        ).fetchall() == []
        assert popup.property("width") <= runtime.root.property("width")
        assert popup.property("height") <= runtime.root.property("height")
        assert abs((float(popup.property("x")) + float(popup.property("width")) / 2) - float(vista.property("width")) / 2) <= 1.5
        assert abs((float(popup.property("y")) + float(popup.property("height")) / 2) - float(vista.property("height")) / 2) <= 1.5

    _recargar_settings()


def test_qml_guardar_basica_persiste_valido_y_error_no_persiste_parcial(qml_factory, tmp_path):
    runtime_error = qml_factory("basica_error.db")
    vista_error = _abrir_configuracion(runtime_error)
    draft_error = _to_dict(vista_error.property("basicaDraft"))
    draft_error["dir_entrada"] = ""
    vista_error.setProperty("basicaDraft", draft_error)

    assert vista_error.metaObject().invokeMethod(vista_error, "saveBasica")
    _wait(runtime_error.app, 180)

    popup_error = _find(vista_error, "popup_config_estado")
    assert popup_error.property("visible") is True
    assert popup_error.property("esError") is True
    assert popup_error.property("bordeAnchoActual") == 1
    assert get_conexion().execute(
        "SELECT 1 FROM config_ui WHERE clave IN ('dir_entrada', 'dir_biblioteca', 'acoustid_key')"
    ).fetchall() == []

    payload = _to_dict(vista_error.property("basicaDraft"))
    payload.update({
        "dir_entrada": str(tmp_path / "entrada"),
        "dir_biblioteca": str(tmp_path / "biblioteca"),
        "dir_revision": str(tmp_path / "revision"),
        "dir_cuarentena": str(tmp_path / "cuarentena"),
        "dir_logs": str(tmp_path / "logs"),
        "dir_procesados": str(tmp_path / "procesados"),
        "dir_assets": "",
        "dir_cache": "",
        "dir_temp": "",
        "dir_manifests": "",
        "enable_acoustid": "1",
        "acoustid_key": "persisted-acoustid",
        "enable_shazam": "0",
        "precision_mode": "conservador",
    })
    vista_error.setProperty("basicaDraft", payload)

    assert vista_error.metaObject().invokeMethod(vista_error, "saveBasica")
    _wait(runtime_error.app, 220)

    popup_ok = _find(vista_error, "popup_config_estado")
    assert popup_ok.property("visible") is True
    assert popup_ok.property("esError") is False
    assert popup_ok.property("bordeAnchoActual") == 1
    assert obtener_config("dir_entrada") == str((tmp_path / "entrada").resolve())
    assert obtener_config("acoustid_key") == "persisted-acoustid"
    assert obtener_config("enable_shazam") == "0"
    assert obtener_config("score_accept") == "0.88"


def test_qml_avanzada_defaults_pro_no_persisten_hasta_guardar(qml_factory, monkeypatch):
    with monkeypatch.context() as m:
        m.setenv("INIT_COMPONENT_MAX_RETRIES", "7")
        m.setenv("NB_SOUND_PROGRESS_MODE", "quiet")
        _recargar_settings()

        runtime = qml_factory("avanzada_defaults.db", pro=True)
        vista = _abrir_configuracion(runtime)
        vista.setProperty("seccion_activa", "avanzada")
        _wait(runtime.app, 120)

        assert vista.metaObject().invokeMethod(vista, "defaultsAvanzada")
        _wait(runtime.app, 180)

        draft = _to_dict(vista.property("avanzadaDraft"))
        popup = _find(vista, "popup_config_estado")
        assert draft["init_component_max_retries"] == "7"
        assert draft["nb_sound_progress_mode"] == "quiet"
        assert popup.property("visible") is True
        assert get_conexion().execute(
            "SELECT 1 FROM config_ui WHERE clave IN ('init_component_max_retries', 'nb_sound_progress_mode')"
        ).fetchall() == []

        assert vista.metaObject().invokeMethod(vista, "saveAvanzada")
        _wait(runtime.app, 180)
        assert obtener_config("init_component_max_retries") == "7"
        assert obtener_config("nb_sound_progress_mode") == "quiet"

    _recargar_settings()


def test_qml_personalizacion_tema_fuente_y_escala_en_vivo(qml_factory):
    runtime = qml_factory("personalizacion_live.db")
    vista = _abrir_configuracion(runtime)
    vista.setProperty("seccion_activa", "personalizacion")
    _wait(runtime.app, 120)

    configuracion = runtime.modelos["configuracion"]
    tema = runtime.modelos["temaUi"]
    fuente = "DejaVu Sans" if "DejaVu Sans" in configuracion.fuentes_disponibles else configuracion.fuentes_disponibles[0]
    assert "AR PL" not in " ".join(configuracion.fuentes_disponibles)
    configuracion.guardar("ui_font_family", fuente)

    scale_150 = _find(vista, "config_escala_150")
    assert scale_150 is not None
    _ensure_visible(runtime, vista, scale_150)
    _click_item(runtime, scale_150)
    tema.aplicar_tema("titanio")
    # La propagación click -> ModeloConfiguracion -> escala_ui pasa por la cola
    # de eventos Qt; una espera fija es frágil (este test era flaky en
    # aislamiento por timing del event loop offscreen). Poll hasta que el
    # binding se aplique en vez de asumir un retardo concreto.
    _wait_until(
        runtime.app,
        lambda: runtime.root.property("escala_ui") == pytest.approx(1.5),
    )

    assert runtime.root.property("fuente_ui") == fuente
    assert runtime.root.property("escala_ui") == pytest.approx(1.5)
    assert tema.property("tema_id") == "titanio"
    assert obtener_config("ui_font_family") == fuente
    assert obtener_config("ui_scale") == "150"
    assert obtener_config("tema") == "titanio"
    assert _find(vista, "config_personalizacion_fuentes") is not None
    assert _find(vista, "config_personalizacion_escala") is not None
    assert _find(vista, "config_personalizacion_temas") is not None
    assert len([t for t in tema.temas_disponibles if t["id"] != "custom"]) == 60
    assert any(t["id"] == "obsidiana_neon" for t in tema.temas_disponibles)
    assert len(_image_color_buckets(_capturar_ventana(runtime))) >= 8


def test_qml_avanzada_ia_invalida_guarda_y_se_desactiva_en_vivo(qml_factory):
    runtime = qml_factory("avanzada_ia_invalida.db", pro=True)
    vista = _abrir_configuracion(runtime)
    vista.setProperty("seccion_activa", "avanzada")
    _wait(runtime.app, 160)

    draft = _to_dict(vista.property("avanzadaDraft"))
    draft.update({
        "enable_ia_tiebreak": "0",
        "enable_ia_discography": "1",
        "ia_proveedor": "No",
        "openai_key": "",
        "anthropic_key": "",
    })
    vista.setProperty("avanzadaDraft", draft)
    vista.setProperty("_avanzadaRev", int(vista.property("_avanzadaRev")) + 1)
    _wait(runtime.app, 180)

    switch = _find(vista, "config_ia_tiebreak_toggle_switch")
    assert switch is not None
    _ensure_visible(runtime, vista, switch)
    _click_item(runtime, switch)
    assert _to_dict(vista.property("avanzadaDraft"))["enable_ia_tiebreak"] == "1"

    openai = _find(vista, "config_ia_proveedor_openai")
    anthropic = _find(vista, "config_ia_proveedor_anthropic")
    ninguno = _find(vista, "config_ia_proveedor_no")
    assert openai is not None and anthropic is not None and ninguno is not None
    _ensure_visible(runtime, vista, openai)
    _click_item(runtime, openai)
    assert _to_dict(vista.property("avanzadaDraft"))["ia_proveedor"] == "OpenAI"
    assert openai.property("activo") is True
    assert _find(vista, "config_openai_key").property("visible") is True

    _click_item(runtime, anthropic)
    assert _to_dict(vista.property("avanzadaDraft"))["ia_proveedor"] == "Anthropic"
    assert anthropic.property("activo") is True
    assert _find(vista, "config_anthropic_key").property("visible") is True

    _click_item(runtime, ninguno)
    assert _to_dict(vista.property("avanzadaDraft"))["ia_proveedor"] == "No"
    assert _find(vista, "config_openai_key").property("visible") is False
    assert _find(vista, "config_anthropic_key").property("visible") is False

    _click_item(runtime, openai)
    guardar = _find(vista, "avanzada_guardar_button")
    assert guardar is not None
    assert guardar.property("deshabilitado") is False
    assert _find(vista, "config_ia_tiebreak_toggle") is not None
    assert _find(vista, "config_openai_key").property("visible") is True

    _ensure_visible(runtime, vista, guardar, target_y=520)
    _click_item(runtime, guardar)
    _wait(runtime.app, 220)

    popup = _find(vista, "popup_config_estado")
    draft_guardado = _to_dict(vista.property("avanzadaDraft"))
    assert popup.property("visible") is True
    assert popup.property("esError") is False
    assert popup.property("bordeAnchoActual") == 1
    assert "IA quedó desactivada" in popup.property("mensaje")
    assert obtener_config("enable_ia_tiebreak") == "0"
    assert obtener_config("enable_ia_discography") == "0"
    assert obtener_config("ia_proveedor") == "No"
    assert draft_guardado["enable_ia_tiebreak"] == "0"
    assert draft_guardado["enable_ia_discography"] == "0"
    assert draft_guardado["ia_proveedor"] == "No"


def test_qml_avanzada_ia_valida_persiste_sin_normalizar(qml_factory):
    runtime = qml_factory("avanzada_ia_valida.db", pro=True)
    vista = _abrir_configuracion(runtime)
    vista.setProperty("seccion_activa", "avanzada")
    _wait(runtime.app, 160)

    draft = _to_dict(vista.property("avanzadaDraft"))
    draft.update({
        "enable_ia_tiebreak": "1",
        "enable_ia_discography": "1",
        "ia_proveedor": "No",
        "anthropic_key": "",
        "openai_key": "",
    })
    vista.setProperty("avanzadaDraft", draft)
    vista.setProperty("_avanzadaRev", int(vista.property("_avanzadaRev")) + 1)
    _wait(runtime.app, 180)

    anthropic = _find(vista, "config_ia_proveedor_anthropic")
    _ensure_visible(runtime, vista, anthropic)
    _click_item(runtime, anthropic)
    anthropic_input = _find(vista, "config_anthropic_key_input")
    assert anthropic.property("activo") is True
    assert _find(vista, "config_anthropic_key").property("visible") is True
    reveal = _find(vista, "config_anthropic_key_reveal")
    _click_item(runtime, reveal)
    assert _find(vista, "config_anthropic_key").property("mostrar") is True
    _click_item(runtime, reveal)
    assert _find(vista, "config_anthropic_key").property("mostrar") is False
    _key_text(runtime, anthropic_input, "anthropic-test")

    assert _find(vista, "avanzada_guardar_button").property("deshabilitado") is False
    assert _find(vista, "config_anthropic_key").property("visible") is True
    guardar = _find(vista, "avanzada_guardar_button")
    _ensure_visible(runtime, vista, guardar, target_y=520)
    _click_item(runtime, guardar)
    _wait(runtime.app, 220)

    popup = _find(vista, "popup_config_estado")
    assert popup.property("visible") is True
    assert "IA quedó desactivada" not in popup.property("mensaje")
    assert obtener_config("enable_ia_tiebreak") == "1"
    assert obtener_config("ia_proveedor") == "Anthropic"
    assert obtener_config("anthropic_key") == "anthropic-test"


def test_qml_avanzada_numerico_invalido_bloquea_guardar_y_muestra_error(qml_factory):
    runtime = qml_factory("avanzada_numerico_invalido.db", pro=True)
    vista = _abrir_configuracion(runtime)
    vista.setProperty("seccion_activa", "avanzada")
    _wait(runtime.app, 160)

    policy = _find(vista, "config_duplicate_policy_prefer_new_if_quality_higher")
    assert policy is not None
    _ensure_visible(runtime, vista, policy)
    _click_item(runtime, policy)
    assert _to_dict(vista.property("avanzadaDraft"))["duplicate_policy"] == "prefer_new_if_quality_higher"
    assert policy.property("activo") is True

    assert _find(vista, "config_nb_sound_progress_mode") is not None
    quiet = _find(vista, "config_nb_sound_progress_mode_quiet")
    assert quiet is not None
    _ensure_visible(runtime, vista, quiet)
    _click_item(runtime, quiet)
    assert _to_dict(vista.property("avanzadaDraft"))["nb_sound_progress_mode"] == "quiet"

    campo_intervalo = _find(vista, "config_campo_nb_sound_progress_interval_sec_input")
    _ensure_visible(runtime, vista, campo_intervalo)
    _key_text(runtime, campo_intervalo, "0.01")
    assert _to_dict(vista.property("avanzadaDraft"))["nb_sound_progress_interval_sec"] == "0.01"
    assert _find(vista, "avanzada_guardar_button").property("deshabilitado") is True

    assert vista.metaObject().invokeMethod(vista, "saveAvanzada")
    _wait(runtime.app, 180)

    popup = _find(vista, "popup_config_estado")
    assert popup.property("visible") is True
    assert popup.property("esError") is True
    assert popup.property("bordeAnchoActual") == 1
    assert "nb_sound_progress_interval_sec" in popup.property("mensaje")
    assert get_conexion().execute(
        "SELECT 1 FROM config_ui WHERE clave = 'nb_sound_progress_interval_sec'"
    ).fetchall() == []


def test_qml_basica_controles_exponen_object_names_y_fallbacks(qml_factory, tmp_path):
    runtime = qml_factory("basica_controles.db")
    vista = _abrir_configuracion(runtime)

    _flickable_config(vista).setProperty("contentY", 5000)
    _wait(runtime.app, 220)
    assert _find(vista, "basica_defaults_button") is not None
    assert _find(vista, "basica_guardar_button") is not None
    assert _find(vista, "config_acoustid_toggle") is not None
    assert _find(vista, "config_acoustid_toggle_switch") is not None
    assert _find(vista, "config_acoustid_key_input") is not None
    assert _find(vista, "config_acoustid_key_reveal") is not None
    assert _find(vista, "config_shazam_toggle") is not None
    assert _find(vista, "config_ruta_dir_entrada_input") is not None

    payload = _to_dict(vista.property("basicaDraft"))
    payload.update({
        "dir_entrada": str(tmp_path / "entrada"),
        "dir_biblioteca": str(tmp_path / "biblioteca"),
        "dir_revision": str(tmp_path / "revision"),
        "dir_cuarentena": str(tmp_path / "cuarentena"),
        "dir_logs": str(tmp_path / "logs"),
        "dir_procesados": str(tmp_path / "procesados"),
        "dir_assets": "",
        "dir_cache": "",
        "dir_temp": "",
        "dir_manifests": "",
        "enable_acoustid": "0",
        "acoustid_key": "",
        "enable_shazam": "1",
        "precision_mode": "flexible",
    })
    resultado = runtime.modelos["configuracion"].guardar_basica(payload)

    assert resultado["ok"] is True
    assert obtener_config("enable_acoustid") == "0"
    assert obtener_config("enable_shazam") == "1"
    assert obtener_config("score_accept") == "0.76"
    assert obtener_config("dir_cache")
    assert obtener_config("dir_temp")
