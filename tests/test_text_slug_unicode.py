from utils.text import construir_slug


def test_slug_conserva_caracteres_unicode():
    slug = construir_slug("Песня 夜に駆ける")
    assert "песня" in slug
    assert "夜に駆ける" in slug


def test_slug_no_cae_a_fallback_en_cirilico():
    casos = [
        ("Шарлот", "шарлот"),
        ("Малышка", "малышка"),
        ("Четыре украинки", "четыре_украинки"),
        ("Мне пох", "мне_пох"),
        ("Последняя Любовь", "последняя_любовь"),
        ("Cristal & МОЁТ", "cristal_моёт"),
    ]
    for original, esperado in casos:
        assert construir_slug(original) == esperado


def test_slug_fallback_solo_para_valores_realmente_vacios_o_inutiles():
    assert construir_slug("") == "sin_titulo"
    assert construir_slug("   ") == "sin_titulo"
    assert construir_slug("////***:::|||???") == "sin_titulo"
    assert construir_slug(None) == "sin_titulo"


def test_slug_regresion_latino_y_acentos():
    assert construir_slug("Beyoncé - Niño") == "beyoncé_niño"
    assert construir_slug("Canción número 1") == "canción_número_1"
