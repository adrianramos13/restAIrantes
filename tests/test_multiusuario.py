"""
Modo multiusuario sin Supabase real: datos.py con `requests` falso, y la app (AppTest) con el
usuario y la base de datos sustituidos por versiones falsas hechas con el excel de siempre.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import datos
import sesion

RAIZ = Path(__file__).resolve().parent.parent
APP = str(RAIZ / "algoritmo" / "app.py")
EXCEL = RAIZ / "excels" / "clasificacion_jev.xlsx"
REFERENCIA = json.loads((Path(__file__).resolve().parent / "referencia.json").read_text(encoding="utf-8"))
CHUECA = (40.4227, -3.6993)


# ---------------------------------------------------------------- datos.py

def test_clave_restaurante():
    assert datos.clave_restaurante("  Casa   Pepe ") == "casa pepe"
    assert datos.clave_restaurante("ＣＡＳＡ") == "casa"   # NFKC
    assert datos.clave_restaurante(None) == ""


def test_valor_para_json():
    assert datos.valor_para_json(float("nan")) is None
    assert datos.valor_para_json(np.float64("nan")) is None
    assert datos.valor_para_json(np.int64(3)) == 3 and type(datos.valor_para_json(np.int64(3))) is int
    assert datos.valor_para_json(np.float64(4.5)) == 4.5
    assert datos.valor_para_json(pd.NA) is None
    assert datos.valor_para_json("20-30 €") == "20-30 €"
    json.dumps(datos.fila_para_json({"a": np.float64("nan"), "b": np.int64(1), "c": "x"}))   # serializable


def test_filas_a_dataframes():
    filas = [
        {"posicion": 2, "restaurantes": {"id": 7, "datos": {"Nombre": "B", "ID": 999}, "imagen": "b.jpg",
                                          "platos": [{"Plato": "sushi", "Sentimiento": "Buena"}]}},
        {"posicion": 1, "restaurantes": {"id": 3, "datos": {"Nombre": "A"}, "imagen": None, "platos": []}},
    ]
    maestro, platos = datos.filas_a_dataframes(filas)
    assert list(maestro["Nombre"]) == ["A", "B"]          # en el orden de la lista
    assert list(maestro["ID"]) == [3, 7]                  # el id del catálogo manda sobre el ID viejo
    assert list(maestro["Imagen archivo"])[1] == "b.jpg"
    assert platos.to_dict("records") == [{"ID_Restaurante": 7, "Plato": "sushi", "Sentimiento": "Buena"}]
    vacio_m, vacio_p = datos.filas_a_dataframes([])
    assert vacio_m.empty and list(vacio_p.columns) == datos.COLUMNAS_PLATOS


@pytest.mark.parametrize("enlace, valido", [
    ("https://maps.app.goo.gl/5QLC8VhBqetTCbjGA", True),
    ("  https://maps.app.goo.gl/5QLC8VhBqetTCbjGA  ", True),
    ("https://www.google.com/maps/@40.5,-4.0,10z/data=!4m3!11m2!2sFdskzm5", True),
    ("https://www.google.es/maps/placelists/list/abc", True),
    ("http://maps.app.goo.gl/5QLC8VhBqetTCbjGA", False),                 # sin https
    ("https://maps.app.goo.gl.evil.com/x", False),
    ("https://www.google.com.evil.co/maps/x", False),
    ("https://evil.com/?u=https://maps.app.goo.gl/x", False),
    ("javascript:alert(1)", False),
    ("", False),
    (None, False),
])
def test_enlace_lista_valido(enlace, valido):
    assert datos.enlace_lista_valido(enlace) is valido


def test_filtro_in_escapa_nombres():
    assert datos._filtro_in(['Bar "El" Sitio', "A, B (C)"]) == r'("Bar \"El\" Sitio","A, B (C)")'


class RespuestaFalsa:
    def __init__(self, cuerpo, codigo=200):
        self.status_code, self.ok, self._cuerpo = codigo, codigo < 400, cuerpo
        self.content = b"x" if cuerpo is not None else b""
        self.text = json.dumps(cuerpo)

    def json(self):
        return self._cuerpo


def test_guardar_restaurantes_hace_upsert_por_clave(monkeypatch):
    llamadas = []

    def falso(metodo, url, **kw):
        llamadas.append((metodo, url, kw))
        return RespuestaFalsa([{"clave": f["clave"], "id": i} for i, f in enumerate(kw["json"], start=10)])

    monkeypatch.setattr(datos.requests, "request", falso)
    cliente = datos.Supabase("https://x.supabase.co/", "clave-secreta")
    ids = cliente.guardar_restaurantes([{"clave": "a", "datos": {}, "platos": [], "imagen": None},
                                        {"clave": "b", "datos": {}, "platos": [], "imagen": None}])
    assert ids == {"a": 10, "b": 11}
    metodo, url, kw = llamadas[0]
    assert (metodo, url) == ("POST", "https://x.supabase.co/rest/v1/restaurantes")
    assert kw["params"] == {"on_conflict": "clave"}
    assert "merge-duplicates" in kw["headers"]["Prefer"]
    assert kw["headers"]["Authorization"] == "Bearer clave-secreta"


def test_reemplazar_lista_quita_repetidos(monkeypatch):
    llamadas = []
    monkeypatch.setattr(datos.requests, "request",
                        lambda metodo, url, **kw: llamadas.append((metodo, kw)) or RespuestaFalsa(None))
    datos.Supabase("https://x.supabase.co", "k").reemplazar_lista(5, [7, 3, 7, 9])
    assert llamadas[0][0] == "DELETE"
    assert [f["restaurante_id"] for f in llamadas[1][1]["json"]] == [7, 3, 9]
    assert [f["posicion"] for f in llamadas[1][1]["json"]] == [1, 2, 4]


def test_error_de_supabase(monkeypatch):
    monkeypatch.setattr(datos.requests, "request", lambda *a, **k: RespuestaFalsa({"message": "no"}, 401))
    with pytest.raises(datos.ErrorSupabase):
        datos.Supabase("https://x.supabase.co", "k").lista_de("ana@ejemplo.com")


# ---------------------------------------------------------------- la app en modo multiusuario

LISTA_OK = {"id": 1, "usuario": "ana@ejemplo.com", "enlace": "https://maps.app.goo.gl/abc", "estado": "lista",
            "mensaje": None, "actualizado_en": "2026-10-12T09:00:00+00:00"}


@pytest.fixture
def multiusuario(monkeypatch):
    """Activa el modo multiusuario con un usuario y una base de datos falsos. Devuelve un dict
    para elegir el usuario, sus datos y ver qué se ha pedido a la base de datos."""
    estado = {"usuario": "ana@ejemplo.com", "permitidos": [], "con_lista": True, "pedidas": []}
    maestro = pd.read_excel(EXCEL, sheet_name="Restaurantes")
    platos = pd.read_excel(EXCEL, sheet_name="Platos mencionados")

    monkeypatch.setattr(sesion, "config_multiusuario",
                        lambda: {"url": "https://x.supabase.co", "clave_servicio": "k", "permitidos": estado["permitidos"]})
    monkeypatch.setattr(sesion, "usuario_actual", lambda: estado["usuario"])
    monkeypatch.setattr(datos.Supabase, "restaurantes_de", lambda self, u: (
        (maestro.copy(), platos.copy(), LISTA_OK) if estado["con_lista"]
        else (pd.DataFrame(), pd.DataFrame(columns=datos.COLUMNAS_PLATOS), None)))
    monkeypatch.setattr(datos.Supabase, "pedir_actualizacion",
                        lambda self, u, enlace: estado["pedidas"].append((u, enlace)))
    st.cache_data.clear()
    yield estado
    st.cache_data.clear()


def correr(at=None):
    if at is None:   # ojo: un AppTest sin ejecutar cuenta como "vacío", así que `at or ...` no sirve
        at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_sin_sesion_pide_entrar(multiusuario):
    multiusuario["usuario"] = None
    at = correr()
    assert [b.label for b in at.button] == ["Entrar con Google"]


def test_correo_no_permitido(multiusuario):
    multiusuario["permitidos"] = ["otra@ejemplo.com"]
    at = correr()
    assert any("no tiene acceso" in w.value for w in at.warning)
    assert "Buscar restaurantes" not in [b.label for b in at.button]


def test_usuario_sin_lista_ve_mi_lista_y_pide_procesar(multiusuario):
    multiusuario["con_lista"] = False
    at = correr()
    assert "Buscar restaurantes" not in [b.label for b in at.button]
    assert any("Todavía no has añadido tu lista" in m.value for m in at.markdown)

    at.text_input(key="enlace_lista").input("https://evil.com/lista")
    [b for b in at.button if b.label == "Guardar y procesar"][0].click().run()
    assert any("no parece de una lista de Google Maps" in e.value for e in at.error)
    assert multiusuario["pedidas"] == []

    at.text_input(key="enlace_lista").input("https://maps.app.goo.gl/5QLC8VhBqetTCbjGA")
    [b for b in at.button if b.label == "Guardar y procesar"][0].click().run()
    assert multiusuario["pedidas"] == [("ana@ejemplo.com", "https://maps.app.goo.gl/5QLC8VhBqetTCbjGA")]


def test_usuario_con_lista_busca_igual_que_en_local(multiusuario):
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["ubicacion_actual"] = CHUECA
    at = correr(at)
    assert any("al día" in m.value for m in at.markdown)
    at.button(key="boton_buscar").click().run()
    assert not at.exception
    assert "resultado" in at.session_state, (at.session_state["vista"], [e.value for e in at.error],
                                             [w.value for w in at.warning], [b.label for b in at.button])
    df = at.session_state["resultado"]["df_puntuado"].sort_values(["Score", "ID"], ascending=[False, True])
    huella = [[int(i), round(float(s), 4)] for i, s in zip(df["ID"], df["Score"])]
    assert huella == REFERENCIA["cualquiera_20min"]
