"""Cruce por nombre entre restaurantes_v1.xlsx y restaurantes_v2.xlsx (clasificar_restaurantes_jev.py).
Necesita las dependencias del proceso de datos (typesafe-sdk); si no están, se salta."""

import sys
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("typesafe_sdk")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "obtener_datos"))
from clasificar_restaurantes_jev import _cruzar_por_nombre  # noqa: E402

REST = pd.DataFrame({"Nombre": ["Casa Pepe", "Bar Ñandú", "La Tasca", "La  Tasca!"], "ID": [1, 2, 3, 4]})


def test_exacto_y_aproximado():
    ids, modo = _cruzar_por_nombre(["casa pepe", "Bar Nandu", "Desconocido"], REST)
    assert ids == [1, 2, None]   # "Bar Nandu" solo coincide sin tildes ni signos
    assert modo == {"exacto": 1, "aproximado": 1, "sin_cruce": 1}


def test_aproximado_ambiguo_no_cruza():
    # "La Tasca" y "La  Tasca!" comparten clave aproximada: si el exacto falla, no se adivina
    ids, _ = _cruzar_por_nombre(["LA-TASCA"], REST)
    assert ids == [None]
