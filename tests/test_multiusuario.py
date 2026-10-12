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


def test_filas_catalogo_desde_excel():
    df_rest = pd.DataFrame([
        {"ID": 1, "Nombre": "Casa Pepe", "Puntuación": 4.5, "Rango de precios": float("nan"), "Imagen archivo": "casa-pepe.jpg"},
        {"ID": 2, "Nombre": "HUNDRED", "Puntuación": np.float64(4.1), "Rango de precios": "20-30 €", "Imagen archivo": None},
        {"ID": 3, "Nombre": "hundred ", "Puntuación": 4.1, "Rango de precios": "20-30 €", "Imagen archivo": None},
    ])
    df_platos = pd.DataFrame([{"ID_Restaurante": 1, "Plato": "cachopo", "Sentimiento": "Buena"}])
    filas = datos.filas_catalogo_desde_excel(df_rest, df_platos)
    assert [f["clave"] for f in filas] == ["casa pepe", "hundred"]     # el repetido, una sola vez
    assert filas[0]["datos"] == {"Nombre": "Casa Pepe", "Puntuación": 4.5, "Rango de precios": None}
    assert filas[0]["platos"] == [{"Plato": "cachopo", "Sentimiento": "Buena"}]
    assert filas[0]["imagen"] == "casa-pepe.jpg" and filas[1]["imagen"] is None
    json.dumps(filas)   # todo serializable a JSON


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


@pytest.mark.parametrize("entrada, esperado", [
    ("  Ana   García ", "Ana García"),
    ("Adrián", "Adrián"),
    ("x" * 40, "x" * 40),
])
def test_validar_nombre_valido(entrada, esperado):
    assert datos.validar_nombre(entrada) == esperado


@pytest.mark.parametrize("entrada", ["", "   ", None, "x" * 41, "<script>alert(1)</script>", "Ana >"])
def test_validar_nombre_no_valido(entrada):
    with pytest.raises(ValueError):
        datos.validar_nombre(entrada)


def test_error_de_red_es_error_supabase(monkeypatch):
    def sin_red(*a, **k):
        raise datos.requests.ConnectionError("sin red")
    monkeypatch.setattr(datos.requests, "request", sin_red)
    with pytest.raises(datos.ErrorSupabase):
        datos.Supabase("https://x.supabase.co", "k").perfil_de("ana@ejemplo.com")


def test_guardar_perfil(monkeypatch):
    llamadas = []
    monkeypatch.setattr(datos.requests, "request", lambda metodo, url, **kw: llamadas.append((metodo, url, kw))
                        or RespuestaFalsa([{"usuario": "ana@ejemplo.com", "nombre": "Ana"}]))
    fila = datos.Supabase("https://x.supabase.co", "k").guardar_perfil("ana@ejemplo.com", "Ana")
    metodo, url, kw = llamadas[0]
    assert (metodo, url, kw["params"]) == ("POST", "https://x.supabase.co/rest/v1/perfiles", {"on_conflict": "usuario"})
    assert kw["json"]["usuario"] == "ana@ejemplo.com" and kw["json"]["nombre"] == "Ana"
    assert fila["nombre"] == "Ana"


def test_cabeceras_segun_tipo_de_clave():
    nueva = datos.Supabase("https://x.supabase.co", "sb_secret_abc")._cabeceras
    assert nueva == {"apikey": "sb_secret_abc"}                  # no es JWT: sin Authorization
    antigua = datos.Supabase("https://x.supabase.co", "eyJhbGci.x.y")._cabeceras
    assert antigua == {"apikey": "eyJhbGci.x.y", "Authorization": "Bearer eyJhbGci.x.y"}


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
    estado = {"usuario": "ana@ejemplo.com", "permitidos": [], "con_lista": True, "pedidas": [],
              "google": {"nombre": "Ana García", "foto": "https://lh3.googleusercontent.com/a/foto"},
              "perfil": None, "perfil_falla": False}
    maestro = pd.read_excel(EXCEL, sheet_name="Restaurantes")
    platos = pd.read_excel(EXCEL, sheet_name="Platos mencionados")

    monkeypatch.setattr(sesion, "config_multiusuario",
                        lambda: {"url": "https://x.supabase.co", "clave_servicio": "k", "permitidos": estado["permitidos"]})
    monkeypatch.setattr(sesion, "usuario_actual", lambda: estado["usuario"])
    monkeypatch.setattr(sesion, "datos_google", lambda: estado["google"])

    def perfil_de(self, u):
        if estado["perfil_falla"]:
            raise datos.ErrorSupabase("GET perfiles: 404 (la tabla no existe)")
        return estado["perfil"]
    monkeypatch.setattr(datos.Supabase, "perfil_de", perfil_de)
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


def portada(at):
    return " ".join(h.proto.body for h in at.get("html") if "portada" in h.proto.body)


def test_portada_saluda_con_el_nombre_de_google(multiusuario):
    at = correr()
    assert "Lista de Ana García · " in portada(at)


def test_portada_saluda_con_el_nombre_elegido(multiusuario):
    multiusuario["perfil"] = {"usuario": "ana@ejemplo.com", "nombre": "Anita"}
    at = correr()
    assert "Lista de Anita · " in portada(at)


def test_sin_tabla_perfiles_la_app_sigue_funcionando(multiusuario):
    multiusuario["perfil_falla"] = True
    at = correr()
    assert "Lista de Ana García · " in portada(at)
    assert "Buscar restaurantes" in [b.label for b in at.button]


def test_nombre_con_html_se_escapa_en_la_portada(multiusuario):
    multiusuario["google"] = {"nombre": "<b>Ana</b>", "foto": None}
    at = correr()
    assert "&lt;b&gt;Ana&lt;/b&gt;" in portada(at) and "<b>Ana</b>" not in portada(at)


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
