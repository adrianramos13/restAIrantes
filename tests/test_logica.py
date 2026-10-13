"""Tests de la lógica de recomendación (algoritmo/logica.py): sin Streamlit, sin red, con datos
inventados. Cubren los filtros estrictos, la puntuación de cocina y el orden."""

import math
import random

import pandas as pd
import pytest

from logica import (COL_CATEGORIA, COL_CATEGORIA_2, COL_VOTOS_1, COL_VOTOS_2, ORDEN_CERCANOS,
                    ORDEN_NOMBRE, ORDEN_PUNTUACION, ORDEN_RESENAS, SCORE_COCINA_DESCONOCIDA,
                    SCORE_COCINA_SECUNDARIA, estadisticas_lista, filtrar_lista, filtrar_y_puntuar,
                    ordenar_resultados, parsear_rango_precio, puntuacion_cocina, solapamiento,
                    sugerencia_plato, hace_cuanto)


@pytest.mark.parametrize("texto, esperado", [
    ("20-30 €", (20, 30)),
    ("10–20 €", (10, 20)),
    ("Más de 60 €", (60, None)),
    ("60+ €", (60, None)),
    ("10 €", (None, 10)),
    ("", (None, None)),
    (float("nan"), (None, None)),
])
def test_parsear_rango_precio(texto, esperado):
    assert parsear_rango_precio(texto) == esperado


def test_solapamiento():
    assert solapamiento(30, 40, 0, 30) == 0.0             # se tocan pero no se cruzan
    assert solapamiento(20, 30, 0, 30) == pytest.approx(1 / 3)
    assert solapamiento(None, None, 0, 30) == 0.5          # precio desconocido: ni sí ni no
    assert solapamiento(60, None, 0, None) == 1.0          # "más de 60" con presupuesto sin tope


def fila(**campos):
    base = {COL_CATEGORIA: None, COL_CATEGORIA_2: None, COL_VOTOS_1: None, COL_VOTOS_2: None,
            "Tipo de cocina": ""}
    return pd.Series({**base, **campos})


def test_puntuacion_cocina_con_jev():
    assert puntuacion_cocina(fila(**{COL_CATEGORIA: "Italiana"}), "Italiana", True) == 1.0
    assert puntuacion_cocina(fila(**{COL_CATEGORIA: "Japonesa"}), "Italiana", True) == 0.0
    secundaria = fila(**{COL_CATEGORIA: "Japonesa", COL_CATEGORIA_2: "Italiana", COL_VOTOS_1: 0.6, COL_VOTOS_2: 0.3})
    assert puntuacion_cocina(secundaria, "Italiana", True) == SCORE_COCINA_SECUNDARIA
    poca = fila(**{COL_CATEGORIA: "Japonesa", COL_CATEGORIA_2: "Italiana", COL_VOTOS_1: 0.8, COL_VOTOS_2: 0.1})
    assert puntuacion_cocina(poca, "Italiana", True) == 0.0
    empate = fila(**{COL_CATEGORIA: "Japonesa", COL_CATEGORIA_2: "Italiana", COL_VOTOS_1: 0.4, COL_VOTOS_2: 0.4})
    assert puntuacion_cocina(empate, "Italiana", True) == 1.0


def test_puntuacion_cocina_sin_categoria_usa_google_por_raiz():
    assert puntuacion_cocina(fila(**{"Tipo de cocina": "Asiática, Fusión"}), "Asiática (otras)", True) == 1.0
    assert puntuacion_cocina(fila(**{"Tipo de cocina": "Restaurante"}), "Italiana", True) == SCORE_COCINA_DESCONOCIDA
    assert puntuacion_cocina(fila(), "", True) == 0.5   # sin cocina pedida


def maestro_de_prueba():
    return pd.DataFrame([
        {"ID": 1, "Nombre": "Italiano cerca", COL_CATEGORIA: "Italiana", "Rango de precios": "10-20 €",
         "Puntuación": 4.5, "Nº Reseñas": 100},
        {"ID": 2, "Nombre": "Italiano lejos", COL_CATEGORIA: "Italiana", "Rango de precios": "10-20 €",
         "Puntuación": 4.9, "Nº Reseñas": 300},
        {"ID": 3, "Nombre": "Japonés", COL_CATEGORIA: "Japonesa", "Rango de precios": "10-20 €",
         "Puntuación": 4.8, "Nº Reseñas": 200},
        {"ID": 4, "Nombre": "Italiano caro", COL_CATEGORIA: "Italiana", "Rango de precios": "50-60 €",
         "Puntuación": 4.7, "Nº Reseñas": 150},
        {"ID": 5, "Nombre": "Italiano sin precio", COL_CATEGORIA: "Italiana", "Rango de precios": None,
         "Puntuación": 4.0, "Nº Reseñas": 50},
        {"ID": 6, "Nombre": "Italiano sin coordenadas", COL_CATEGORIA: "Italiana", "Rango de precios": "10-20 €",
         "Puntuación": 5.0, "Nº Reseñas": 500},
    ])


PLATOS = pd.DataFrame([
    {"ID_Restaurante": 1, "Plato": "carbonara", "Sentimiento": "Buena"},
    {"ID_Restaurante": 5, "Plato": "carbonara", "Sentimiento": "Mala"},
    {"ID_Restaurante": 5, "Plato": "carbonara", "Sentimiento": "Mala"},
])
MINUTOS = [5, 25, 6, 7, 8, None]   # misma posición que maestro_de_prueba()


def busqueda(**cambios):
    r = {"presupuesto_min": 0, "presupuesto_max": 30, "cocina": "Italiana", "tiempo_maximo_min": 20,
         "plato_deseado": ""}
    return {**r, **cambios}


def test_filtros_estrictos():
    df = filtrar_y_puntuar(maestro_de_prueba(), PLATOS, busqueda(), MINUTOS)
    # fuera: 2 (lejos), 3 (otra cocina), 4 (fuera de presupuesto), 6 (sin tiempo);
    # dentro: 5, porque sin precio conocido no se puede descartar
    assert sorted(df["ID"]) == [1, 5]
    assert df["Score"].between(0, 1).all()


def test_no_rellena_si_no_hay():
    df = filtrar_y_puntuar(maestro_de_prueba(), PLATOS, busqueda(cocina="Mexicana"), MINUTOS)
    assert df.empty


def test_filtro_de_plato_exige_menciones_positivas():
    df = filtrar_y_puntuar(maestro_de_prueba(), PLATOS, busqueda(plato_deseado="carbonara"), MINUTOS)
    assert list(df["ID"]) == [1]   # el 5 solo tiene menciones malas


def test_presupuesto_sin_tope_admite_caros():
    df = filtrar_y_puntuar(maestro_de_prueba(), PLATOS, busqueda(presupuesto_max=None), MINUTOS)
    assert 4 in set(df["ID"])


def test_ordenar_resultados():
    df = filtrar_y_puntuar(maestro_de_prueba(), PLATOS, busqueda(cocina="", presupuesto_max=None), MINUTOS)
    por_nota = ordenar_resultados(df, ORDEN_PUNTUACION)
    assert list(por_nota["Score"]) == sorted(por_nota["Score"], reverse=True)
    por_cercania = ordenar_resultados(df, ORDEN_CERCANOS)
    tiempos = list(por_cercania["Tiempo desplazamiento (min)"])
    assert tiempos == sorted(tiempos) and not any(math.isnan(t) for t in tiempos)


# ---------------------------------------------------------------- "Mi lista", Inicio y Perfil

def test_filtrar_lista():
    m = maestro_de_prueba()
    m["Estado"] = ["", "", "", "Cerrado temporalmente", "", ""]
    todos = filtrar_lista(m, PLATOS, presupuesto_max=None)
    assert len(todos) == 6 and list(todos["ID"])[0] == 6                       # sin filtros, por nota
    assert list(filtrar_lista(m, PLATOS, texto="japones")["ID"]) == [3]        # sin tildes ni mayúsculas
    assert sorted(filtrar_lista(m, PLATOS, cocinas=["Japonesa"])["ID"]) == [3]
    assert 4 not in set(filtrar_lista(m, PLATOS, presupuesto_max=30)["ID"])   # fuera de presupuesto
    assert set(filtrar_lista(m, PLATOS, nota_min=4.8, presupuesto_max=None)["ID"]) == {2, 3, 6}
    assert list(filtrar_lista(m, PLATOS, plato="carbonara")["ID"]) == [1]      # solo menciones buenas
    assert 4 not in set(filtrar_lista(m, PLATOS, ocultar_cerrados=True, presupuesto_max=None)["ID"])
    assert list(filtrar_lista(m, PLATOS, orden=ORDEN_RESENAS, presupuesto_max=None)["ID"])[0] == 6
    assert list(filtrar_lista(m, PLATOS, orden=ORDEN_NOMBRE, presupuesto_max=None)["Nombre"])[0] == "Italiano caro"
    assert filtrar_lista(m, PLATOS, texto="no existe", cocinas=["Italiana"]).empty
    assert filtrar_lista(pd.DataFrame(), PLATOS, texto="x").empty                 # lista vacía


def test_sugerencia_plato():
    m = maestro_de_prueba()
    m["Estado"] = ["", "", "", "", "", "Cerrado permanentemente"]
    platos = pd.DataFrame([
        {"ID_Restaurante": 1, "Plato": "carbonara", "Sentimiento": "Buena"},
        {"ID_Restaurante": 1, "Plato": "carbonara", "Sentimiento": "Buena"},
        {"ID_Restaurante": 2, "Plato": "carbonara", "Sentimiento": "Buena"},
        {"ID_Restaurante": 2, "Plato": "carbonara", "Sentimiento": "Buena"},
        {"ID_Restaurante": 2, "Plato": "carbonara", "Sentimiento": "Buena"},
        {"ID_Restaurante": 3, "Plato": "sushi", "Sentimiento": "Buena"},       # una sola mención: no basta
        {"ID_Restaurante": 6, "Plato": "lasaña", "Sentimiento": "Buena"},      # cerrado
        {"ID_Restaurante": 6, "Plato": "lasaña", "Sentimiento": "Buena"},
        {"ID_Restaurante": 4, "Plato": "tiramisú", "Sentimiento": "Mala"},     # malas no cuentan
        {"ID_Restaurante": 4, "Plato": "tiramisú", "Sentimiento": "Mala"},
        {"ID_Restaurante": 3, "Plato": "India", "Sentimiento": "Buena"},       # es una cocina, no un plato
        {"ID_Restaurante": 3, "Plato": "India", "Sentimiento": "Buena"},
    ])
    rng = random.Random(1)
    assert sugerencia_plato(m, platos, rng) == ("carbonara", 2, 3)              # el que más lo elogia
    assert sugerencia_plato(m, platos, rng, evitar="carbonara") == ("carbonara", 2, 3)   # no hay otro
    assert sugerencia_plato(m, PLATOS, rng) is None
    assert sugerencia_plato(pd.DataFrame(), platos, rng) is None


def test_estadisticas_lista():
    e = estadisticas_lista(maestro_de_prueba())
    assert e["total"] == 6 and e["cocinas"].to_dict() == {"Italiana": 5, "Japonesa": 1}
    assert e["precio_medio"] == pytest.approx((15 * 4 + 55) / 5)
    assert e["nota_media"] == pytest.approx(sum([4.5, 4.9, 4.8, 4.7, 4.0, 5.0]) / 6)
    assert estadisticas_lista(pd.DataFrame()) is None


def test_hace_cuanto():
    from datetime import datetime, timezone
    ahora = datetime(2026, 10, 13, 9, 0, tzinfo=timezone.utc)
    assert hace_cuanto("2026-10-13T08:00:00+00:00", ahora) == "hoy"
    assert hace_cuanto("2026-10-12T23:59:00+00:00", ahora) == "ayer"
    assert hace_cuanto("2026-10-10T12:00:00.123456+00:00", ahora) == "hace 3 días"
    assert hace_cuanto("2026-09-01T12:00:00+00:00", ahora) == "01/09"
