from PySide6.QtCore import QObject, Signal

from ui.modelos_qml import ModeloBusqueda


class _FakeWorker(QObject):
    resultados = Signal(dict)
    finished = Signal()
    instances = []

    def __init__(self, termino, parent=None):
        super().__init__(parent)
        self.termino = termino
        self._running = False
        self._interrupted = False
        _FakeWorker.instances.append(self)

    def isRunning(self):
        return self._running

    def requestInterruption(self):
        self._interrupted = True

    def wait(self, _ms):
        self._running = False
        return True

    def start(self):
        self._running = True

    def emit_result(self, payload):
        self.resultados.emit(payload)
        self._running = False
        self.finished.emit()


def test_busqueda_ignora_resultados_stale(monkeypatch):
    import workers.workers_qt as workers_qt

    _FakeWorker.instances = []
    monkeypatch.setattr(workers_qt, "WorkerBusqueda", _FakeWorker)

    modelo = ModeloBusqueda()

    eventos_buscando = []
    modelo.buscando.connect(lambda valor: eventos_buscando.append(valor))

    modelo.buscar("ab")
    worker_1 = _FakeWorker.instances[-1]

    modelo.buscar("abc")
    worker_2 = _FakeWorker.instances[-1]

    worker_2.emit_result(
        {
            "pistas": [{"id": 2, "titulo": "vigente"}],
            "albums": [],
            "artistas": [],
        }
    )
    worker_1.emit_result(
        {
            "pistas": [{"id": 1, "titulo": "stale"}],
            "albums": [],
            "artistas": [],
        }
    )

    assert modelo.pistas.obtener(0)["id"] == 2
    assert eventos_buscando[-1] is False


def test_busqueda_corta_apaga_estado_buscando(monkeypatch):
    import workers.workers_qt as workers_qt

    _FakeWorker.instances = []
    monkeypatch.setattr(workers_qt, "WorkerBusqueda", _FakeWorker)

    modelo = ModeloBusqueda()
    eventos_buscando = []
    modelo.buscando.connect(lambda valor: eventos_buscando.append(valor))

    modelo.buscar("ab")
    modelo.buscar("")

    assert modelo.pistas.total == 0
    assert eventos_buscando[-1] is False


def test_busqueda_un_caracter_crea_worker(monkeypatch):
    import workers.workers_qt as workers_qt

    _FakeWorker.instances = []
    monkeypatch.setattr(workers_qt, "WorkerBusqueda", _FakeWorker)

    modelo = ModeloBusqueda()
    eventos_buscando = []
    modelo.buscando.connect(lambda valor: eventos_buscando.append(valor))

    modelo.buscar("X")

    assert _FakeWorker.instances[-1].termino == "X"
    assert eventos_buscando[-1] is True


def test_busqueda_puntuacion_crea_worker(monkeypatch):
    import workers.workers_qt as workers_qt

    _FakeWorker.instances = []
    monkeypatch.setattr(workers_qt, "WorkerBusqueda", _FakeWorker)

    modelo = ModeloBusqueda()

    modelo.buscar(":")

    assert _FakeWorker.instances[-1].termino == ":"
