"""Importador de Overture (obtener_datos/importar_overture.py): sus funciones puras, sin red ni DuckDB."""

import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "obtener_datos"))
import importar_overture as io_  # noqa: E402


def lugares(*filas):
    columnas = ["id", "nombre", "primaria", "basica", "lat", "lon", "direccion", "ciudad", "pais", "web",
                "telefono", "confianza"]
    return pd.DataFrame([dict(zip(columnas, f)) for f in filas], columns=columnas)


def test_etiqueta_categoria():
    assert io_.etiqueta_categoria("japanese_restaurant", "restaurant") == "Japonesa"
    assert io_.etiqueta_categoria("raro_restaurant", "fast_food_restaurant") == "Comida rápida"   # por el tipo
    assert io_.etiqueta_categoria(None, None) == "Restaurante"


def test_filas_lugares_sin_nan_y_con_nombre_para_buscar():
    df = lugares(("a1", "Sobrino de Botín", "spanish_restaurant", "restaurant", 40.41, -3.70, "C. Cuchilleros 17",
                  "Madrid", "ES", float("nan"), None, 0.987654))
    fila = io_.filas_lugares(df)[0]
    assert fila["nombre_busqueda"] == "sobrino de botin" and fila["categoria"] == "Española"
    assert fila["web"] is None and fila["telefono"] is None and fila["confianza"] == 0.988
    assert set(fila) == set(io_.filas_lugares(lugares(("b", "X", None, "bar", 1.0, 2.0, *[None] * 6)))[0])


def test_enlazar_mismo_sitio_y_nombre_parecido():
    df = lugares(
        ("cerca-parecido", "Dabaobao", "chinese_restaurant", "restaurant", 40.4200, -3.7000, *[None] * 6),
        ("cerca-distinto", "Bar Sobrado", "bar", "bar", 40.4201, -3.7001, *[None] * 6),
        ("lejos-igual", "Casa Pepe", "restaurant", "restaurant", 41.0, -3.7, *[None] * 6),
    )
    catalogo = pd.DataFrame([
        {"ID": 7, "Nombre": "DaBaobao", "Latitud": 40.4205, "Longitud": -3.7003},       # ~60 m
        {"ID": 8, "Nombre": "Bar Gyoza Go!", "Latitud": 40.4201, "Longitud": -3.7001},  # al lado pero otro nombre
        {"ID": 9, "Nombre": "Casa Pepe", "Latitud": 40.4, "Longitud": -3.7},            # mismo nombre, a 60 km
        {"ID": 10, "Nombre": "Sin sitio", "Latitud": math.nan, "Longitud": math.nan},
    ])
    assert io_.enlazar(df, catalogo) == {"cerca-parecido": 7}
    assert io_.enlazar(df.iloc[:0], catalogo) == {} and io_.enlazar(df, pd.DataFrame()) == {}


def test_ids_a_cerrar_solo_los_que_ya_no_estan_y_nadie_ha_pedido():
    existentes = {"sigue": "sin_analizar", "se_fue": "sin_analizar", "fallo": "error", "pedido": "pendiente",
                  "analizado": "analizado", "ya_cerrado": "cerrado"}
    abiertos = {"sigue"} | {f"nuevo{i}" for i in range(10)}
    assert io_.ids_a_cerrar(existentes, abiertos) == {"se_fue", "fallo"}


def test_ids_a_cerrar_no_cierra_nada_si_la_descarga_viene_corta():
    existentes = {f"l{i}": "sin_analizar" for i in range(100)}
    assert io_.ids_a_cerrar(existentes, {"l1", "l2"}) == set()          # ¿ha fallado la descarga? por si acaso
    assert io_.ids_a_cerrar({}, set()) == set()
