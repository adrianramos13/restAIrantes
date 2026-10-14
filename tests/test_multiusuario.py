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

import cuentas
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
    monkeypatch.setattr(datos.Supabase, "todos_los_restaurantes", lambda self: (maestro.copy(), platos.copy()))
    # Amigos y "He ido": sin amigos salvo que el test diga otra cosa.
    estado.update(relaciones=[], visitas=[], visitas_guardadas=[], confirmacion=True)
    monkeypatch.setattr(datos.Supabase, "relaciones_de", lambda self, u: estado["relaciones"])
    monkeypatch.setattr(datos.Supabase, "visitas_de", lambda self, usuarios, limite=10: estado["visitas"])
    monkeypatch.setattr(datos.Supabase, "registrar_visita", lambda self, u, i, nota=None, comentario=None:
                        estado["visitas_guardadas"].append((u, i, nota, comentario)))
    monkeypatch.setattr(cuentas.Cuentas, "confirmacion_obligatoria", lambda self: estado["confirmacion"])
    st.cache_data.clear()
    yield estado
    st.cache_data.clear()


def correr(at=None, seccion="comer"):
    if at is None:   # ojo: un AppTest sin ejecutar cuenta como "vacío", así que `at or ...` no sirve
        at = AppTest.from_file(APP, default_timeout=180)
    if "seccion" not in at.session_state:
        at.session_state["seccion"] = seccion
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_sin_sesion_pide_entrar(multiusuario):
    multiusuario["usuario"] = None
    at = correr()
    assert "Entrar con Google" in [b.label for b in at.button]
    assert at.text_input(key="entrar_correo") and at.text_input(key="entrar_contrasena")


def test_sin_confirmacion_de_correo_no_hay_cuentas_con_contrasena(multiusuario):
    multiusuario["usuario"], multiusuario["confirmacion"] = None, False
    at = correr()
    assert [b.label for b in at.button] == ["Entrar con Google"]
    assert any("Confirm email" in c.value for c in at.caption)


def test_correo_no_permitido(multiusuario):
    multiusuario["permitidos"] = ["otra@ejemplo.com"]
    at = correr()
    assert any("no tiene acceso" in w.value for w in at.warning)
    assert "Buscar restaurantes" not in [b.label for b in at.button]


def test_usuario_sin_lista_va_al_perfil_y_pide_sincronizar(multiusuario):
    multiusuario["con_lista"] = False
    at = correr()
    assert "Buscar restaurantes" not in [b.label for b in at.button]
    assert any("Todavía no tienes restaurantes" in i.value for i in at.info)

    [b for b in at.button if b.label == "Añadir tu lista"][0].click().run()   # lleva al Perfil
    assert not at.exception and at.session_state["seccion"] == "perfil"
    assert any("Todavía no has añadido tu lista" in m.value for m in at.markdown)

    at.text_input(key="enlace_lista").input("https://evil.com/lista")
    at.button(key="sincronizar_lista").click().run()
    assert any("no parece de una lista de Google Maps" in e.value for e in at.error)
    assert multiusuario["pedidas"] == []

    at.text_input(key="enlace_lista").input("https://maps.app.goo.gl/5QLC8VhBqetTCbjGA")
    at.button(key="sincronizar_lista").click().run()
    assert multiusuario["pedidas"] == [("ana@ejemplo.com", "https://maps.app.goo.gl/5QLC8VhBqetTCbjGA")]


def test_buscar_en_todos_los_restaurantes_sin_lista_propia(multiusuario):
    multiusuario["con_lista"] = False
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["ubicacion_actual"] = CHUECA
    at.session_state["fuente"] = "Todos los restaurantes"
    at = correr(at)
    assert "Todos los restaurantes · " in portada(at)
    at.button(key="boton_buscar").click().run()
    assert not at.exception
    assert not at.session_state["resultado"]["df_puntuado"].empty


def _supabase_falso(monkeypatch, respuestas):
    """Supabase con _rest sustituido: `respuestas` decide qué devolver según (método, tabla, params)."""
    llamadas = []

    def _rest(self, metodo, tabla, *, params=None, json=None, prefer=None):
        llamadas.append((metodo, tabla, params, json))
        return respuestas(metodo, tabla, params or {})
    monkeypatch.setattr(datos.Supabase, "_rest", _rest)
    return datos.Supabase("https://x.supabase.co", "k"), llamadas


def test_pedir_actualizacion_copia_una_lista_ya_procesada(monkeypatch):
    def respuestas(metodo, tabla, params):
        if (metodo, tabla) == ("POST", "listas"):
            return [{"id": 2, "usuario": "nuevo@ejemplo.com", "estado": "pendiente"}]
        if (metodo, tabla) == ("GET", "listas"):
            return [{"id": 1, "usuario": "adrian@ejemplo.com", "estado": "lista"}]
        if (metodo, tabla) == ("GET", "lista_restaurantes"):
            return [{"restaurante_id": 7, "posicion": 1}, {"restaurante_id": 3, "posicion": 2}]
        return None
    bd_, llamadas = _supabase_falso(monkeypatch, respuestas)
    lista = bd_.pedir_actualizacion("nuevo@ejemplo.com", "https://maps.app.goo.gl/abc")
    assert lista["estado"] == "lista"
    copiadas = [j for m, t, p, j in llamadas if (m, t) == ("POST", "lista_restaurantes")][0]
    assert [(f["lista_id"], f["restaurante_id"]) for f in copiadas] == [(2, 7), (2, 3)]
    assert [j for m, t, p, j in llamadas if (m, t) == ("PATCH", "listas")][0]["estado"] == "lista"


def test_pedir_actualizacion_sin_copia_queda_pendiente(monkeypatch):
    def respuestas(metodo, tabla, params):
        if (metodo, tabla) == ("POST", "listas"):
            return [{"id": 2, "usuario": "nuevo@ejemplo.com", "estado": "pendiente"}]
        return []   # nadie más tiene esa lista
    bd_, llamadas = _supabase_falso(monkeypatch, respuestas)
    assert bd_.pedir_actualizacion("nuevo@ejemplo.com", "https://maps.app.goo.gl/abc")["estado"] == "pendiente"
    assert not [1 for m, t, p, j in llamadas if t == "lista_restaurantes" and m != "GET"]


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
    at.button(key="boton_buscar").click().run()
    assert not at.exception
    assert "resultado" in at.session_state, (at.session_state["vista"], [e.value for e in at.error],
                                             [w.value for w in at.warning], [b.label for b in at.button])
    df = at.session_state["resultado"]["df_puntuado"].sort_values(["Score", "ID"], ascending=[False, True])
    huella = [[int(i), round(float(s), 4)] for i, s in zip(df["ID"], df["Score"])]
    assert huella == REFERENCIA["cualquiera_20min"]


@pytest.mark.parametrize("guardadas, esperado", [
    (None, datos.PREFERENCIAS_DEFECTO),
    ({"transporte": "A pie", "tiempo": 35, "presupuesto": [10, 100]},
     {"transporte": "A pie", "tiempo": 35, "presupuesto": [10, 100]}),
    ({"transporte": "En cohete", "tiempo": 37, "presupuesto": [40, 10]}, datos.PREFERENCIAS_DEFECTO),
    ({"tiempo": True, "presupuesto": [0, "30"]}, datos.PREFERENCIAS_DEFECTO),
    ("basura", datos.PREFERENCIAS_DEFECTO),
])
def test_preferencias_validas(guardadas, esperado):
    assert datos.preferencias_validas(guardadas) == esperado


def test_guardar_perfil_con_preferencias(monkeypatch):
    llamadas = []
    monkeypatch.setattr(datos.requests, "request", lambda metodo, url, **kw: llamadas.append(kw)
                        or RespuestaFalsa([{"usuario": "ana@ejemplo.com", "nombre": "Ana"}]))
    datos.Supabase("https://x.supabase.co", "k").guardar_perfil(
        "ana@ejemplo.com", "Ana", {"transporte": "A pie", "tiempo": 999})
    assert llamadas[0]["json"]["preferencias"] == {"transporte": "A pie", "tiempo": 20, "presupuesto": [0, 30]}



def test_inicio_saluda_y_propone_un_plato(multiusuario):
    at = correr(seccion="inicio")
    assert "Hola, Ana García." in portada(at) and "Lista de Ana García · " in portada(at)
    assert any(h.value.startswith("¿Te apetece ") for h in at.subheader)


def test_perfil_guarda_preferencias_y_el_buscador_las_usa(multiusuario, monkeypatch):
    guardadas = []
    monkeypatch.setattr(datos.Supabase, "guardar_perfil",
                        lambda self, u, nombre, preferencias=None: guardadas.append((u, nombre, preferencias)))
    multiusuario["perfil"] = {"usuario": "ana@ejemplo.com", "nombre": "Anita",
                              "preferencias": {"transporte": "A pie", "tiempo": 35, "presupuesto": [10, 40]}}
    at = correr(seccion="perfil")
    assert any("Anita" in m.value and "ana@ejemplo.com" in m.value for m in at.markdown)
    assert at.slider(key="pref_tiempo").value == 35
    at.slider(key="pref_tiempo").set_value(50).run()
    at.button(key="guardar_preferencias").click().run()
    assert not at.exception
    assert guardadas == [("ana@ejemplo.com", "Anita", {"transporte": "A pie", "tiempo": 50, "presupuesto": [10, 40]})]

    at.session_state["seccion"] = "comer"
    at.run()   # el perfil falso sigue diciendo 35: el buscador arranca con lo guardado en la base de datos
    assert at.slider(key="tiempo").value == 35 and at.slider(key="presupuesto").value == (10, 40)


# ---------------------------------------------------------------- amigos y "He ido"

@pytest.mark.parametrize("entrada, esperado", [("@Ana_G", "ana_g"), ("  pepe.99 ", "pepe.99")])
def test_validar_alias_valido(entrada, esperado):
    assert datos.validar_alias(entrada) == esperado


@pytest.mark.parametrize("entrada", ["ab", "áéí", "con espacio", "a" * 21, "", None, "x,y"])
def test_validar_alias_no_valido(entrada):
    with pytest.raises(ValueError):
        datos.validar_alias(entrada)


def test_directorio_solo_gente_con_alias_y_sin_uno_mismo(monkeypatch):
    bd_, llamadas = _supabase_falso(monkeypatch, lambda m, t, p: [])
    bd_.directorio(excepto="yo@x.com")
    metodo, tabla, params, _ = llamadas[-1]
    assert (metodo, tabla) == ("GET", "perfiles")
    assert params["alias"] == "not.is.null" and params["usuario"] == "neq.yo@x.com"
    assert params["select"] == "usuario,nombre,alias"


def test_solicitar_amistad(monkeypatch):
    existentes = []
    bd_, llamadas = _supabase_falso(monkeypatch, lambda m, t, p: existentes if m == "GET" else None)
    assert bd_.solicitar_amistad("ana@x.com", "luis@x.com") == "pendiente"
    assert llamadas[-1][0:2] == ("POST", "amistades")
    assert llamadas[-1][3] == {"solicitante": "ana@x.com", "destinatario": "luis@x.com"}

    existentes.append({"solicitante": "luis@x.com", "destinatario": "ana@x.com", "estado": "pendiente"})
    assert bd_.solicitar_amistad("ana@x.com", "luis@x.com") == "aceptada"   # él ya se la había pedido
    metodo, tabla, params, cuerpo = llamadas[-1]
    assert (metodo, tabla, cuerpo) == ("PATCH", "amistades", {"estado": "aceptada"})
    assert params["solicitante"] == "eq.luis@x.com" and params["destinatario"] == "eq.ana@x.com"

    with pytest.raises(ValueError):
        bd_.solicitar_amistad("ana@x.com", "ana@x.com")


def test_alias_repetido_es_value_error(monkeypatch):
    def _rest(self, metodo, tabla, **kw):
        raise datos.ErrorSupabase("POST perfiles: 409 duplicate key value violates unique constraint")
    monkeypatch.setattr(datos.Supabase, "_rest", _rest)
    with pytest.raises(ValueError, match="@ana_g"):
        datos.Supabase("https://x.supabase.co", "k").guardar_alias("ana@x.com", "Ana", "ana_g")


def test_registrar_visita_actualiza_la_que_hubiera(monkeypatch):
    bd_, llamadas = _supabase_falso(monkeypatch, lambda m, t, p: None)
    bd_.registrar_visita("ana@x.com", np.int64(7), 4.5, "  Las   croquetas ")
    metodo, tabla, params, cuerpo = llamadas[-1]
    assert (metodo, tabla, params) == ("POST", "visitas", {"on_conflict": "usuario,restaurante_id"})
    assert {k: cuerpo[k] for k in ("usuario", "restaurante_id", "nota", "comentario")} == {
        "usuario": "ana@x.com", "restaurante_id": 7, "nota": 4.5, "comentario": "Las croquetas"}
    bd_.registrar_visita("ana@x.com", 7)
    assert llamadas[-1][3]["nota"] is None and llamadas[-1][3]["comentario"] is None
    bd_.quitar_visita("ana@x.com", 7)
    assert llamadas[-1][:3] == ("DELETE", "visitas", {"usuario": "eq.ana@x.com", "restaurante_id": "eq.7"})


@pytest.mark.parametrize("nota", [0, 0.3, 4.25, 5.5, 6, True, "4"])
def test_nota_no_valida(nota):
    with pytest.raises(ValueError):
        datos.validar_nota(nota)


def test_comentario_demasiado_largo():
    with pytest.raises(ValueError):
        datos.validar_comentario("x" * 281)


def test_visitas_a_dataframe():
    visitas = [{"usuario": "luis@x.com", "nota": 5, "creado_en": "2026-10-12T20:00:00+00:00",
                "restaurantes": {"id": 7, "datos": {"Nombre": "Casa Pepe"}, "imagen": "casa-pepe.jpg"}},
               {"usuario": "eva@x.com", "nota": None, "creado_en": "2026-10-11T20:00:00+00:00",
                "restaurantes": None}]   # restaurante borrado del catálogo: se salta
    df = datos.visitas_a_dataframe(visitas, {"luis@x.com": "Luis"})
    assert df.to_dict("records") == [{"Nombre": "Casa Pepe", "ID": 7, "Imagen archivo": "casa-pepe.jpg",
                                      "Amigo": "Luis", "Nota visita": 5, "Comentario visita": None,
                                      "Fecha visita": "2026-10-12T20:00:00+00:00"}]


# ---------------------------------------------------------------- cuentas con contraseña en la app

SESION_ANA = {"correo": "ana@ejemplo.com", "nombre": "Ana", "acceso": "acc", "renovacion": "ren"}


def boton(at, etiqueta):
    return [b for b in at.button if b.label == etiqueta][0]


def test_entrar_con_correo_y_contrasena(multiusuario, monkeypatch):
    multiusuario["usuario"] = None
    pedidas = []
    monkeypatch.setattr(cuentas.Cuentas, "entrar", lambda self, c, p: pedidas.append((c, p)) or SESION_ANA)
    at = correr(seccion="inicio")
    at.text_input(key="entrar_correo").input("ana@ejemplo.com")
    at.text_input(key="entrar_contrasena").input("secreta123")
    boton(at, "Entrar").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert pedidas == [("ana@ejemplo.com", "secreta123")]
    assert at.session_state["cuenta"] == SESION_ANA
    assert "Hola, Ana." in portada(at)                      # dentro, con el nombre del registro


def test_contrasena_incorrecta(multiusuario, monkeypatch):
    multiusuario["usuario"] = None

    def entrar(self, c, p):
        raise cuentas.ErrorCuenta("Correo o contraseña incorrectos.")
    monkeypatch.setattr(cuentas.Cuentas, "entrar", entrar)
    at = correr()
    at.text_input(key="entrar_correo").input("ana@ejemplo.com")
    at.text_input(key="entrar_contrasena").input("mala")
    boton(at, "Entrar").click().run()
    assert any("incorrectos" in e.value for e in at.error) and "cuenta" not in at.session_state


def test_registro_valida_el_nombre_y_las_contrasenas(multiusuario, monkeypatch):
    multiusuario["usuario"] = None
    registros = []
    monkeypatch.setattr(cuentas.Cuentas, "registrar", lambda self, c, p, n: registros.append((c, n)))
    at = correr()
    at.segmented_control(key="modo_acceso").set_value("Crear cuenta").run()
    at.text_input(key="registro_nombre").input("Ana")
    at.text_input(key="registro_correo").input("ana@ejemplo.com")
    at.text_input(key="registro_contrasena").input("secreta123")
    at.text_input(key="registro_repetida").input("otra-cosa")
    boton(at, "Crear cuenta").click().run()
    assert any("no coinciden" in e.value for e in at.error) and registros == []
    at.text_input(key="registro_repetida").input("secreta123")
    boton(at, "Crear cuenta").click().run()
    assert registros == [("ana@ejemplo.com", "Ana")]
    assert any("Te hemos enviado un correo" in m.value for m in at.success)


def test_cerrar_sesion_con_contrasena(multiusuario, monkeypatch):
    multiusuario["usuario"] = None
    salidas = []
    monkeypatch.setattr(cuentas.Cuentas, "salir", lambda self, token: salidas.append(token))
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["cuenta"] = SESION_ANA
    at = correr(at, seccion="perfil")
    at.button(key="cerrar_sesion").click().run()
    assert not at.exception and salidas == ["acc"]
    assert "cuenta" not in at.session_state and at.session_state["cookie_borrar"]
    assert "Entrar con Google" in [b.label for b in at.button]   # de vuelta a la pantalla de entrar


# ---------------------------------------------------------------- amigos en la app

def test_inicio_sin_amigos_invita_a_buscarlos(multiusuario):
    at = correr(seccion="inicio")
    assert any(h.value == "Tus amigos han ido a" for h in at.subheader)
    at.button(key="ir_a_amigos").click().run()
    assert at.session_state["seccion"] == "perfil"


def test_inicio_ensena_las_visitas_de_los_amigos(multiusuario):
    multiusuario["relaciones"] = [{"usuario": "luis@x.com", "nombre": "Luis", "alias": "luis",
                                   "estado": "aceptada", "enviada": False}]
    multiusuario["visitas"] = [VISITA_LUIS]
    at = correr(seccion="inicio")
    assert not at.exception, [e.value for e in at.exception]
    assert not any("todavía no han marcado" in c.value or "Añade amigos" in c.value for c in at.caption)


def test_perfil_pide_elegir_nombre_de_usuario(multiusuario, monkeypatch):
    guardados = []
    monkeypatch.setattr(datos.Supabase, "guardar_alias", lambda self, u, n, a: guardados.append((u, n, a)))
    at = correr(seccion="perfil")
    at.text_input(key="alias_nuevo").input("Ana G")                     # espacio: no vale
    at.button(key="guardar_alias").click().run()
    assert any("3 a 20 caracteres" in e.value for e in at.error) and guardados == []
    at.text_input(key="alias_nuevo").input("@Ana_G")
    at.button(key="guardar_alias").click().run()
    assert guardados == [("ana@ejemplo.com", "Ana García", "ana_g")]


def test_perfil_solicitudes_y_busqueda(multiusuario, monkeypatch):
    multiusuario["perfil"] = {"usuario": "ana@ejemplo.com", "nombre": "Ana", "alias": "ana_g"}
    multiusuario["relaciones"] = [{"usuario": "luis@x.com", "nombre": "Luis", "alias": "luis",
                                   "estado": "pendiente", "enviada": False}]
    respuestas, solicitudes = [], []
    monkeypatch.setattr(datos.Supabase, "responder_solicitud",
                        lambda self, u, de, aceptar: respuestas.append((u, de, aceptar)))
    monkeypatch.setattr(datos.Supabase, "directorio", lambda self, excepto: [
        {"usuario": "eva@x.com", "nombre": "[Eva](javascript:alert(1))", "alias": "eva"},
        {"usuario": "pepe@x.com", "nombre": "Pepe", "alias": "pepe_99"}])
    monkeypatch.setattr(datos.Supabase, "solicitar_amistad", lambda self, de, a: solicitudes.append((de, a)))
    at = correr(seccion="perfil")
    assert any("Luis" in m.value and "quiere ser tu amigo" in m.value for m in at.markdown)
    at.button(key="aceptar_luis").click().run()
    assert respuestas == [("ana@ejemplo.com", "luis@x.com", True)]

    buscador = at.selectbox(key="buscar_amigos")
    assert buscador.options == ["[Eva](javascript:alert(1)) · @eva", "Pepe · @pepe_99"]   # sugerencias: nombre y @
    assert not any("@x.com" in o for o in buscador.options)            # sin correos
    buscador.select("eva").run()
    textos = " ".join(m.value for m in at.markdown)
    assert "eva@x.com" not in textos                                   # el correo no se enseña nunca
    assert r"\[Eva\]\(javascript" in textos                          # el nombre no puede meter un enlace
    at.button(key="anadir_eva").click().run()
    assert solicitudes == [("ana@ejemplo.com", "eva@x.com")]


def test_he_ido_desde_la_ficha(multiusuario):
    at = correr(seccion="inicio")
    _, id_restaurante, _ = at.session_state["sugerencia"]
    at.button(key="ver_ficha_sugerida").click().run()
    # En Streamlit real, el botón de la ventana solo recarga la ventana; AppTest recarga todo el script,
    # así que se vuelve a pedir abrir la ficha antes del clic.
    at.session_state["ficha_abrir"] = id_restaurante
    at.text_area(key=f"comentario_visita_{id_restaurante}").input("Las croquetas")
    at.session_state["ficha_abrir"] = id_restaurante
    at.button(key=f"he_ido_{id_restaurante}").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert multiusuario["visitas_guardadas"] == [("ana@ejemplo.com", id_restaurante, None, "Las croquetas")]


VISITA_LUIS = {"usuario": "luis@x.com", "nota": 4.5, "comentario": "Las bravas",
               "creado_en": "2026-10-12T20:00:00+00:00",
               "restaurantes": {"id": 7, "datos": {"Nombre": "Casa Pepe", "Puntuación": 4.5}, "imagen": None}}


def test_perfil_ensena_arroba_y_mis_visitas(multiusuario):
    multiusuario["perfil"] = {"usuario": "ana@ejemplo.com", "nombre": "Ana", "alias": "ana_g"}
    multiusuario["visitas"] = [{**VISITA_LUIS, "usuario": "ana@ejemplo.com"}]
    at = correr(seccion="perfil")
    assert not at.exception, [e.value for e in at.exception]
    cabecera = [m.value for m in at.markdown if m.value.startswith("### Ana")][0]
    assert cabecera.index("@ana_g") < cabecera.index("ana@ejemplo.com")   # nombre, @usuario y correo
    assert any(h.value == "Los restaurantes a los que has ido" for h in at.subheader)
    assert any(c.value == "1 restaurante" for c in at.caption)


def test_ficha_en_verde_si_ya_has_ido(multiusuario):
    at = correr(seccion="inicio")
    _, id_restaurante, _ = at.session_state["sugerencia"]
    multiusuario["visitas"] = [{**VISITA_LUIS, "usuario": "ana@ejemplo.com",
                                "restaurantes": {**VISITA_LUIS["restaurantes"], "id": id_restaurante}}]
    st.cache_data.clear()
    at.session_state["ficha_abrir"] = id_restaurante
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert any(m.value.startswith("**✓ Has ido**") for m in at.markdown)
    assert at.text_area(key=f"comentario_visita_{id_restaurante}").value == "Las bravas"
    assert at.button(key=f"he_ido_{id_restaurante}").label == "Guardar"
