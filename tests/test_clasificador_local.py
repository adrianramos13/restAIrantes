"""Clasificador gratis de reseñas (obtener_datos/clasificador_local.py), el sustituto de Jev."""

import sys
from pathlib import Path

import pytest

pytest.importorskip("typesafe_sdk")   # importa las categorías de clasificar_restaurantes_jev
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "obtener_datos"))
import clasificador_local as cl  # noqa: E402
import clasificar_restaurantes_jev as cj  # noqa: E402


@pytest.mark.parametrize("texto, esperada", [
    ("El sushi y el ramen buenísimos, muy auténtico japonés", "japonesa"),
    ("La mejor pizza napolitana y una carbonara de verdad", "italiana"),
    ("Tacos al pastor y guacamole muy ricos", "mexicana"),
    ("Hamburguesas enormes y alitas", "americana"),
    ("El chuletón a la brasa en su punto", "carnes_parrilla"),
    ("Atendieron rápido y el sitio es bonito", "no_se_sabe"),
])
def test_cocina_por_palabras(texto, esperada):
    assert cl.clasificar(texto)["categoria"] == esperada


@pytest.mark.parametrize("estrellas, esperado", [(5, "Buena"), (4.0, "Buena"), (3, "Neutra"), (2, "Mala"), (1, "Mala")])
def test_sentimiento_por_estrellas(estrellas, esperado):
    assert cl.clasificar("Todo correcto, sin más", estrellas)["sentimiento"] == esperado


def test_sentimiento_sin_estrellas_por_palabras():
    assert cl.clasificar("Espectacular, volveremos seguro", float("nan"))["sentimiento"] == "Buena"
    assert cl.clasificar("Horrible, no volveremos nunca más", None)["sentimiento"] == "Mala"


def test_mismo_formato_que_jev_y_agregable():
    salida = cl.clasificar("Paella riquísima", 5)
    assert salida["categoria"] in cj.CATEGORIAS and salida["sentimiento"] in cj.CATEGORIAS_SENTIMIENTO
    fila = cj.agregar_restaurante([{**salida, "estado": "ok"}] * 3)
    assert fila["Categoría (Jev)"] == "Arroces y mediterránea" and fila["Reseñas buenas"] == 3
