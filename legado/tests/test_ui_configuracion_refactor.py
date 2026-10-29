import importlib
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

from db.conexion import cerrar_db, inicializar_db


@pytest.fixture()
def db_tmp(tmp_path):
    ruta = tmp_path / "ui_test.db"
    inicializar_db(ruta)
    try:
        yield ruta
    finally:
        cerrar_db()


def _modelo_configuracion():
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloConfiguracion

    return ModeloConfiguracion()


def _modelo_tema(modelo_configuracion):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloTema

    return ModeloTema(modelo_configuracion)


def _recargar_settings():
    import config.settings as settings

    return importlib.reload(settings)


def test_configuracion_db_nueva_carga_env_sin_insertar_filas(db_tmp, tmp_path, monkeypatch):
    from db.conexion import get_conexion

    with monkeypatch.context() as m:
        m.setenv("USER_INPUT_DIR", str(tmp_path / "env_entrada"))
        m.setenv("USER_LIBRARY_DIR", str(tmp_path / "env_biblioteca"))
        m.setenv("ACOUSTID_API_KEY", "env-acoustid")
        m.setenv("ENABLE_SHAZAM", "false")
        m.setenv("NB_SOUND_PROGRESS_MODE", "quiet")
        m.setenv("INIT_COMPONENT_MAX_RETRIES", "6")
        _recargar_settings()

        modelo = _modelo_configuracion()

        assert modelo.obtener("dir_entrada") == str((tmp_path / "env_entrada").resolve())
        assert modelo.obtener("dir_biblioteca") == str((tmp_path / "env_biblioteca").resolve())
        assert modelo.obtener("acoustid_key") == "env-acoustid"
        assert modelo.obtener("enable_shazam") == "0"
        assert modelo.obtener("nb_sound_progress_mode") == "quiet"
        assert modelo.obtener("init_component_max_retries") == "6"

        filas = get_conexion().execute(
            """
            SELECT clave FROM config_ui
            WHERE clave IN (
                'dir_entrada', 'dir_biblioteca', 'acoustid_key',
                'enable_shazam', 'nb_sound_progress_mode',
                'init_component_max_retries'
            )
            """
        ).fetchall()
        assert filas == []

    _recargar_settings()


def test_configuracion_db_existente_gana_sobre_env_incluye_vacios(db_tmp, tmp_path, monkeypatch):
    from db.conexion import guardar_config

    guardar_config("dir_entrada", str(tmp_path / "db_entrada"))
    guardar_config("acoustid_key", "")
    guardar_config("enable_shazam", "1")

    with monkeypatch.context() as m:
        m.setenv("USER_INPUT_DIR", str(tmp_path / "env_entrada"))
        m.setenv("ACOUSTID_API_KEY", "env-acoustid")
        m.setenv("ENABLE_SHAZAM", "false")
        _recargar_settings()

        modelo = _modelo_configuracion()

        assert modelo.obtener("dir_entrada") == str(tmp_path / "db_entrada")
        assert modelo.obtener("acoustid_key") == ""
        assert modelo.obtener("enable_shazam") == "1"

    _recargar_settings()


def test_defaults_basica_usan_env_y_no_persisten(db_tmp, tmp_path, monkeypatch):
    from db.conexion import get_conexion

    with monkeypatch.context() as m:
        m.setenv("USER_INPUT_DIR", str(tmp_path / "default_entrada"))
        m.setenv("ACOUSTID_API_KEY", "default-acoustid")
        m.setenv("ENABLE_ACOUSTID", "false")
        _recargar_settings()

        modelo = _modelo_configuracion()
        defaults = modelo.valores_predeterminados_modulo("basica")

        assert defaults["dir_entrada"] == str((tmp_path / "default_entrada").resolve())
        assert defaults["acoustid_key"] == "default-acoustid"
        assert defaults["enable_acoustid"] == "0"
        filas = get_conexion().execute(
            "SELECT clave FROM config_ui WHERE clave IN ('dir_entrada', 'acoustid_key', 'enable_acoustid')"
        ).fetchall()
        assert filas == []

    _recargar_settings()


def test_defaults_basica_sin_env_usa_recomendadas_y_fallbacks(db_tmp, monkeypatch):
    route_vars = [
        "USER_INPUT_DIR", "USER_LIBRARY_DIR", "USER_QUARANTINE_DIR",
        "USER_REVIEW_DIR", "USER_LOGS_DIR", "USER_PROCESSED_DIR",
        "USER_CACHE_DIR", "USER_TEMP_DIR", "USER_ASSETS_DIR", "USER_MANIFESTS_DIR",
    ]
    with monkeypatch.context() as m:
        for var in route_vars:
            m.setenv(var, "")
        _recargar_settings()

        modelo = _modelo_configuracion()
        defaults = modelo.valores_predeterminados_modulo("basica")
        recomendadas = modelo.rutas_recomendadas()

        assert defaults["dir_entrada"] == recomendadas["dir_entrada"]
        assert defaults["dir_biblioteca"] == recomendadas["dir_biblioteca"]
        assert defaults["dir_cache"] == modelo.fallback_ruta("dir_cache")
        assert defaults["dir_temp"] == modelo.fallback_ruta("dir_temp")
        assert all(str(defaults[clave]).strip() for clave in modelo._RUTAS_KEYS)

    _recargar_settings()


def test_defaults_avanzada_usan_env_settings_y_no_persisten(db_tmp, monkeypatch):
    from db.conexion import get_conexion

    with monkeypatch.context() as m:
        m.setenv("NB_SOUND_PROGRESS_MODE", "quiet")
        m.setenv("INIT_COMPONENT_MAX_RETRIES", "7")
        m.setenv("SIDECAR_FUTURE_TIMEOUT_SEG", "135")
        _recargar_settings()

        modelo = _modelo_configuracion()
        defaults = modelo.valores_predeterminados_modulo("avanzada")

        assert defaults["nb_sound_progress_mode"] == "quiet"
        assert defaults["init_component_max_retries"] == "7"
        assert defaults["sidecar_future_timeout_seg"] == "135.0"
        filas = get_conexion().execute(
            """
            SELECT clave FROM config_ui
            WHERE clave IN ('nb_sound_progress_mode', 'init_component_max_retries', 'sidecar_future_timeout_seg')
            """
        ).fetchall()
        assert filas == []

    _recargar_settings()


def test_guardar_basica_permite_opcionales_vacios_y_aplica_fallback(db_tmp, tmp_path, monkeypatch):
    with monkeypatch.context() as m:
        m.setenv("USER_ASSETS_DIR", str(tmp_path / "assets"))
        m.setenv("USER_CACHE_DIR", str(tmp_path / "cache"))
        m.setenv("USER_TEMP_DIR", str(tmp_path / "temp"))
        m.setenv("USER_MANIFESTS_DIR", str(tmp_path / "manifests"))
        _recargar_settings()

        modelo = _modelo_configuracion()

        data = {
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
        }

        resultado = modelo.guardar_basica(data)

        assert resultado["ok"] is True, resultado.get("mensaje", str(resultado))
        assert modelo.obtener("dir_cache") == modelo.fallback_ruta("dir_cache")
        assert modelo.obtener("dir_temp") == modelo.fallback_ruta("dir_temp")
        assert modelo.obtener("dir_assets") == modelo.fallback_ruta("dir_assets")
        assert modelo.obtener("dir_manifests") == modelo.fallback_ruta("dir_manifests")
        # Sin API key explicita en el payload, AcoustID se persiste como
        # desactivado (validación de coherencia: la app no debería intentar
        # llamar a AcoustID sin clave configurada).
        assert modelo.obtener("enable_acoustid") == "0"
        assert modelo.obtener("enable_shazam") == "1"

    _recargar_settings()


def test_modelo_configuracion_cubre_variables_env_backed():
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloConfiguracion

    settings_src = Path("config/settings.py").read_text(encoding="utf-8")
    env_names = set(re.findall(r'_env_(?:str|bool|int|float)\("([^"]+)"', settings_src))

    assert set(ModeloConfiguracion._ENV_TO_CONFIG_KEY) == env_names
    assert len(set(ModeloConfiguracion._ENV_TO_CONFIG_KEY.values())) == len(env_names)


def test_qml_configuracion_cubre_env_backed_y_enums_sin_desplegables():
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloConfiguracion

    qml = Path("ui/qml/vistas/VistaConfiguracion.qml").read_text(encoding="utf-8")
    faltantes = sorted(
        clave for clave in ModeloConfiguracion._ENV_TO_CONFIG_KEY.values()
        if f'"{clave}"' not in qml
    )

    assert faltantes == []
    assert "ComboBox" not in qml
    assert "ListView" not in qml
    assert "FormCombo" not in qml
    for object_name in [
        "config_ia_proveedor_no",
        "config_ia_proveedor_openai",
        "config_ia_proveedor_anthropic",
        "config_duplicate_policy_replace_if_better",
        "config_duplicate_policy_prefer_new_if_quality_higher",
        "config_nb_sound_progress_mode_auto",
        "config_nb_sound_progress_mode_tty",
        "config_nb_sound_progress_mode_log",
        "config_nb_sound_progress_mode_quiet",
    ]:
        assert object_name in qml


def test_defaults_separan_basica_y_avanzada_sin_duplicar(db_tmp):
    modelo = _modelo_configuracion()

    basica = modelo.valores_predeterminados_modulo("basica")
    avanzada = modelo.valores_predeterminados_modulo("avanzada")

    assert "acoustid_key" in basica
    assert "enable_acoustid" in basica
    assert "enable_shazam" in basica
    assert "enable_ia_tiebreak" not in basica
    assert "acoustid_key" not in avanzada
    assert "enable_acoustid" not in avanzada
    assert "enable_shazam" not in avanzada
    for clave in {
        "init_component_max_retries",
        "init_component_retry_backoff_seg",
        "nb_sound_progress_mode",
        "nb_sound_progress_interval_sec",
        "sidecar_future_timeout_seg",
        "sidecar_wait_heartbeat_seg",
    }:
        assert clave in avanzada


def test_guardar_avanzada_valida_rangos_numericos_estrictos(db_tmp):
    modelo = _modelo_configuracion()

    resultado = modelo.guardar_avanzada({"nb_sound_progress_interval_sec": "0.01"})

    assert resultado["ok"] is False
    assert "nb_sound_progress_interval_sec" in resultado["mensaje"]


def test_guardar_avanzada_persiste_duplicate_policy_soportada(db_tmp):
    modelo = _modelo_configuracion()

    resultado = modelo.guardar_avanzada({"duplicate_policy": "prefer_new_if_quality_higher"})

    assert resultado["ok"] is True
    assert modelo.obtener("duplicate_policy") == "prefer_new_if_quality_higher"


def test_guardar_avanzada_persiste_assets_hd_y_fallbacks_lyrics(db_tmp):
    modelo = _modelo_configuracion()

    resultado = modelo.guardar_avanzada({
        "assets_hd_max_image_bytes": "30000000",
        "lyrics_suggest_limit": "2",
        "lyrics_max_retries": "0",
    })

    assert resultado["ok"] is True
    assert modelo.obtener("assets_hd_max_image_bytes") == "30000000"
    assert modelo.obtener("lyrics_suggest_limit") == "2"
    assert modelo.obtener("lyrics_max_retries") == "0"


def test_guardar_avanzada_persiste_progreso_sidecars_e_inicializacion(db_tmp):
    modelo = _modelo_configuracion()

    resultado = modelo.guardar_avanzada({
        "init_component_max_retries": "4",
        "init_component_retry_backoff_seg": "1.5",
        "nb_sound_progress_mode": "log",
        "nb_sound_progress_interval_sec": "3.25",
        "sidecar_future_timeout_seg": "120",
        "sidecar_wait_heartbeat_seg": "4",
    })

    assert resultado["ok"] is True
    assert modelo.obtener("init_component_max_retries") == "4"
    assert modelo.obtener("init_component_retry_backoff_seg") == "1.50"
    assert modelo.obtener("nb_sound_progress_mode") == "log"
    assert modelo.obtener("nb_sound_progress_interval_sec") == "3.25"
    assert modelo.obtener("sidecar_future_timeout_seg") == "120.00"
    assert modelo.obtener("sidecar_wait_heartbeat_seg") == "4.00"


def test_guardar_avanzada_normaliza_ia_invalida_y_apaga_dependientes(db_tmp):
    modelo = _modelo_configuracion()

    resultado = modelo.guardar_avanzada({
        "enable_ia_tiebreak": "1",
        "enable_ia_discography": "1",
        "ia_proveedor": "OpenAI",
        "openai_key": "",
    })

    assert resultado["ok"] is True
    assert resultado["ia_normalizada"] is True
    assert modelo.obtener("enable_ia_tiebreak") == "0"
    assert modelo.obtener("enable_ia_discography") == "0"
    assert modelo.obtener("ia_proveedor") == "No"


def test_guardar_avanzada_normaliza_ia_sin_proveedor_o_anthropic_sin_key(db_tmp):
    modelo = _modelo_configuracion()

    sin_proveedor = modelo.guardar_avanzada({
        "enable_ia_tiebreak": "1",
        "enable_ia_discography": "1",
        "ia_proveedor": "No",
    })
    assert sin_proveedor["ok"] is True
    assert sin_proveedor["ia_normalizada"] is True
    assert modelo.obtener("enable_ia_tiebreak") == "0"
    assert modelo.obtener("enable_ia_discography") == "0"

    anthropic_sin_key = modelo.guardar_avanzada({
        "enable_ia_tiebreak": "1",
        "enable_ia_discography": "1",
        "ia_proveedor": "Anthropic",
        "anthropic_key": "",
    })
    assert anthropic_sin_key["ok"] is True
    assert anthropic_sin_key["ia_normalizada"] is True
    assert modelo.obtener("ia_proveedor") == "No"


def test_guardar_avanzada_mantiene_ia_con_proveedor_y_key_validos(db_tmp):
    modelo = _modelo_configuracion()

    resultado = modelo.guardar_avanzada({
        "enable_ia_tiebreak": "1",
        "enable_ia_discography": "1",
        "ia_proveedor": "OpenAI",
        "openai_key": "sk-test",
    })

    assert resultado["ok"] is True
    assert resultado["ia_normalizada"] is False
    assert modelo.obtener("enable_ia_tiebreak") == "1"
    assert modelo.obtener("enable_ia_discography") == "1"
    assert modelo.obtener("ia_proveedor") == "OpenAI"
    assert modelo.obtener("openai_key") == "sk-test"


def test_temas_predefinidos_son_63_completos_y_con_previews_curados(db_tmp):
    modelo = _modelo_configuracion()
    tema = _modelo_tema(modelo)
    from ui.modelos_qml import ModeloTema

    temas = ModeloTema._TEMAS
    nuevos = {
        "obsidiana_neon", "hielo_oled", "blanco_editorial", "oro_negro",
        "jade_nocturno", "plasma_morado", "amanecer_sintetico",
        "tinta_marina", "frambuesa_dark", "cielo_coral", "violeta_laser",
        "acero_azul", "rosa_polar", "circuito_verde", "ultra_violeta",
        "marfil_grafito", "noche_arcade", "neon_citrico",
    }
    nombres_obligatorios = {
        "Negro Puro (OLED)", "Sangre de Dragón", "Nieve", "Menta Fresh",
        "Obsidiana Neón", "Hielo OLED", "Blanco Editorial", "Neón Cítrico",
    }

    assert len(temas) == 63
    assert nuevos.issubset(temas)
    assert len({data["nombre"] for data in temas.values()}) == len(temas)
    assert nombres_obligatorios.issubset({data["nombre"] for data in temas.values()})
    assert temas["crepusculo_violeta"]["acento"].lower() == "#d77dff"
    for tema_id, data in temas.items():
        assert set(ModeloTema._CLAVES_COLOR).issubset(data), tema_id
        for clave in ModeloTema._CLAVES_COLOR:
            assert re.fullmatch(r"#[0-9a-fA-F]{6}", data[clave]), (tema_id, clave, data[clave])

    disponibles = tema.temas_disponibles
    assert len([t for t in disponibles if t["id"] != "custom"]) == 63
    assert any(t["id"] == "custom" for t in disponibles)
    for preview in disponibles:
        assert set(ModeloTema._CLAVES_COLOR).issubset(preview), preview["id"]


def test_tema_guardado_invalido_vuelve_a_negro_puro(db_tmp):
    from db.conexion import guardar_config

    guardar_config("tema", "tema_inexistente")
    modelo = _modelo_configuracion()
    tema = _modelo_tema(modelo)

    assert tema.property("tema_id") == "negro_puro"


def test_fuentes_disponibles_salen_de_qfontdatabase_y_se_aplican_globalmente(db_tmp, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication([])
    modelo = _modelo_configuracion()
    fuentes = list(modelo.fuentes_disponibles)
    fuente = "DejaVu Sans" if "DejaVu Sans" in fuentes else fuentes[0]
    nombres_invalidos = (
        "AR PL", "UKai", "UMing", "C059", "D050", "Emoji", "Ding",
        "Symbol", "Fallback", "Noto Sans Adlam", "Noto Sans Arabic",
    )

    resultado = modelo.guardar_personalizacion({
        "ui_font_family": fuente,
        "ui_scale": "150",
        "ui_mode": "pro",
    })

    assert resultado["ok"] is True
    assert fuentes
    assert len(fuentes) <= 40
    assert not any(any(fragmento in f for fragmento in nombres_invalidos) for f in fuentes)
    assert all(re.fullmatch(r"[A-Za-z0-9À-ÿ .,+_\-/()[\]&']+", f) for f in fuentes)
    assert modelo.obtener("ui_font_family") == fuente
    assert modelo.obtener("ui_scale") == "150"
    assert modelo.obtener("ui_mode") == "pro"
    assert app.font().family() == fuente


def test_importacion_aplica_ajustes_avanzados_de_ui():
    from servicios.importacion import ServicioImportacion

    cfg = SimpleNamespace(
        ENABLE_ASSETS_PIPELINE=True,
        ASSETS_HD_MAX_IMAGE_BYTES=0,
        ENABLE_LYRICS_OVH=False,
        LYRICS_SUGGEST_LIMIT=0,
        LYRICS_RETRY_BACKOFF_SEG=0.0,
        INIT_COMPONENT_MAX_RETRIES=0,
        INIT_COMPONENT_RETRY_BACKOFF_SEG=0.0,
        NB_SOUND_PROGRESS_MODE="auto",
        NB_SOUND_PROGRESS_INTERVAL_SEC=2.0,
        SIDECAR_FUTURE_TIMEOUT_SEG=90.0,
        SIDECAR_WAIT_HEARTBEAT_SEG=2.0,
    )

    ServicioImportacion._aplicar_ajustes_avanzados(cfg, {
        "enable_assets_pipeline": "0",
        "assets_hd_max_image_bytes": "30000000",
        "enable_lyrics_ovh": "1",
        "lyrics_suggest_limit": "2",
        "lyrics_retry_backoff_seg": "1.25",
        "init_component_max_retries": "4",
        "init_component_retry_backoff_seg": "1.5",
        "nb_sound_progress_mode": "log",
        "nb_sound_progress_interval_sec": "3.25",
        "sidecar_future_timeout_seg": "120",
        "sidecar_wait_heartbeat_seg": "4",
    })

    assert cfg.ENABLE_ASSETS_PIPELINE is False
    assert cfg.ASSETS_HD_MAX_IMAGE_BYTES == 30000000
    assert cfg.ENABLE_LYRICS_OVH is True
    assert cfg.LYRICS_SUGGEST_LIMIT == 2
    assert cfg.LYRICS_RETRY_BACKOFF_SEG == 1.25
    assert cfg.INIT_COMPONENT_MAX_RETRIES == 4
    assert cfg.INIT_COMPONENT_RETRY_BACKOFF_SEG == 1.5
    assert cfg.NB_SOUND_PROGRESS_MODE == "log"
    assert cfg.NB_SOUND_PROGRESS_INTERVAL_SEC == 3.25
    assert cfg.SIDECAR_FUTURE_TIMEOUT_SEG == 120.0
    assert cfg.SIDECAR_WAIT_HEARTBEAT_SEG == 4.0


def test_qml_incluye_precision_mode_y_dependencias_ia():
    qml = Path("ui/qml/vistas/VistaConfiguracion.qml").read_text(encoding="utf-8")

    assert '"precision_mode"' in qml
    assert '"conservador"' in qml
    assert '"equilibrado"' in qml
    assert '"flexible"' in qml
    assert 'clave: "acoustid_key"; draftObj: basicaDraft' in qml
    assert 'clave: "acoustid_key"; draftObj: avanzadaDraft' not in qml
    assert 'basicaDraft["enable_ia_tiebreak"]' not in qml
    assert 'enabled: avanzadaDraft["enable_ia_tiebreak"] === "1"' in qml


def test_qml_configuracion_no_repite_basica_en_avanzada_y_gatea_pro():
    qml = Path("ui/qml/vistas/VistaConfiguracion.qml").read_text(encoding="utf-8")

    assert 'visible: esPro && seccion_activa === "avanzada"' in qml
    assert 'objectName: "tab_config_avanzada"; visible: esPro; Layout.fillWidth: visible; texto: "Avanzada"' in qml
    assert 'checkedValue: { _avanzadaRev; return avanzadaDraft["enable_acoustid"] === "1" }' not in qml
    assert 'checkedValue: { _avanzadaRev; return avanzadaDraft["enable_shazam"] === "1" }' not in qml


def test_qml_personalizacion_no_contiene_nombre_y_defaults_no_guardan():
    qml = Path("ui/qml/vistas/VistaConfiguracion.qml").read_text(encoding="utf-8")

    assert "Nombre de usuario" not in qml
    assert "nombre_usuario" not in qml
    assert "placeholderText" not in qml
    assert "popupConfirmDefaultsBasica" not in qml
    assert "guardará inmediatamente" not in qml


def test_qml_refuerzo_responsive_para_tabs_y_campos_largos():
    qml = Path("ui/qml/vistas/VistaConfiguracion.qml").read_text(encoding="utf-8")

    assert "Layout.maximumWidth: contentMaxWidth" in qml
    assert "Layout.minimumWidth: 0" in qml
    assert "clip: true" in qml
    assert "wrapMode: Text.WordWrap" in qml


def test_qml_personalizacion_ofrece_todas_las_escalas_soportadas():
    qml = Path("ui/qml/vistas/VistaConfiguracion.qml").read_text(encoding="utf-8")

    assert 'readonly property var scaleOptions: ["100", "125", "150", "175", "200"]' in qml


def test_qml_configuracion_expone_object_names_para_runtime():
    qml = Path("ui/qml/vistas/VistaConfiguracion.qml").read_text(encoding="utf-8")

    for object_name in [
        "vista_configuracion",
        "tab_config_basica",
        "tab_config_avanzada",
        "tab_config_personalizacion",
        "config_personalizacion",
        "config_personalizacion_fuentes",
        "config_personalizacion_escala",
        "config_personalizacion_temas",
        "popup_config_estado",
    ]:
        assert object_name in qml

    assert 'objectPrefix: "basica"' in qml
    assert 'objectPrefix: "avanzada"' in qml
    assert 'objectName: objectPrefix + "_defaults_button"' in qml
    assert 'objectName: objectPrefix + "_guardar_button"' in qml
    assert "Valores predeterminados cargados" in qml
    assert "Pulsa Guardar configuración para persistirlos" in qml


def test_qml_validacion_avanzada_incluye_progreso_y_sidecars():
    qml = Path("ui/qml/vistas/VistaConfiguracion.qml").read_text(encoding="utf-8")

    for modo in ["auto", "tty", "log", "quiet"]:
        assert f'"config_nb_sound_progress_mode_{modo}"' in qml
    assert '"init_component_max_retries"' in qml
    assert '"sidecar_future_timeout_seg"' in qml
    assert '"sidecar_wait_heartbeat_seg"' in qml


def test_qml_principal_sanea_escala_invalida():
    qml = Path("ui/qml/Principal.qml").read_text(encoding="utf-8")

    assert "function _resolver_escala_ui()" in qml
    assert "if (isNaN(escalaGuardada) || escalaGuardada <= 0)" in qml
    assert "ventana_principal.escala_ui = _resolver_escala_ui()" in qml


def test_qml_importacion_envia_ajustes_avanzados_pipeline():
    qml = Path("ui/qml/vistas/VistaImportacion.qml").read_text(encoding="utf-8")

    assert "function _ajustesAvanzadosPipeline()" in qml
    assert '"assets_hd_max_image_bytes": _cfgValor("assets_hd_max_image_bytes", "25000000")' in qml
    assert '"lyrics_suggest_limit": _cfgValor("lyrics_suggest_limit", "3")' in qml
    assert '"init_component_max_retries": _cfgValor("init_component_max_retries", "2")' in qml
    assert '"nb_sound_progress_mode": _cfgValor("nb_sound_progress_mode", "auto")' in qml
    assert '"sidecar_future_timeout_seg": _cfgValor("sidecar_future_timeout_seg", "90.0")' in qml
    assert '"ajustes_avanzados": _ajustesAvanzadosPipeline()' in qml


def test_qml_importacion_eta_normaliza_segundos_redondeados():
    qml = Path("ui/qml/vistas/VistaImportacion.qml").read_text(encoding="utf-8")

    assert "var totalSeg = Math.max(1, Math.round(segundos))" in qml
    assert "var seg = totalSeg % 60" in qml


def test_qml_avanzada_valida_incluye_assets_negative_cache_ttl():
    """avanzadaValida() debe validar assets_negative_cache_ttl_seg para que el botón guardar
    quede bloqueado antes de llegar al backend, donde mínimo es 60."""
    qml = Path("ui/qml/vistas/VistaConfiguracion.qml").read_text(encoding="utf-8")
    assert 'esNumeroValido(d["assets_negative_cache_ttl_seg"]' in qml, (
        "assets_negative_cache_ttl_seg no está validado en avanzadaValida() — "
        "el botón guardar queda habilitado con valores inválidos"
    )


def test_qml_importacion_auto_refresh_en_visible_changed():
    """La vista de importación debe refrescar diagnóstico y estado deep al hacerse visible."""
    qml = Path("ui/qml/vistas/VistaImportacion.qml").read_text(encoding="utf-8")
    assert "onVisibleChanged" in qml
    assert "refrescarDiagnosticoImportacion" in qml
    assert "refrescarAudioDeepEstado" in qml
    assert "if (!visible) return" in qml
