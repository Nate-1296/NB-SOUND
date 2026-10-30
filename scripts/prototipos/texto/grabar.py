"""F4.1.2: graba lo que responde `utils/text.py` de la V1 a frases inventadas.

Herramienta de desarrollo (ver check-sin-python). Desde `legado/`:

    .venv/bin/python ../scripts/prototipos/texto/grabar.py [ruta-de-frases]

Sin argumento usa las frases de abajo y escribe `src-tauri/tests/fixtures/texto_v1.json`,
que la prueba de Rust compara función a función. Con un archivo de frases (una por
línea) no escribe nada: imprime el resultado en JSON, para compararlo a mano con un
corpus que no puede entrar en el repositorio.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from utils import text  # noqa: E402

FRASES = [
    "Hello (Official Video)", "Song [spotdown.org]", "Song (www.spotdown.org) - Artist",
    "Yesterday (2019 Remaster)", "Yesterday (2009 Remaster)", "Come Together (2019 Mix)",
    "Hotel California (Remaster)", "Something (feat. Ringo)", "Umbrella (feat. Jay-Z)",
    "Title [ft. Artist]", "Drake feat. Future", "Jay-Z ft. Kanye", "Radiohead",
    "Bad Bunny (feat. Drake)", "Beyoncé - Niño", "Canción número 1", "Песня 夜に駆ける",
    "Cristal & МОЁТ", "Don’t Stop — Believin…", "  hola   x  ", "Mañana, ¡Sí!",
    "Artist - Title.mp3", "Artist - 01 - Title.mp3", "01. Title.mp3", "01_Title [spotdown.org].mp3",
    "2024 - Title.mp3", "Solo.flac", "Song (Remix)", "Song (Live at Wembley)",
    "Song (Acoustic Version)", "Song (feat. A) (Remix)", "Song (Demo)", "Song - Instrumental",
    "Tití Me Preguntó", "Ojitos Lindos (feat. Bomba Estéreo)", "MONACO", "Me Porto Bonito",
    "Song [mp3paw.com] (Lyrics)", "Track [algo.net]", "website.band", "(Live)", "",
    "Ñoño café", "AC/DC", "Guns N' Roses", "P!nk", "Sigur Rós", "Mötley Crüe",
    "Despacito - Remix", "Shape of You (Ed Sheeran Remix) [HD]", "x" * 120,
]
PARES = [
    ("Hotel California", "California Hotel"), ("Hello", "hello"), ("Despacito", "Despasito"),
    ("Bad Bunny", "Bad Bunny feat. Drake"), ("AC/DC", "ACDC"), ("Sigur Rós", "Sigur Ros"),
    ("Tití Me Preguntó", "Titi me pregunto"), ("ab", "ab"), ("The Beatles", "Beatles"),
]


def responder(frases):
    salida = []
    for f in frases:
        nombre = text.parsear_nombre_archivo(f)
        base, variante = text.parsear_variante_titulo(f)
        salida.append({
            "entrada": f,
            "slug": text.construir_slug(f),
            "para_comparacion": text.para_comparacion(f),
            "normalizar_para_comparar": text.normalizar_para_comparar(f),
            "normalizar_titulo": text.normalizar_titulo(f),
            "limpiar_version_titulo": text.limpiar_version_titulo(f),
            "normalizar_artista": text.normalizar_artista(f),
            "separar_artista_principal": list(text.separar_artista_principal(f)),
            "extraer_featuring_del_titulo": list(text.extraer_featuring_del_titulo(f)),
            "nombre_archivo": [nombre["artista"], nombre["titulo"], nombre["track_number"]],
            "variante": [base, variante],
            "limpiar_basura_descarga": text.limpiar_basura_descarga(f),
        })
    return salida


def main():
    if len(sys.argv) > 1:
        frases = Path(sys.argv[1]).read_text().splitlines()
        print(json.dumps(responder(frases), ensure_ascii=False))
        return
    datos = {
        "origen": "NB Sound v1.1.16 (legado/utils/text.py)",
        "frases": responder(FRASES),
        "pares": [{"a": a, "b": b, "combinada": text.similitud_combinada(a, b)} for a, b in PARES],
    }
    destino = Path.cwd().parent / "src-tauri" / "tests" / "fixtures" / "texto_v1.json"
    destino.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(FRASES)} frases y {len(PARES)} pares en {destino}")


if __name__ == "__main__":
    main()
