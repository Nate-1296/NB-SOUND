"""F4.1.2 y F4.1.6: graba lo que decide la V1 (normalizer.py y matcher.py) en casos
inventados, para que la prueba de Rust compare decisión a decisión.

Herramienta de desarrollo (ver check-sin-python). Desde `legado/`:

    .venv/bin/python ../scripts/prototipos/emparejador/grabar.py

Escribe `src-tauri/tests/fixtures/emparejador_v1.json`. Sin red y sin IA.
"""

import itertools
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from core import matcher, normalizer  # noqa: E402
from domain.models import (  # noqa: E402
    ArchivoAudio, CandidatoMB, MetadataCruda, ResultadoAcoustID, ResultadoShazam,
)

random.seed(7)
TITULOS = ["Clavado en un bar", "Despacito (feat. Daddy Yankee)", "Song (Remix)", "Hello (Official Video)",
           "La Bachata", "Tití Me Preguntó", "Live Forever (Live)", "Yesterday (2019 Remaster)", "", "Track"]
ARTISTAS = ["Maná", "Luis Fonsi", "Drake feat. Future", "Adele", "Manuel Turizo", "Bad Bunny", "Oasis", "The Beatles", ""]
ALBUMES = ["Sueños líquidos", "Vida", "", "25", "Un Verano Sin Ti", "Help!"]
TIPOS = ["Album", "Single", "EP", "Compilation", "Live", "", "Other"]


def candidato(i, cruda):
    parecido = random.random() < 0.7
    t = (cruda["titulo"] if parecido and cruda["titulo"] else random.choice(TITULOS)) or "Algo"
    a = (cruda["artista"] if parecido and cruda["artista"] else random.choice(ARTISTAS)) or "Alguien"
    tipo = random.choice(TIPOS)
    sec = random.choice([[], [], ["Compilation"], ["Live"], ["Remix"]])
    estado = random.choice(["Official", "Official", "Official", "Promotion", "Bootleg", ""])
    return {
        "recording_id": f"r{i}", "release_id": f"l{i}", "titulo_oficial": t.replace(" (feat. Daddy Yankee)", ""),
        "artista_principal": a.split(" feat.")[0], "artistas_credito": [a.split(" feat.")[0]],
        "album_oficial": (cruda["album"] if parecido and cruda["album"] and random.random() < 0.7 else random.choice(ALBUMES)), "track_number": random.choice([None, 1, 3, 4]),
        "anio_release": random.choice([None, 1997, 2017, 2018]),
        "duracion_seg": random.choice([None, 300.0, 228.5, 210.0, 330.0]),
        "isrc": random.choice([None, None, "USUM71700001"]), "tipo_release": tipo,
        "tipos_secundarios": sec, "status_release": estado, "es_oficial": estado == "Official",
        "es_compilacion": "Compilation" in sec,
        "penalizaciones": [f"tipo_secundario:{s}" for s in sec if s in {"Live", "Remix", "Compilation"}],
        "procedencia_acoustid": random.random() < 0.2,
    }


def caso(k):
    cruda = {
        "titulo": random.choice(TITULOS) or None, "artista": random.choice(ARTISTAS) or None,
        "album": random.choice(ALBUMES) or None, "numero": random.choice([None, "3", "3/12", "x"]),
        "anio": random.choice([None, "1997", "2017-05-01"]),
    }
    shazam = None
    if random.random() < 0.3:
        shazam = {"titulo": random.choice(TITULOS), "artista": random.choice(ARTISTAS) or "Adele",
                  "isrc": random.choice([None, "us-um7-17-00001"]), "album": random.choice([None, "Vida"]),
                  "anio": random.choice([None, 2019])}
    acoustid = None
    if random.random() < 0.3:
        acoustid = {"grabaciones": ["r1"], "confianzas": [random.choice([0.62, 0.8, 0.95])]}
    return {
        "cruda": cruda, "duracion": random.choice([300.0, 228.0, 200.0]),
        "nombre": random.choice(["Maná - 03 - Clavado en un bar.mp3", "track.mp3", "01 Hello.mp3", "x.mp3"]),
        "shazam": shazam, "acoustid": acoustid,
        "candidatos": [candidato(f"{k}-{i}", cruda) for i in range(random.randint(0, 4))],
    }


def resolver(c):
    a = ArchivoAudio(ruta_original=Path("/no/" + c["nombre"]))
    m = MetadataCruda()
    m.titulo, m.artista, m.album = c["cruda"]["titulo"], c["cruda"]["artista"], c["cruda"]["album"]
    m.track_number, m.anio, m.duracion_seg = c["cruda"]["numero"], c["cruda"]["anio"], c["duracion"]
    a.metadata_cruda = m
    if c["shazam"]:
        s = c["shazam"]
        a.resultado_shazam = ResultadoShazam(titulo=s["titulo"], artista=s["artista"], isrc=s["isrc"],
                                             album=s["album"], anio=s["anio"], disponible=True, identificado=True)
    if c["acoustid"]:
        a.resultado_acoustid = ResultadoAcoustID(recording_ids=c["acoustid"]["grabaciones"],
                                                 scores=c["acoustid"]["confianzas"], disponible=True)
    ok, causa = normalizer.normalizar_metadata(a)
    n = a.metadata_norm
    salida = {"normalizada": None if n is None else {
        "titulo": n.titulo, "titulo_para_match": n.titulo_para_match, "artista": n.artista_principal,
        "artista_para_match": n.artista_para_match, "featuring": n.featuring, "album": n.album,
        "numero": n.track_number, "anio": n.anio, "isrc": n.isrc, "confianza": round(n.confianza_identificacion, 6),
        "fuente_titulo": n.fuente_titulo.value, "fuente_artista": n.fuente_artista.value},
        "ok": ok, "causa_normalizacion": causa.value if causa else None}
    if ok:
        cands = [CandidatoMB(**d) for d in c["candidatos"]]
        d = matcher.evaluar_candidatos(a, cands, None)
        salida["decision"] = {
            "tipo": d.tipo.value,
            "causa": (d.causa_revision or d.causa_cuarentena).value if (d.causa_revision or d.causa_cuarentena) else None,
            "puntaje": round(d.puntaje_maximo, 6),
            "elegido": d.candidato_elegido.recording_id if d.candidato_elegido else None,
        }
    return salida


def main():
    casos = [caso(k) for k in range(400)]
    for c in casos:
        c["v1"] = resolver(c)
    destino = Path.cwd().parent / "src-tauri" / "tests" / "fixtures" / "emparejador_v1.json"
    destino.write_text(json.dumps({"origen": "NB Sound v1.1.16 (core/normalizer.py, core/matcher.py)", "casos": casos},
                                  ensure_ascii=False, indent=2) + "\n")
    print(f"{len(casos)} casos en {destino}")


if __name__ == "__main__":
    main()
