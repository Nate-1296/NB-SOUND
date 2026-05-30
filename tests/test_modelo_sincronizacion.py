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

    # El modelo se conecta a estas señales si existen; aquí no hace falta.
    def pausar_reanudar(self):
        self.acciones.append("pausar_reanudar")

    def siguiente(self):
        self.acciones.append("siguiente")

    def anterior(self):
        self.acciones.append("anterior")

    def set_volumen(self, v):
        self.acciones.append(("set_volumen", v))


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
