"""Tests del verificador de anclaje de hechos (FCT-001)."""

from apps.checks.hechos import anclar_hechos


def test_cifra_nueva_bloquea():
    resultado = anclar_hechos(
        "El plan cuesta 100 euros.",
        "El plan cuesta 250 euros.",
    )

    assert resultado["regla"] == "FCT-001"
    assert resultado["severidad"] == "alta"
    assert resultado["bloquea"] is True
    assert [
        (entidad["tipo"], entidad["valor"])
        for entidad in resultado["entidades"]
    ] == [("cifra", "250")]


def test_nombre_propio_nuevo_bloquea():
    resultado = anclar_hechos(
        "El informe analiza el mercado local.",
        "El informe analiza el mercado de Madrid.",
    )

    assert resultado["severidad"] == "alta"
    assert resultado["bloquea"] is True
    assert [
        (entidad["tipo"], entidad["valor"])
        for entidad in resultado["entidades"]
    ] == [("nombre", "Madrid")]


def test_entidad_existente_no_bloquea():
    original = "El informe de Madrid cifra el coste en 100 euros."

    resultado = anclar_hechos(original, original)

    assert resultado["entidades"] == []
    assert resultado["bloquea"] is False
    assert resultado["severidad"] is None


def test_mayuscula_inicio_frase_en_exclusion_no_bloquea():
    resultado = anclar_hechos(
        "El informe analiza el mercado.",
        "Además, el informe analiza el mercado.",
        excluir=["Además"],
    )

    assert resultado["entidades"] == []
    assert resultado["bloquea"] is False


def test_lista_exclusion_vacia_marca_todo():
    resultado = anclar_hechos(
        "El informe analiza el mercado.",
        "Además, el informe analiza el mercado.",
        excluir=[],
    )

    assert resultado["severidad"] == "alta"
    assert resultado["bloquea"] is True
    assert [
        (entidad["tipo"], entidad["valor"])
        for entidad in resultado["entidades"]
    ] == [("nombre", "Además")]
