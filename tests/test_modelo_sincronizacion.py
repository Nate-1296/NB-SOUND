# =============================================================================
# tests/test_modelo_sincronizacion.py
#
# BLOQUE 4.1 (+ 2.3 / 3.4 puente Qt) del plan de ecosistema movil.
#   - Encender el servidor desde el modelo expone un QR no vacio con
#     host/puerto/token y el modelo queda `activo`.
#   - Revocar un dispositivo lo saca de la lista.
#   - El puente de comandos WS -> reproductor aplica el comando en el hilo Qt.
#   - cerrar() detiene el servidor sin dejar hilos.
# =============================================================================

import json
import threading
import time

import pytest

from db.conexion import cerrar_db, inicializar_db
from servicios import sync_repositorio

pytest.importorskip("aiohttp")
pytest.importorskip("qrcode")
from PySide6.QtGui import QGuiApplication  # noqa: E402

from ui.modelos_qml import ModeloSincronizacion  # noqa: E402


@pytest.fixture()
def app():
    return QGuiApplication.instance() or QGuiApplication([])


@pytest.fixture()
def db_sync(tmp_path):
    inicializar_db(tmp_path / "modelo_sync.sqlite3")
    try:
        yield tmp_path
    finally:
        cerrar_db()


def _esperar(app, condicion, timeout=8.0):
    fin = time.time() + timeout
    while time.time() < fin:
        app.processEvents()
        if condicion():
            return True
        time.sleep(0.02)
    app.processEvents()
    return condicion()


class _ReproductorFake:
    """Doble mínimo del ModeloReproductor para el puente de control."""

    def __init__(self):
        self.acciones = []
        # Refleja el estado de DJ Privado en el snapshot WS (dj_activo).
        self.modo_dj_activo = False

    # El modelo se conecta a estas señales si existen; aquí no hace falta.
    def pausar_reanudar(self):
        self.acciones.append("pausar_reanudar")

    def siguiente(self):
        self.acciones.append("siguiente")

    def anterior(self):
        self.acciones.append("anterior")

    def set_volumen(self, v):
        self.acciones.append(("set_volumen", v))

    # Comandos nuevos de Connect (karaoke + manipulación de cola espejada).
    def alternar_karaoke(self):
        self.acciones.append("alternar_karaoke")

    def reproducir_cola_desde_pistas(self, datos, indice):
        self.acciones.append(("set_queue", [d["id"] for d in datos], indice))

    def mover_en_cola(self, desde, hasta):
        self.acciones.append(("mover_en_cola", desde, hasta))

    def quitar_de_cola(self, indice):
        self.acciones.append(("quitar_de_cola", indice))

    def vaciar_cola_mantener_actual(self):
        self.acciones.append("vaciar_cola_mantener_actual")


def test_encender_expone_qr_con_host_puerto_token(app, db_sync):
    modelo = ModeloSincronizacion(parent=None)
    # Forzar loopback para que el bind sea determinista en CI.
    modelo._crear_servidor = _patch_loopback(modelo)
    try:
        modelo.encender()
        assert _esperar(app, lambda: modelo.activo and not modelo.ocupado)
        assert modelo.activo is True
        assert modelo.host
        assert modelo.puerto > 0
        # QR generado como file URL.
        assert _esperar(app, lambda: modelo.qrImagen != "")
        assert modelo.qrImagen.startswith("file://")
        assert modelo.qrImagen.endswith(".png")
        # El payload del QR del servidor lleva host/puerto/token.
        payload = modelo._servidor.payload_qr()
        assert payload["host"] == modelo.host
        assert payload["puerto"] == modelo.puerto
        assert payload["token"]
    finally:
        modelo.cerrar()


def test_revocar_saca_dispositivo_de_la_lista(app, db_sync):
    disp = sync_repositorio.registrar_dispositivo("Pixel", "android")
    modelo = ModeloSincronizacion(parent=None)
    try:
        modelo.recargarDispositivos()
        assert any(d["id"] == disp["id"] for d in modelo.dispositivos)
        modelo.revocar(disp["id"])
        assert all(d["id"] != disp["id"] for d in modelo.dispositivos)
    finally:
        modelo.cerrar()


def test_puente_comando_ws_aplica_en_reproductor(app, db_sync):
    rep = _ReproductorFake()
    modelo = ModeloSincronizacion(rep, parent=None)
    try:
        # Simula el callback que el servidor invoca desde su hilo (esquema móvil).
        ack = modelo._comando_control_thread_safe({"tipo": "comando", "accion": "play_pause"})
        assert ack["ok"] is True
        # El comando se entrega en cola: procesar eventos para aplicarlo.
        assert _esperar(app, lambda: "pausar_reanudar" in rep.acciones, timeout=3.0)
    finally:
        modelo.cerrar()


def test_puente_comandos_cola_karaoke(app, db_sync, monkeypatch):
    """Los comandos nuevos de Connect (karaoke + cola espejada) se traducen a
    llamadas del reproductor."""
    rep = _ReproductorFake()
    modelo = ModeloSincronizacion(rep, parent=None)

    # set_queue resuelve ids vía obtener_pista: se simula la biblioteca.
    import servicios.biblioteca as bib
    monkeypatch.setattr(
        bib, "obtener_pista", lambda pid: {"id": pid, "titulo": f"T{pid}"}
    )

    try:
        def enviar(msg):
            modelo._comando_control_thread_safe(msg)

        enviar({"tipo": "comando", "accion": "karaoke"})
        enviar({"tipo": "comando", "accion": "set_queue", "ids": [3, 1, 2], "indice": 1})
        enviar({"tipo": "comando", "accion": "move_queue", "desde": 0, "hasta": 2})
        enviar({"tipo": "comando", "accion": "remove_queue", "indice": 1})
        enviar({"tipo": "comando", "accion": "clear_queue"})

        assert _esperar(
            app,
            lambda: "vaciar_cola_mantener_actual" in rep.acciones,
            timeout=3.0,
        )
        assert "alternar_karaoke" in rep.acciones
        assert ("set_queue", [3, 1, 2], 1) in rep.acciones
        assert ("mover_en_cola", 0, 2) in rep.acciones
        assert ("quitar_de_cola", 1) in rep.acciones
    finally:
        modelo.cerrar()


def test_presencia_dispositivos_conectados_por_ventana(app, db_sync):
    """dispositivos_conectados_ids incluye los tocados recientemente y excluye los
    inactivos; el modelo marca `conectado` en cada dispositivo."""
    from db.conexion import ejecutar

    reciente = sync_repositorio.registrar_dispositivo("Reciente", "android")
    viejo = sync_repositorio.registrar_dispositivo("Viejo", "android")

    # El reciente tocó el servidor hace nada; el viejo hace 10 minutos.
    sync_repositorio.tocar_dispositivo(reciente["id"])
    ejecutar(
        "UPDATE sync_dispositivos SET ultima_conexion = ? WHERE id = ?",
        ("2000-01-01T00:00:00.000000Z", viejo["id"]),
    )

    ids = sync_repositorio.dispositivos_conectados_ids()
    assert reciente["id"] in ids
    assert viejo["id"] not in ids

    # El modelo refleja la bandera `conectado` en la lista de dispositivos.
    modelo = ModeloSincronizacion(parent=None)
    try:
        modelo._recargar_dispositivos(emitir=False)
        por_id = {d["id"]: d for d in modelo.dispositivos}
        assert por_id[reciente["id"]]["conectado"] is True
        assert por_id[viejo["id"]]["conectado"] is False
    finally:
        modelo.cerrar()


def test_snapshot_estado_incluye_dj_activo(app, db_sync):
    """El frame de estado WS expone dj_activo desde modo_dj_activo del reproductor."""
    rep = _ReproductorFake()
    modelo = ModeloSincronizacion(rep, parent=None)
    try:
        snap = modelo._construir_snapshot()
        assert snap["dj_activo"] is False
        rep.modo_dj_activo = True
        snap2 = modelo._construir_snapshot()
        assert snap2["dj_activo"] is True
    finally:
        modelo.cerrar()


def test_bridge_backup_crear_y_restaurar(app, tmp_path, monkeypatch):
    from db.conexion import get_conexion, inicializar_db, cerrar_db
    from config import settings

    # Aislar los assets a un directorio temporal vacío para no recorrer la
    # carpeta real del usuario durante el test.
    assets_tmp = tmp_path / "assets_vacios"
    assets_tmp.mkdir()
    monkeypatch.setattr(settings, "DEFAULT_ASSETS_DIR", assets_tmp, raising=False)

    inicializar_db(tmp_path / "bridge_backup.sqlite3")
    get_conexion().execute(
        "INSERT INTO pistas(titulo, artista_nombre, album_titulo, ruta_archivo, nombre_archivo) "
        "VALUES ('Bridge', 'A', 'B', '/m/x.mp3', 'x.mp3')"
    )
    modelo = ModeloSincronizacion(parent=None)
    resultados = []
    modelo.backupTerminado.connect(lambda ok, msg, ruta: resultados.append((ok, ruta)))
    try:
        carpeta = tmp_path / "backups"
        carpeta.mkdir()
        modelo.crearBackup(str(carpeta))
        assert _esperar(app, lambda: len(resultados) == 1, timeout=8.0)
        ok, ruta = resultados[0]
        assert ok is True
        assert ruta.endswith(".nbsound-backup")

        # Restaurar el backup recién creado sobre la BD activa.
        modelo.restaurarBackup(ruta)
        assert _esperar(app, lambda: len(resultados) == 2, timeout=8.0)
        assert resultados[1][0] is True
        fila = get_conexion().execute("SELECT titulo FROM pistas").fetchone()
        assert fila["titulo"] == "Bridge"
    finally:
        modelo.cerrar()
        cerrar_db()


def test_backup_programado_config_persiste_y_dispara_primera_copia(app, tmp_path, monkeypatch):
    """#8b: fijar carpeta + frecuencia persiste en config_ui y, como nunca se
    había respaldado, dispara la primera copia automática enseguida; un segundo
    chequeo dentro del plazo no crea otra."""
    from db.conexion import get_conexion, inicializar_db, cerrar_db, obtener_config
    from config import settings
    from PySide6.QtCore import QUrl

    assets_tmp = tmp_path / "assets_vacios"
    assets_tmp.mkdir()
    monkeypatch.setattr(settings, "DEFAULT_ASSETS_DIR", assets_tmp, raising=False)

    inicializar_db(tmp_path / "auto_backup.sqlite3")
    get_conexion().execute(
        "INSERT INTO pistas(titulo, artista_nombre, album_titulo, ruta_archivo, nombre_archivo) "
        "VALUES ('Auto', 'A', 'B', '/m/a.mp3', 'a.mp3')"
    )
    modelo = ModeloSincronizacion(parent=None)
    resultados = []
    modelo.backupTerminado.connect(lambda ok, msg, ruta: resultados.append((ok, ruta)))
    try:
        carpeta = tmp_path / "auto_backups"
        carpeta.mkdir()

        # Fijar la carpeta primero (frecuencia aún 0 → no respalda todavía).
        modelo.setBackupCarpeta(QUrl.fromLocalFile(str(carpeta)).toString())
        assert modelo.backupCarpeta == str(carpeta)
        assert obtener_config("backup_carpeta", "") == str(carpeta)
        app.processEvents()
        assert len(resultados) == 0

        # Activar una frecuencia: sin copia previa → vence → respalda ya.
        modelo.setBackupFrecuenciaDias(7)
        assert modelo.backupFrecuenciaDias == 7
        assert obtener_config("backup_frecuencia_dias", "") == "7"

        assert _esperar(app, lambda: len(resultados) >= 1, timeout=8.0)
        assert resultados[0][0] is True
        assert list(carpeta.glob("*.nbsound-backup"))

        # backup_ultimo quedó registrado (lo muestra la UI) y no re-dispara.
        assert _esperar(app, lambda: modelo.backupUltimo != "", timeout=3.0)
        assert obtener_config("backup_ultimo", "") != ""

        # Segundo chequeo dentro del plazo: no debe crear otra copia.
        assert _esperar(app, lambda: modelo._backup_hilo is None, timeout=5.0)
        modelo.verificarBackupProgramado()
        app.processEvents()
        assert len(resultados) == 1
    finally:
        modelo.cerrar()
        cerrar_db()


def test_backup_programado_desactivado_no_respalda(app, tmp_path, monkeypatch):
    """Con frecuencia 0 (Desactivado) nunca se crea una copia automática,
    aunque haya carpeta y no exista marca previa."""
    from db.conexion import inicializar_db, cerrar_db
    from config import settings
    from PySide6.QtCore import QUrl

    assets_tmp = tmp_path / "assets_vacios2"
    assets_tmp.mkdir()
    monkeypatch.setattr(settings, "DEFAULT_ASSETS_DIR", assets_tmp, raising=False)

    inicializar_db(tmp_path / "auto_off.sqlite3")
    modelo = ModeloSincronizacion(parent=None)
    resultados = []
    modelo.backupTerminado.connect(lambda ok, msg, ruta: resultados.append(ok))
    try:
        carpeta = tmp_path / "off_backups"
        carpeta.mkdir()
        modelo.setBackupCarpeta(QUrl.fromLocalFile(str(carpeta)).toString())
        # Frecuencia 0 explícita.
        modelo.setBackupFrecuenciaDias(0)
        modelo.verificarBackupProgramado()
        app.processEvents()
        assert len(resultados) == 0
        assert not list(carpeta.glob("*.nbsound-backup"))
    finally:
        modelo.cerrar()
        cerrar_db()


def test_cerrar_detiene_servidor_sin_hilos(app, db_sync):
    modelo = ModeloSincronizacion(parent=None)
    modelo._crear_servidor = _patch_loopback(modelo)
    modelo.encender()
    assert _esperar(app, lambda: modelo.activo and not modelo.ocupado)
    modelo.cerrar()
    # El hilo del servidor debe haber terminado.
    for _ in range(40):
        if not any(t.name == "nb-sound-sync-server" for t in threading.enumerate()):
            break
        app.processEvents()
        time.sleep(0.05)
    assert not any(t.name == "nb-sound-sync-server" for t in threading.enumerate())


def _patch_loopback(modelo):
    """Devuelve un _crear_servidor que fuerza host=127.0.0.1 y sin mDNS."""
    def _crear():
        from servicios.servidor_sync import ServidorSync

        return ServidorSync(
            comando_control=modelo._comando_control_thread_safe,
            estado_provider=lambda: modelo._estado_snapshot,
            on_dispositivo_emparejado=modelo._on_dispositivo_emparejado,
            nombre_servicio="NB Sound",
            host="127.0.0.1",
            anunciar_mdns=False,
            tls=False,
        )

    return _crear


# ─── Issue: toggle "encender al abrir la app" ────────────────────────────────

def test_auto_encender_persiste_entre_modelos(app, db_sync):
    """El ajuste de auto-encendido se guarda al instante y un modelo nuevo
    (siguiente arranque) lo recuerda."""
    modelo = ModeloSincronizacion(parent=None)
    try:
        assert modelo.autoEncender is False  # por defecto, apagado
        modelo.setAutoEncender(True)
        assert modelo.autoEncender is True
        # Un modelo nuevo (simula el siguiente arranque) lee el valor persistido.
        modelo2 = ModeloSincronizacion(parent=None)
        try:
            assert modelo2.autoEncender is True
        finally:
            modelo2.cerrar()
    finally:
        modelo.cerrar()


def test_auto_encender_apagado_no_arranca_servidor(app, db_sync):
    """Con el toggle apagado, autoEncenderSiCorresponde es un no-op seguro."""
    modelo = ModeloSincronizacion(parent=None)
    try:
        modelo.setAutoEncender(False)
        modelo.autoEncenderSiCorresponde()
        assert modelo.activo is False
        assert modelo.ocupado is False
    finally:
        modelo.cerrar()
