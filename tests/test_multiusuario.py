"""
Modo multiusuario sin Supabase real: datos.py con `requests` falso, y la app (AppTest) con el
usuario y la base de datos sustituidos por versiones falsas hechas con el excel de siempre.
"""

import json
import re
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
    monkeypatch.setattr(datos.Supabase, "visitas_de", lambda self, usuarios, limite=10, desde=None: estado["visitas"])
    def registrar_visita(self, u, i, nota=None, comentario=None, fecha=None, anadido_por=None):
        estado["visitas_guardadas"].append((u, i, nota, comentario))
        estado["fechas_visita"].append(fecha)
    estado["fechas_visita"] = []
    monkeypatch.setattr(datos.Supabase, "registrar_visita", registrar_visita)
    monkeypatch.setattr(cuentas.Cuentas, "confirmacion_obligatoria", lambda self: estado["confirmacion"])
    estado["fotos_guardadas"] = []
    # Eatlist: filas como las devuelve Supabase (con el restaurante embebido) y lo que se guarda.
    estado.update(eatlist=[], eatlists_guardadas=[])
    monkeypatch.setattr(datos.Supabase, "eatlist_de", lambda self, u: estado["eatlist"])
    monkeypatch.setattr(datos.Supabase, "guardar_eatlist", lambda self, u, ids: estado["eatlists_guardadas"].append(list(ids)))
    monkeypatch.setattr(datos.Supabase, "guardar_foto", lambda self, u, n, f: estado["fotos_guardadas"].append((u, f)))
    # "He ido con...": sin invitaciones salvo que el test diga otra cosa
    estado.update(comensales=[], anadido_por=None, invitados=[], invitaciones=[], invitaciones_enviadas=[],
                  invitaciones_borradas=[], invitaciones_aceptadas=[])
    monkeypatch.setattr(datos.Supabase, "comensales_de", lambda self, u, i: estado["comensales"])
    monkeypatch.setattr(datos.Supabase, "anadido_por", lambda self, u, i: estado["anadido_por"])
    monkeypatch.setattr(datos.Supabase, "invitados_de", lambda self, u, i: estado["invitados"])
    monkeypatch.setattr(datos.Supabase, "invitaciones_para", lambda self, u: estado["invitaciones"])
    monkeypatch.setattr(datos.Supabase, "invitar_comensales", lambda self, u, i, amigos, fecha=None:
                        estado["invitaciones_enviadas"].append((u, i, list(amigos), fecha)))
    monkeypatch.setattr(datos.Supabase, "borrar_invitacion", lambda self, de, para, i:
                        estado["invitaciones_borradas"].append((de, para, i)))
    monkeypatch.setattr(datos.Supabase, "aceptar_invitacion", lambda self, u, de, i, nota=None, comentario=None, fecha=None:
                        estado["invitaciones_aceptadas"].append((u, de, i, nota, comentario, fecha)))
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

    [b for b in at.button if b.label == "Añadir tu lista"][0].click().run()   # al Perfil, con los ajustes abiertos
    assert not at.exception and at.session_state["seccion"] == "perfil"
    assert any("Todavía no has añadido tu lista" in m.value for m in at.markdown)

    # (AppTest recarga todo el script en cada paso: se vuelve a pedir abrir la ventana de ajustes)
    at.session_state["abrir_ajustes"] = True
    at.text_input(key="enlace_lista").input("https://evil.com/lista")
    at.session_state["abrir_ajustes"] = True
    at.button(key="sincronizar_lista").click().run()
    assert any("no parece de una lista de Google Maps" in e.value for e in at.error)
    assert multiusuario["pedidas"] == []

    at.session_state["abrir_ajustes"] = True
    at.text_input(key="enlace_lista").input("https://maps.app.goo.gl/5QLC8VhBqetTCbjGA")
    at.session_state["abrir_ajustes"] = True
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
    assert "Los restaurantes de Ana García<br>" in portada(at)


def test_portada_saluda_con_el_nombre_elegido(multiusuario):
    multiusuario["perfil"] = {"usuario": "ana@ejemplo.com", "nombre": "Anita"}
    at = correr()
    assert "Los restaurantes de Anita<br>" in portada(at)


def test_sin_tabla_perfiles_la_app_sigue_funcionando(multiusuario):
    multiusuario["perfil_falla"] = True
    at = correr()
    assert "Los restaurantes de Ana García<br>" in portada(at)
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
    assert "Hola, Ana García." in portada(at) and "Los restaurantes de Ana García<br>" in portada(at)
    assert any(h.value.startswith("¿Te apetece ") for h in at.subheader)


def test_perfil_guarda_preferencias_y_el_buscador_las_usa(multiusuario, monkeypatch):
    guardadas = []
    monkeypatch.setattr(datos.Supabase, "guardar_perfil",
                        lambda self, u, nombre, preferencias=None: guardadas.append((u, nombre, preferencias)))
    multiusuario["perfil"] = {"usuario": "ana@ejemplo.com", "nombre": "Anita",
                              "preferencias": {"transporte": "A pie", "tiempo": 35, "presupuesto": [10, 40]}}
    at = correr(seccion="perfil")
    assert "Anita" in cabecera(at)
    assert "pref_tiempo" not in [w.key for w in at.slider]               # ya no está en la pestaña Perfil
    at.session_state["abrir_ajustes"] = True                            # está en los ajustes (tocando tu foto)
    at.run()
    assert at.slider(key="pref_tiempo").value == 35
    at.session_state["abrir_ajustes"] = True
    at.slider(key="pref_tiempo").set_value(50).run()
    at.session_state["abrir_ajustes"] = True
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


def test_fecha_de_la_visita():
    from datetime import date, timedelta
    assert datos.momento_visita(date(2026, 10, 12)) == "2026-10-12T14:00:00+02:00"   # ese día, hora de Madrid
    with pytest.raises(ValueError):
        datos.momento_visita(date.today() + timedelta(days=2))                        # nunca en el futuro
    assert datos.momento_visita(None)[:10] == datos._ahora()[:10]                   # sin decir: ahora


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
    assert at.session_state["seccion"] == "mi_lista" and at.session_state["buscar_modo"] == "Personas"


def test_inicio_ensena_las_visitas_de_los_amigos(multiusuario):
    multiusuario["relaciones"] = [{"usuario": "luis@x.com", "nombre": "Luis", "alias": "luis",
                                   "estado": "aceptada", "enviada": False}]
    multiusuario["visitas"] = [VISITA_LUIS]
    at = correr(seccion="inicio")
    assert not at.exception, [e.value for e in at.exception]
    assert not any("todavía no han marcado" in c.value or "Añade amigos" in c.value for c in at.caption)


def test_buscar_personas_pide_elegir_nombre_de_usuario(multiusuario, monkeypatch):
    guardados = []
    monkeypatch.setattr(datos.Supabase, "guardar_alias", lambda self, u, n, a: guardados.append((u, n, a)))
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["buscar_modo"] = "Personas"
    at = correr(at, seccion="mi_lista")
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
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["perfil_vista"] = "amigos"                         # lo que hace tocar "amigos" arriba
    at = correr(at, seccion="perfil")
    assert any("Luis" in m.value and "quiere ser tu amigo" in m.value for m in at.markdown)
    at.button(key="aceptar_luis").click().run()
    assert respuestas == [("ana@ejemplo.com", "luis@x.com", True)]

    at.session_state["buscar_modo"] = "Personas"
    at.session_state["seccion"] = "mi_lista"
    at.run()
    # El buscador (componente propio) filtra en el navegador; aquí: qué le llega y qué hace "Añadir".
    buscador = [c for c in at.get("bidi_component") if "pepe_99" in str(c.proto)]
    assert buscador, "falta el buscador de amigos"
    assert "@x.com" not in str(buscador[0].proto)                      # al navegador no le llegan correos
    import amigos
    directorio = {"eva": {"usuario": "eva@x.com", "alias": "eva"}}
    cliente = datos.Supabase("https://x.supabase.co", "k")
    amigos.solicitar_por_alias(cliente, "ana@ejemplo.com", "eva", directorio)
    amigos.solicitar_por_alias(cliente, "ana@ejemplo.com", "no_existe", directorio)   # un @ inventado: nada
    assert solicitudes == [("ana@ejemplo.com", "eva@x.com")]


def abrir_ventana_he_ido(at, id_restaurante):
    """Toca "Ya he ido" (debajo de la foto) para abrir la ventanita. (AppTest recarga todo en cada paso: se
    vuelve a pedir abrir la ficha antes de cada clic, como hace Streamlit con la ventana abierta.)"""
    at.session_state["ficha_abrir"] = id_restaurante
    at.button(key=f"he_ido_{id_restaurante}").click().run()
    at.session_state["ficha_abrir"] = id_restaurante
    return at


def test_he_ido_desde_la_ficha(multiusuario):
    at = correr(seccion="inicio")
    _, id_restaurante, _ = at.session_state["sugerencia"]
    at.button(key="ver_ficha_sugerida").click().run()
    assert at.button(key=f"he_ido_{id_restaurante}").label == "Ya he ido"   # debajo de la foto
    assert not [t for t in at.text_area if t.key == f"comentario_visita_{id_restaurante}"]   # aún cerrada
    abrir_ventana_he_ido(at, id_restaurante)
    assert at.date_input(key=f"fecha_visita_{id_restaurante}")              # estrellas, fecha, comentario...
    at.text_area(key=f"comentario_visita_{id_restaurante}").input("Las croquetas")
    at.session_state["ficha_abrir"] = id_restaurante
    at.button(key=f"visita_guardar_{id_restaurante}").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert multiusuario["visitas_guardadas"] == [("ana@ejemplo.com", id_restaurante, None, "Las croquetas")]


VISITA_LUIS = {"usuario": "luis@x.com", "nota": 4.5, "comentario": "Las bravas",
               "creado_en": "2026-10-12T20:00:00+00:00",
               "restaurantes": {"id": 7, "datos": {"Nombre": "Casa Pepe", "Puntuación": 4.5}, "imagen": None}}


def test_ficha_en_verde_si_ya_has_ido(multiusuario):
    at = correr(seccion="inicio")
    _, id_restaurante, _ = at.session_state["sugerencia"]
    multiusuario["visitas"] = [{**VISITA_LUIS, "usuario": "ana@ejemplo.com",
                                "restaurantes": {**VISITA_LUIS["restaurantes"], "id": id_restaurante}}]
    st.cache_data.clear()
    at.session_state["ficha_abrir"] = id_restaurante
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.button(key=f"he_ido_{id_restaurante}").label == "Has ido · ★ 4,5 · 12/10/2026"
    abrir_ventana_he_ido(at, id_restaurante)
    assert at.text_area(key=f"comentario_visita_{id_restaurante}").value == "Las bravas"
    assert str(at.date_input(key=f"fecha_visita_{id_restaurante}").value) == "2026-10-12"


def test_visitas_de_solo_desde_una_fecha(monkeypatch):
    from datetime import datetime, timezone
    bd_, llamadas = _supabase_falso(monkeypatch, lambda m, t, p: [])
    bd_.visitas_de(["luis@x.com"], desde=datetime(2026, 10, 4, 9, 0, tzinfo=timezone.utc))
    assert llamadas[-1][2]["creado_en"] == "gte.2026-10-04T09:00:00+00:00"
    bd_.visitas_de(["luis@x.com"])
    assert "creado_en" not in llamadas[-1][2]


def test_inicio_pide_las_visitas_de_las_dos_ultimas_semanas(multiusuario, monkeypatch):
    from datetime import datetime, timedelta, timezone
    pedidas = []
    monkeypatch.setattr(datos.Supabase, "visitas_de", lambda self, usuarios, limite=10, desde=None:
                        pedidas.append(desde) or [VISITA_LUIS])
    multiusuario["relaciones"] = [{"usuario": "luis@x.com", "nombre": "Luis", "alias": "luis",
                                   "estado": "aceptada", "enviada": False}]
    at = correr(seccion="inicio")
    assert not at.exception, [e.value for e in at.exception]
    hace_dos_semanas = datetime.now(timezone.utc) - timedelta(days=14)
    assert any(d is not None and abs((d - hace_dos_semanas).total_seconds()) < 120 for d in pedidas)


def test_portada_con_el_arroba_si_lo_tiene(multiusuario):
    multiusuario["perfil"] = {"usuario": "ana@ejemplo.com", "nombre": "Anita", "alias": "ana_g"}
    at = correr(seccion="inicio")
    assert "Los restaurantes de @ana_g<br>" in portada(at)
    assert "Hola, Anita." in portada(at)   # el saludo sigue con el nombre



@pytest.mark.parametrize("url, valida", [
    ("https://lh3.googleusercontent.com/a/ACg8ocJ=s96-c", True),
    ("https://abcd.supabase.co/storage/v1/object/public/fotos/perfiles/" + "a1" * 16 + ".jpg", True),   # propia
    ("https://abcd.supabase.co/storage/v1/object/public/fotos/casa-pepe.jpg", False),   # foto de restaurante
    ("https://abcd.supabase.co/storage/v1/object/public/fotos/perfiles/x.svg", False),
    ("http://lh3.googleusercontent.com/a/x", False),                 # sin https
    ("https://googleusercontent.com.evil.com/a/x", False),
    ("https://evil.com/?u=https://lh3.googleusercontent.com/a", False),
    ('https://lh3.googleusercontent.com/a/x" onerror="alert(1)', False),
    (None, False),
])
def test_foto_valida(url, valida):
    assert (datos.foto_valida(url) is not None) is valida


def test_guardar_foto_solo_de_google(monkeypatch):
    bd_, llamadas = _supabase_falso(monkeypatch, lambda m, t, p: None)
    bd_.guardar_foto("ana@x.com", "Ana", "https://lh3.googleusercontent.com/a/foto")
    assert llamadas[-1][3]["foto"] == "https://lh3.googleusercontent.com/a/foto"
    with pytest.raises(ValueError):
        bd_.guardar_foto("ana@x.com", "Ana", "https://evil.com/foto.jpg")


def test_relaciones_traen_la_foto_si_es_valida(monkeypatch):
    def respuestas(m, t, p):
        if t == "amistades":
            return [{"solicitante": "ana@x.com", "destinatario": "luis@x.com", "estado": "aceptada"},
                    {"solicitante": "eva@x.com", "destinatario": "ana@x.com", "estado": "pendiente"}]
        return [{"usuario": "luis@x.com", "nombre": "Luis", "alias": "luis",
                 "foto": "https://lh3.googleusercontent.com/a/luis"},
                {"usuario": "eva@x.com", "nombre": "Eva", "alias": "eva", "foto": "https://evil.com/x.jpg"}]
    bd_, _ = _supabase_falso(monkeypatch, respuestas)
    luis, eva = bd_.relaciones_de("ana@x.com")
    assert luis["foto"] == "https://lh3.googleusercontent.com/a/luis" and luis["enviada"]
    assert eva["foto"] is None and not eva["enviada"]



# ---------------------------------------------------------------- amigos más visuales

LUIS = {"usuario": "luis@x.com", "nombre": "Luis", "alias": "luis", "estado": "aceptada", "enviada": False,
        "foto": "https://lh3.googleusercontent.com/a/luis"}
EVA = {"usuario": "eva@x.com", "nombre": "Eva", "alias": "eva", "estado": "pendiente", "enviada": False, "foto": None}


def test_se_guarda_la_foto_de_google_una_vez(multiusuario):
    at = correr(seccion="inicio")
    at.run()
    assert multiusuario["fotos_guardadas"] == [("ana@ejemplo.com", "https://lh3.googleusercontent.com/a/foto")]


def test_amigos_cifras_solicitudes_y_fila(multiusuario):
    multiusuario["perfil"] = {"usuario": "ana@ejemplo.com", "nombre": "Ana", "alias": "ana_g"}
    multiusuario["relaciones"] = [LUIS, EVA]
    at = correr(seccion="perfil")
    assert not any(h.value == "Amigos" for h in at.subheader)           # en la pestaña Perfil ya no están
    at.button(key="contador_amigos").click().run()                     # tocar "amigos" arriba abre su listado
    assert not at.exception, [e.value for e in at.exception]
    assert any(h.value == "Amigos" for h in at.subheader)
    assert at.button(key="contador_amigos").label == "**1** amigos"
    total = len(pd.read_excel(EXCEL, sheet_name="Restaurantes"))   # el amigo falso tiene la misma lista
    assert any(f"· {total} sitios de tu lista" in c.value for c in at.caption)
    assert any("Eva" in m.value and "quiere ser tu amigo" in m.value for m in at.markdown)
    assert at.button(key="aceptar_eva").label == "Aceptar"
    lista = [c for c in at.get("bidi_component") if "lista_amigos" in str(c.proto)]
    assert lista and "luis" in str(lista[0].proto) and "Luis" in str(lista[0].proto)   # su @ y su nombre
    assert "luis@x.com" not in str(lista[0].proto)                     # sin correos
    assert "ver_amigo_luis" not in [b.key for b in at.button]           # sin botón "Ver": se toca la fila
    at.session_state["amigo_abierto"] = "luis"                          # lo que hace tocar su fila
    at.run()
    assert any("% de gustos en común" in m.value for m in at.markdown)
    at.button(key="volver_del_listado").click().run()
    assert "perfil_vista" not in at.session_state


def test_mini_perfil_de_un_amigo(multiusuario):
    multiusuario["perfil"] = {"usuario": "ana@ejemplo.com", "nombre": "Ana", "alias": "ana_g"}
    multiusuario["relaciones"] = [LUIS]
    multiusuario["visitas"] = [VISITA_LUIS]
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["perfil_vista"] = "amigos"
    at.session_state["amigo_abierto"] = "luis"                          # lo que hace tocar "Ver" en el listado
    at = correr(at, seccion="perfil")
    assert any("% de gustos en común" in m.value for m in at.markdown)
    metricas = {m.label: m.value for m in at.metric}
    assert metricas["Ha ido a"] == "1" and metricas["Nota media"] == "4,5 ★"
    assert any(m.value.startswith("🍽️ Cocina favorita: **") for m in at.markdown)
    assert any(m.value.startswith("**En común**") for m in at.markdown)


def test_globito_de_solicitudes_en_la_barra(multiusuario):
    import re
    multiusuario["relaciones"] = [EVA, {**EVA, "usuario": "pepe@x.com", "alias": "pepe"}, LUIS]
    at = correr(seccion="inicio")
    barra = [c for c in at.get("bidi_component") if "barra_secciones" in str(c.proto)][0]
    assert re.search(r"avisos\W+2\b", str(barra.proto))                # 2 solicitudes recibidas (Luis ya es amigo)



def test_ver_mis_visitas_en_formato_lista(multiusuario):
    multiusuario["visitas"] = [{**VISITA_LUIS, "usuario": "ana@ejemplo.com",
                                "restaurantes": {"id": 900 + i, "imagen": None, "datos": {
                                    "Nombre": f"Sitio {i}", "Puntuación": 4.0 + i / 10, "Nº Reseñas": 100,
                                    "Rango de precios": "20-30 €", "Tipo de cocina": "Bar"}}} for i in range(3)]
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["perfil_pestana"] = "Diario"                       # el botón está en la pestaña Diario
    at = correr(at, seccion="perfil")
    at.button(key="mis_visitas_en_lista").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["seccion"] == "mi_lista" and at.toggle(key="ml_idos").value
    assert any(c.value == "3 de 3 restaurantes" for c in at.caption)    # solo los 3 a los que has ido
    at.toggle(key="ml_idos").set_value(False).run()                     # y se puede volver a la lista entera
    assert not any(c.value == "3 de 3 restaurantes" for c in at.caption)


def test_solo_los_que_he_ido_se_olvida_al_cambiar_de_pestana(multiusuario):
    multiusuario["visitas"] = [{**VISITA_LUIS, "usuario": "ana@ejemplo.com"}]
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["perfil_pestana"] = "Diario"                       # el botón está en la pestaña Diario
    at = correr(at, seccion="perfil")
    at.button(key="mis_visitas_en_lista").click().run()
    assert at.toggle(key="ml_idos").value
    at.session_state["seccion"] = "inicio"
    at.run()
    at.session_state["seccion"] = "mi_lista"                            # volver a Mi lista desde la barra
    at.run()
    assert not at.exception and at.toggle(key="ml_idos").value is False



def _imagen(ancho, alto, formato="PNG"):
    import io
    from PIL import Image
    salida = io.BytesIO()
    Image.new("RGB", (ancho, alto), (200, 80, 20)).save(salida, format=formato)
    return salida.getvalue()


def test_preparar_foto_perfil_la_deja_cuadrada_y_pequena():
    import io
    from PIL import Image
    jpeg = datos.preparar_foto_perfil(_imagen(1200, 800))
    with Image.open(io.BytesIO(jpeg)) as img:
        assert (img.format, img.size) == ("JPEG", (256, 256))
        assert not img.getexif()                                     # sin metadatos (ni GPS)


@pytest.mark.parametrize("contenido", [b"", b"esto no es una imagen", b"x" * (5 * 1024 * 1024 + 1)],
                         ids=["vacio", "no_es_imagen", "mas_de_5_mb"])
def test_preparar_foto_perfil_rechaza(contenido):
    with pytest.raises(ValueError):
        datos.preparar_foto_perfil(contenido)


def test_subir_foto_perfil(monkeypatch):
    subidas, borradas = [], []
    bd_, llamadas = _supabase_falso(monkeypatch, lambda m, t, p: None)
    monkeypatch.setattr(datos.Supabase, "subir_foto", lambda self, archivo, contenido: subidas.append((archivo, contenido)))
    monkeypatch.setattr(datos.requests, "delete", lambda url, **kw: borradas.append(url))
    anterior = "https://x.supabase.co/storage/v1/object/public/fotos/perfiles/" + "b2" * 16 + ".jpg"
    url = bd_.subir_foto_perfil("ana@x.com", "Ana", _imagen(300, 300), anterior=anterior)
    archivo, contenido = subidas[0]
    assert archivo.startswith("perfiles/") and archivo.endswith(".jpg") and contenido[:2] == b"\xff\xd8"   # JPEG
    assert datos.es_foto_propia(url) and llamadas[-1][3]["foto"] == url
    assert borradas == ["https://x.supabase.co/storage/v1/object/fotos/perfiles/" + "b2" * 16 + ".jpg"]
    bd_.quitar_foto_perfil("ana@x.com", "Ana", anterior=url)
    assert llamadas[-1][3]["foto"] is None and len(borradas) == 2
    bd_.quitar_foto_perfil("ana@x.com", "Ana", anterior="https://lh3.googleusercontent.com/a/x")
    assert len(borradas) == 2                                         # la de Google no es nuestra: no se borra



FOTO_PROPIA = "https://x.supabase.co/storage/v1/object/public/fotos/perfiles/" + "c3" * 16 + ".jpg"


def test_foto_propia_manda_sobre_la_de_google(multiusuario):
    multiusuario["perfil"] = {"usuario": "ana@ejemplo.com", "nombre": "Ana", "alias": "ana_g", "foto": FOTO_PROPIA}
    at = correr(seccion="perfil")
    assert not at.exception, [e.value for e in at.exception]
    assert multiusuario["fotos_guardadas"] == []                        # la de Google no la pisa
    barra = [c for c in at.get("bidi_component") if "barra_secciones" in str(c.proto)][0]
    assert FOTO_PROPIA in str(barra.proto)                              # la barra enseña la propia
    avatar = [c for c in at.get("bidi_component") if "ajustes" in str(c.proto) and FOTO_PROPIA in str(c.proto)]
    assert avatar                                                       # arriba, tu foto (abre tus ajustes)
    assert "quitar_foto" not in [b.key for b in at.button]              # "Quitar foto" ya no está en la cabecera
    assert "foto_perfil_0" not in str(at.main)                          # ya no hay barra para subir archivos


def test_quitar_mi_foto(multiusuario, monkeypatch):
    quitadas = []
    monkeypatch.setattr(datos.Supabase, "quitar_foto_perfil",
                        lambda self, u, n, anterior=None: quitadas.append((u, anterior)))
    multiusuario["perfil"] = {"usuario": "ana@ejemplo.com", "nombre": "Ana", "alias": "ana_g", "foto": FOTO_PROPIA}
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["abrir_ajustes"] = True                            # lo que hace tocar tu foto arriba
    at = correr(at, seccion="perfil")
    assert "quitar_foto" in [b.key for b in at.button]
    at.session_state["abrir_ajustes"] = True                            # (AppTest recarga todo: se reabre la ventana)
    at.button(key="quitar_foto").click().run()
    assert not at.exception and quitadas == [("ana@ejemplo.com", FOTO_PROPIA)]


def test_sin_foto_propia_no_hay_boton_de_quitar(multiusuario):
    at = correr(seccion="perfil")
    assert "quitar_foto" not in [b.key for b in at.button]


@pytest.mark.parametrize("texto", ["no es una foto", "data:text/html;base64,PGh0bWw+", "data:image/svg+xml;base64,PHN2Zz4=",
                                   "data:image/jpeg;base64," + "A" * (8 * 1024 * 1024)],
                         ids=["texto", "html", "svg", "demasiado_grande"])
def test_foto_desde_data_url_rechaza(texto):
    with pytest.raises(ValueError):
        datos.foto_desde_data_url(texto)


def test_foto_desde_data_url():
    import base64
    jpeg = datos.preparar_foto_perfil(_imagen(100, 100))
    assert datos.foto_desde_data_url("data:image/jpeg;base64," + base64.b64encode(jpeg).decode()) == jpeg



def test_guardar_eatlist_renumera_y_quita_las_que_sobran(monkeypatch):
    bd_, llamadas = _supabase_falso(monkeypatch, lambda m, t, p: None)
    bd_.guardar_eatlist("ana@x.com", [7, np.int64(3), 7, 9])
    (m1, t1, p1, j1), (m2, t2, p2, _) = llamadas[-2:]
    assert (m1, t1, p1) == ("POST", "eatlist", {"on_conflict": "usuario,restaurante_id"})
    assert j1 == [{"usuario": "ana@x.com", "restaurante_id": 7, "posicion": 1},
                  {"usuario": "ana@x.com", "restaurante_id": 3, "posicion": 2},
                  {"usuario": "ana@x.com", "restaurante_id": 9, "posicion": 3}]   # sin repetidos
    assert (m2, t2, p2) == ("DELETE", "eatlist", {"usuario": "eq.ana@x.com", "restaurante_id": "not.in.(7,3,9)"})
    bd_.guardar_eatlist("ana@x.com", [])                              # vaciarla: solo borra
    assert llamadas[-1][:3] == ("DELETE", "eatlist", {"usuario": "eq.ana@x.com"})


def test_eatlist_a_dataframe():
    df = datos.eatlist_a_dataframe([{"posicion": 1, "restaurantes": {"id": 7, "datos": {"Nombre": "Casa Pepe"},
                                                                       "imagen": None}},
                                    {"posicion": 2, "restaurantes": None}])
    assert df.to_dict("records") == [{"Nombre": "Casa Pepe", "ID": 7, "Imagen archivo": None, "Posición": 1}]



# ---------------------------------------------------------------- Perfil rediseñado: cabecera, Diario y Eatlist

def cabecera(at):
    return " ".join(h.proto.body for h in at.get("html") if "perfil-nombre" in h.proto.body)


def test_cabecera_estilo_instagram(multiusuario):
    multiusuario["perfil"] = {"usuario": "ana@ejemplo.com", "nombre": "Ana", "alias": "ana_g"}
    multiusuario["relaciones"] = [LUIS]
    multiusuario["visitas"] = [{**VISITA_LUIS, "usuario": "ana@ejemplo.com"}]
    at = correr(seccion="perfil")
    assert not at.exception, [e.value for e in at.exception]
    assert "Ana" in cabecera(at) and "@ana_g" in cabecera(at) and "ana@ejemplo.com" not in cabecera(at)
    total = len(pd.read_excel(EXCEL, sheet_name="Restaurantes"))
    assert [at.button(key=k).label for k in ("contador_idos", "contador_lista", "contador_amigos")] == [
        "**1** idos", f"**{total}** en tu lista", "**1** amigos"]
    assert [o for o in at.button_group if "Eatlist" in str(o.proto)], "faltan las pestañas Perfil / Diario / Eatlist"
    assert any(h.value == "Tus datos" for h in at.subheader)
    at.button(key="contador_idos").click().run()                       # "idos": Buscar con "solo los que he ido"
    assert at.session_state["seccion"] == "mi_lista" and at.toggle(key="ml_idos").value
    assert at.session_state["buscar_modo"] == "Mis restaurantes"
    at.session_state["seccion"] = "perfil"
    at.run()
    at.button(key="contador_lista").click().run()                      # "en tu lista": Buscar, sin ese filtro
    assert at.session_state["seccion"] == "mi_lista" and at.toggle(key="ml_idos").value is False


def test_diario_por_meses(multiusuario):
    multiusuario["visitas"] = [
        {**VISITA_LUIS, "usuario": "ana@ejemplo.com", "creado_en": "2026-10-07T20:00:00+00:00"},
        {**VISITA_LUIS, "usuario": "ana@ejemplo.com", "creado_en": "2026-08-23T20:00:00+00:00",
         "restaurantes": {**VISITA_LUIS["restaurantes"], "id": 8}}]
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["perfil_pestana"] = "Diario"
    at = correr(at, seccion="perfil")
    assert not at.exception, [e.value for e in at.exception]
    diario = [c for c in at.get("bidi_component") if "grupos" in str(c.proto) and "octubre 2026" in str(c.proto)]
    assert diario and "agosto 2026" in str(diario[0].proto)            # una cabecera por mes
    assert any(c.value == "2 restaurantes" for c in at.caption)


EATLIST = [{"posicion": n, "restaurantes": {"id": 900 + n, "datos": {"Nombre": nombre, "Rango de precios": "20-30 €"},
                                             "imagen": None}} for n, nombre in ((1, "Sitio A"), (2, "Sitio B"),
                                                                                (3, "Sitio C"))]


def test_eatlist_vista_previa_y_anadir(multiusuario):
    multiusuario["eatlist"] = EATLIST
    at = correr(seccion="inicio")
    _, id_restaurante, _ = at.session_state["sugerencia"]
    at.session_state["ficha_abrir"] = id_restaurante
    at.run()
    assert at.button(key=f"eat_abrir_{id_restaurante}").label == "Añadir a mi eatlist"
    assert not [n for n in at.number_input if n.key == f"eat_puesto_{id_restaurante}"]   # aún en la ficha
    at.session_state["ficha_abrir"] = id_restaurante
    at.button(key=f"eat_abrir_{id_restaurante}").click().run()        # "Tu eatlist" encima de la ficha
    assert not at.exception, [e.value for e in at.exception]
    nuevo = at.number_input(key=f"eat_puesto_{id_restaurante}")
    assert nuevo.value == 4 and nuevo.max == 4                          # por defecto, al final
    assert f"he_ido_{id_restaurante}" in [b.key for b in at.button]      # la ficha sigue abierta debajo
    # (AppTest recarga todo en cada paso: se vuelve a abrir la ficha; la capa sigue abierta sola)
    at.session_state["ficha_abrir"] = id_restaurante
    nuevo.set_value(2).run()                                            # el ejemplo: D en el puesto 2
    previa = " ".join(h.proto.body for h in at.get("html") if "eat-previa" in h.proto.body)
    assert re.search(r">1<.*Sitio A.*eat-este.*>2<.*>3<.*Sitio B", previa), previa   # 1 A · 2 este · 3 B
    assert multiusuario["eatlists_guardadas"] == []                     # aún no se ha guardado nada
    at.session_state["ficha_abrir"] = id_restaurante
    at.button(key=f"eat_guardar_{id_restaurante}").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert multiusuario["eatlists_guardadas"] == [[901, id_restaurante, 902, 903]]
    assert f"eat_capa_{id_restaurante}" not in at.session_state         # al guardar se cierra la capa


def test_he_ido_lo_quita_de_la_eatlist(multiusuario):
    at = correr(seccion="inicio")
    _, id_restaurante, _ = at.session_state["sugerencia"]
    multiusuario["eatlist"] = EATLIST + [{"posicion": 4, "restaurantes": {"id": id_restaurante, "datos": {
        "Nombre": "Este"}, "imagen": None}}]
    st.cache_data.clear()
    at.session_state["ficha_abrir"] = id_restaurante
    at.run()
    abrir_ventana_he_ido(at, id_restaurante)
    at.button(key=f"visita_guardar_{id_restaurante}").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert multiusuario["eatlists_guardadas"] == [[901, 902, 903]]      # ya has ido: fuera de la eatlist


def test_pestana_eatlist_en_orden(multiusuario):
    multiusuario["eatlist"] = EATLIST
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["perfil_pestana"] = "Eatlist"
    at = correr(at, seccion="perfil")
    assert not at.exception, [e.value for e in at.exception]
    lista = [c for c in at.get("bidi_component") if "Sitio A" in str(c.proto) and "puestos" in str(c.proto)]
    assert lista and str(lista[0].proto).index("Sitio A") < str(lista[0].proto).index("Sitio C")



def test_tocar_tu_foto_abre_los_ajustes_con_datos_personales(multiusuario, monkeypatch):
    guardados = []
    monkeypatch.setattr(datos.Supabase, "guardar_perfil", lambda self, u, n, preferencias=None: guardados.append((u, n)))
    at = correr(seccion="perfil")
    assert "perfil_nombre" not in [t.key for t in at.text_input]          # Datos personales ya no está en la pestaña
    at.session_state["abrir_ajustes"] = True                            # lo que hace tocar tu foto
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("Toca tu foto para cambiarla." in c.value for c in at.caption)
    at.session_state["abrir_ajustes"] = True
    at.text_input(key="perfil_nombre").input("Anita")
    at.session_state["abrir_ajustes"] = True
    at.button(key="guardar_perfil").click().run()
    assert guardados == [("ana@ejemplo.com", "Anita")]



def test_quitar_de_mi_lista_sin_borrar_el_restaurante(multiusuario, monkeypatch):
    quitados = []
    monkeypatch.setattr(datos.Supabase, "quitar_de_lista", lambda self, lista_id, r: quitados.append((lista_id, r)))
    at = correr(seccion="inicio")
    _, id_restaurante, _ = at.session_state["sugerencia"]
    at.session_state["ficha_abrir"] = id_restaurante
    at.run()
    at.session_state["ficha_abrir"] = id_restaurante
    at.button(key=f"quitar_de_lista_{id_restaurante}").click().run()   # primero pide confirmar
    assert quitados == []
    at.session_state["ficha_abrir"] = id_restaurante
    at.button(key=f"quitar_de_lista_si_{id_restaurante}").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert quitados == [(LISTA_OK["id"], id_restaurante)]


def test_quitar_de_lista_solo_borra_la_relacion(monkeypatch):
    bd_, llamadas = _supabase_falso(monkeypatch, lambda m, t, p: None)
    bd_.quitar_de_lista(1, np.int64(7))
    assert llamadas == [("DELETE", "lista_restaurantes", {"lista_id": "eq.1", "restaurante_id": "eq.7"}, None)]



# ---------------------------------------------------------------- Explorar (lugares de Overture)

def test_texto_busqueda():
    assert datos.texto_busqueda("  Sobrino de Botín (Cuchilleros)*,") == "sobrino de botin cuchilleros"
    assert datos.texto_busqueda("寿司 Ñandú") == "寿司 nandu"            # otras escrituras se conservan
    assert datos.texto_busqueda(None) == ""


def test_buscar_lugares_por_nombre_y_zona(monkeypatch):
    bd_, llamadas = _supabase_falso(monkeypatch, lambda m, t, p: [])
    assert bd_.buscar_lugares("  *, ") == [] and llamadas == []         # ni texto ni sitio: ni pregunta
    bd_.buscar_lugares("Casa*Labra,", cerca=(40.0, -3.7), radio_km=1.1132)
    metodo, tabla, params, _ = llamadas[-1]                             # (antes, una que mira si está la 012)
    assert (metodo, tabla) == ("GET", "lugares")
    assert params["nombre_busqueda"] == "ilike.*casa*labra*"            # sin comodines ni filtros colados
    assert params["and"].startswith("(lat.gte.39.990000,lat.lte.40.010000,lon.gte.-3.71")


def test_pedir_analisis_apunta_y_encola(monkeypatch):
    bd_, llamadas = _supabase_falso(monkeypatch, lambda m, t, p: None)
    bd_.pedir_analisis("ana@ejemplo.com", "x1")
    assert llamadas[0][:2] == ("POST", "solicitudes_analisis")
    assert llamadas[0][3] == {"lugar_id": "x1", "usuario": "ana@ejemplo.com"}
    assert llamadas[1][:2] == ("PATCH", "lugares")                       # si ya estaba analizado, no se toca
    assert llamadas[1][2] == {"id": "eq.x1", "estado_analisis": "in.(sin_analizar,error)"}


def test_lugares_pendientes_primero_los_mas_pedidos(monkeypatch):
    def respuestas(metodo, tabla, params):
        if tabla == "lugares":
            return [{"id": "a"}, {"id": "b"}, {"id": "c"}]               # del más antiguo al más nuevo
        return [{"lugar_id": "b"}, {"lugar_id": "b"}, {"lugar_id": "c"}]
    bd_, _ = _supabase_falso(monkeypatch, respuestas)
    assert [l["id"] for l in bd_.lugares_pendientes()] == ["b", "c", "a"]


def _lugar(id_, nombre, lat, lon, estado="sin_analizar", restaurante_id=None, web=None):
    return {"id": id_, "nombre": nombre, "categoria": "Tapas", "lat": lat, "lon": lon, "direccion": "C. Falsa 1",
            "ciudad": "Madrid", "pais": "ES", "web": web, "telefono": None, "estado_analisis": estado,
            "restaurante_id": restaurante_id}


@pytest.fixture
def explorar(multiusuario, monkeypatch):
    maestro = pd.read_excel(EXCEL, sheet_name="Restaurantes")
    id_analizado = int(maestro["ID"].iloc[0])
    estado = {"pedidos": [], "busquedas": [], "id_analizado": id_analizado, "lugares": [
        _lugar("l1", "Taberna Nueva", CHUECA[0] + 0.0004, CHUECA[1], web="javascript:alert(1)"),
        _lugar("l2", "Ya Analizado", CHUECA[0], CHUECA[1], "analizado", id_analizado)]}
    monkeypatch.setattr(datos.Supabase, "buscar_lugares", lambda self, texto="", cerca=None, radio_km=2.0, limite=200:
                        estado["busquedas"].append((texto, cerca)) or [dict(l) for l in estado["lugares"]])
    monkeypatch.setattr(datos.Supabase, "pedir_analisis", lambda self, u, i: estado["pedidos"].append((u, i)))
    monkeypatch.setattr(datos.Supabase, "solicitudes_de", lambda self, u, limite=20: [])
    monkeypatch.setattr(datos.Supabase, "restaurantes_por_ids", lambda self, ids: (
        maestro[maestro["ID"].isin(ids)].copy(), pd.DataFrame(columns=datos.COLUMNAS_PLATOS)))
    monkeypatch.setattr(datos.Supabase, "lugar_por_id", lambda self, i: next(
        dict(l) for l in estado["lugares"] if l["id"] == i))
    return estado


def descubrir(at=None):
    """Buscar -> Descubrir (antes, la sección Explorar)."""
    if at is None:   # (un AppTest sin ejecutar cuenta como "vacío": `at or ...` no sirve)
        at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["buscar_modo"] = "Descubrir"
    return correr(at, seccion="mi_lista")


def componente(at, contiene):
    """Los datos (en texto) del componente propio que lleva `contiene` ("" si no está)."""
    return next((str(c.proto) for c in at.get("bidi_component") if contiene in str(c.proto)), "")


def test_explorar_busca_cerca_y_pide_analizar(explorar):
    at = descubrir()
    assert not componente(at, "estado_texto")                           # sin texto ni ubicación: nada aún
    at.session_state["ubicacion_actual"] = CHUECA
    at.text_input(key="ex_texto").input("taberna").run()
    assert not at.exception, [e.value for e in at.exception]
    assert explorar["busquedas"][-1] == ("taberna", CHUECA)
    lista = componente(at, "estado_texto")                              # las tarjetas de Comer hoy
    assert lista.index("Ya Analizado") < lista.index("Taberna Nueva")    # el más cercano primero
    assert "44 m" in lista and "Analizado" in lista and "Datos b" in lista
    at.session_state["lugar_abrir"] = explorar["lugares"][0]            # lo que hace tocar su tarjeta
    at.run()                                                            # su ventana: datos básicos
    assert not at.exception, [e.value for e in at.exception]
    assert "analizar_lugar" in [b.key for b in at.button]
    assert not [b for b in at.get("link_button") if b.label == "Web"]    # javascript: no se enlaza
    at.button(key="analizar_lugar").click().run()
    assert explorar["pedidos"] == [("ana@ejemplo.com", "l1")]
    assert "lisis en camino" in componente(at, "estado_texto")           # se ve al momento


def test_explorar_en_mapa(explorar):
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["ubicacion_actual"] = CHUECA
    at.session_state["ex_vista"] = "Mapa"
    at = descubrir(at)
    mapa = componente(at, "mapa_explorar")
    assert "Taberna Nueva" in mapa and "Ya Analizado" in mapa and "analizado" in mapa   # pin verde
    assert not componente(at, "estado_texto")                           # en vez de la lista
    assert any("borde verde" in c.value for c in at.caption)


def test_explorar_un_sitio_analizado_abre_su_ficha_completa(explorar):
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["lugar_abrir"] = explorar["lugares"][1]
    at = descubrir(at)
    assert any(b.label == "Cómo llegar" for b in at.get("link_button"))
    assert f"he_ido_{explorar['id_analizado']}" in [b.key for b in at.button]   # con "He ido", eatlist...
    assert "analizar_lugar" not in [b.key for b in at.button]


def test_explorar_sin_la_tabla_avisa(multiusuario, monkeypatch):
    def falla(self, *a, **k):
        raise datos.ErrorSupabase("GET lugares: 404")
    monkeypatch.setattr(datos.Supabase, "buscar_lugares", falla)
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["ubicacion_actual"] = CHUECA
    at = descubrir(at)
    assert any("009_lugares.sql" in w.value for w in at.warning)


def test_buscar_tiene_mis_restaurantes_descubrir_y_personas(multiusuario):
    at = correr(seccion="mi_lista")
    modos = at.get("button_group")[0]
    assert "Mis restaurantes" in str(modos.proto) and "Descubrir" in str(modos.proto) and "Personas" in str(modos.proto)
    assert at.session_state["buscar_modo"] == "Mis restaurantes"


def test_buscar_lugares_no_ensena_los_cerrados(monkeypatch):
    bd_, llamadas = _supabase_falso(monkeypatch, lambda m, t, p: [])
    bd_.buscar_lugares("casa")
    assert llamadas[-1][2]["estado_analisis"] == "neq.cerrado"


def test_lugares_a_verificar_y_marcar_sin_la_012(monkeypatch):
    def respuestas(metodo, tabla, params):
        if params.get("select") == "ficha_en":
            raise datos.ErrorSupabase("GET lugares: 400 column ficha_en does not exist")
        return []
    bd_, llamadas = _supabase_falso(monkeypatch, respuestas)
    bd_.lugares_a_verificar(10, dias=30)
    params = llamadas[-1][2]
    assert params["order"] == "verificado_en.asc.nullsfirst" and params["estado_analisis"] == "neq.cerrado"
    assert params["or"].startswith("(verificado_en.is.null,verificado_en.lt.")
    bd_.marcar_verificado("a", cerrado=True)
    bd_.marcar_verificado("b", ficha={"nota_google": 4.3})
    assert llamadas[-2][3]["estado_analisis"] == "cerrado" and "verificado_en" in llamadas[-2][3]
    assert set(llamadas[-1][3]) == {"verificado_en"}                   # sin la 012: ni ficha_en ni ficha


def test_ficha_rapida_con_la_012(monkeypatch):
    bd_, llamadas = _supabase_falso(monkeypatch, lambda m, t, p: [])
    bd_.lugares_a_verificar(10)
    params = llamadas[-1][2]
    assert params["order"] == "ficha_en.asc.nullsfirst" and params["or"].startswith("(ficha_en.is.null,")   # primero los que no tienen
    bd_.marcar_verificado("b", ficha={"nota_google": 4.3, "cocina_google": "Taberna", "foto": "lugares/b.jpg"})
    cambios = llamadas[-1][3]
    assert cambios["ficha_en"] == cambios["verificado_en"] and cambios["nota_google"] == 4.3 and cambios["foto"] == "lugares/b.jpg"
    bd_.lugares_para_analizar(1)
    params = llamadas[-1][2]
    assert params["order"] == "nota_google.desc" and params["estado_analisis"] == "eq.sin_analizar"   # mejor nota primero
    assert params["restaurante_id"] == "is.null" and params["nota_google"] == "not.is.null"
    assert "nota_google" in bd_._columnas_lugar()


def test_restaurantes_cerca_pide_solo_la_zona(monkeypatch):
    bd_, llamadas = _supabase_falso(monkeypatch, lambda m, t, p: [
        {"id": 7, "datos": {"Nombre": "Casa Pepe"}, "platos": [{"Plato": "cachopo", "Sentimiento": "Buena"}], "imagen": None}])
    maestro, platos = bd_.restaurantes_cerca(40.0, -3.7, 1.1132)
    metodo, tabla, params, _ = llamadas[0]
    assert (metodo, tabla) == ("GET", "restaurantes") and params["and"].startswith("(lat.gte.39.990000,lat.lte.40.010000,")
    assert list(maestro["ID"]) == [7] and list(platos["Plato"]) == ["cachopo"]


def test_comer_hoy_todos_los_restaurantes_por_zona(multiusuario, monkeypatch):
    maestro = pd.read_excel(EXCEL, sheet_name="Restaurantes")
    platos = pd.read_excel(EXCEL, sheet_name="Platos mencionados")
    zonas = []
    monkeypatch.setattr(datos.Supabase, "con_ficha_rapida", lambda self: True)
    monkeypatch.setattr(datos.Supabase, "cocinas_del_catalogo", lambda self: (["Japonesa", "Tapas"], 5000))
    monkeypatch.setattr(datos.Supabase, "todos_los_restaurantes",
                        lambda self: pytest.fail("no debería descargar el catálogo entero"))
    monkeypatch.setattr(datos.Supabase, "restaurantes_cerca", lambda self, lat, lon, radio:
                        zonas.append((lat, lon, radio)) or (maestro.copy(), platos.copy()))
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["fuente"] = "Todos los restaurantes"
    at.session_state["ubicacion_actual"] = CHUECA
    at = correr(at)
    assert at.selectbox(key="cocina").options == ["Cualquiera", "Japonesa", "Tapas"]   # sin bajarse el catálogo
    at.button(key="boton_buscar").click().run()
    assert not at.exception, [e.value for e in at.exception]
    (lat, lon, radio), = zonas
    assert (lat, lon) == (round(CHUECA[0], 3), round(CHUECA[1], 3)) and radio == 20 * 1.3   # 20 min en coche
    assert at.session_state["resultado"]["df_puntuado"] is not None


def test_descubrir_ensena_la_ficha_rapida(explorar):
    explorar["lugares"][0].update(nota_google=4.6, cocina_google="Taberna", foto="lugares/l1.jpg")
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["ubicacion_actual"] = CHUECA
    at = descubrir(at)
    lista = componente(at, "estado_texto")
    assert "4,6" in lista and "Taberna" in lista and "lugares/l1.jpg" in lista   # nota, cocina y foto al momento
    at.session_state["ex_orden"] = "Mejor nota"
    at = descubrir(at)
    lista = componente(at, "estado_texto")
    assert lista.index("Taberna Nueva") < lista.index("Ya Analizado")    # la de mejor nota, primero


def test_avisar_de_que_ha_cerrado_lo_quita(explorar, monkeypatch):
    cerrados = []
    monkeypatch.setattr(datos.Supabase, "avisar_cerrado", lambda self, i: cerrados.append(i))
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["ubicacion_actual"] = CHUECA
    at = descubrir(at)
    assert "Taberna Nueva" in componente(at, "estado_texto")
    at.session_state["lugar_abrir"] = explorar["lugares"][0]
    at.run()
    at.button(key="avisar_cerrado").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert cerrados == ["l1"]
    lista = componente(at, "estado_texto")
    assert "Ya Analizado" in lista and "Taberna Nueva" not in lista    # ya no sale



def test_lugar_por_id(monkeypatch):
    bd_, llamadas = _supabase_falso(monkeypatch, lambda m, t, p: [{"id": "x"}])
    assert bd_.lugar_por_id("x") == {"id": "x"} and llamadas[0][2]["id"] == "eq.x"


def test_la_ventana_de_un_sitio_en_analisis_se_actualiza_sola(explorar, monkeypatch):
    pendiente = {**explorar["lugares"][0], "estado_analisis": "pendiente"}
    estado_bd = {"lugar": dict(pendiente)}
    monkeypatch.setattr(datos.Supabase, "lugar_por_id", lambda self, i: dict(estado_bd["lugar"]))
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["lugar_abrir"] = pendiente
    at = descubrir(at)
    assert any("se actualiza sola" in i.value for i in at.info)            # aún analizándose
    assert "analizar_lugar" not in [b.key for b in at.button]
    # el procesador termina: la próxima vez que la ventana mira, se abre con la ficha completa
    estado_bd["lugar"] = {**pendiente, "estado_analisis": "analizado", "restaurante_id": explorar["id_analizado"]}
    at.session_state["lugar_abrir"] = pendiente                            # (AppTest: se vuelve a abrir la ventana)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert any(b.label == "Cómo llegar" for b in at.get("link_button"))
    assert f"he_ido_{explorar['id_analizado']}" in [b.key for b in at.button]


def test_un_sitio_que_ha_cerrado_lo_dice(explorar, monkeypatch):
    cerrado = {**explorar["lugares"][0], "estado_analisis": "cerrado"}
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["lugar_abrir"] = cerrado
    at = descubrir(at)
    assert any("ha cerrado" in w.value for w in at.warning) and "analizar_lugar" not in [b.key for b in at.button]



# ---------------------------------------------------------------- "He ido con..." (comensales)

def test_invitaciones_de_comensal_en_la_base_de_datos(monkeypatch):
    from datetime import date
    bd_, llamadas = _supabase_falso(monkeypatch, lambda m, t, p: None)
    bd_.invitar_comensales("ana@x.com", 7, ["luis@x.com", "luis@x.com", "ana@x.com"], fecha=date(2026, 10, 12))
    metodo, tabla, params, cuerpo = llamadas[0]
    assert (metodo, tabla) == ("POST", "invitaciones_visita")              # a él aún no le sale nada
    assert cuerpo == [{"de": "ana@x.com", "para": "luis@x.com", "restaurante_id": 7, "fecha": "2026-10-12"}]
    llamadas.clear()
    bd_.aceptar_invitacion("luis@x.com", "ana@x.com", 7, 4.5, "Rico", fecha=date(2026, 10, 12))
    (m1, t1, p1, visita), (m2, t2, p2, _) = llamadas
    assert (m1, t1, p1) == ("POST", "visitas", {"on_conflict": "usuario,restaurante_id"})   # su única entrada
    assert {k: visita[k] for k in ("usuario", "nota", "comentario", "anadido_por")} == {
        "usuario": "luis@x.com", "nota": 4.5, "comentario": "Rico", "anadido_por": "ana@x.com"}
    assert (m2, t2, p2) == ("DELETE", "invitaciones_visita", {"de": "eq.ana@x.com", "para": "eq.luis@x.com",
                                                              "restaurante_id": "eq.7"})
    llamadas.clear()
    bd_.registrar_visita("ana@x.com", 7)
    assert "anadido_por" not in llamadas[0][3]                              # funciona sin 011_comensales.sql


def test_he_ido_con_un_amigo_le_pregunta_a_el(multiusuario):
    multiusuario["relaciones"] = [LUIS, {**LUIS, "usuario": "eva@x.com", "alias": "eva", "estado": "pendiente"}]
    at = correr(seccion="inicio")
    _, id_restaurante, _ = at.session_state["sugerencia"]
    at.session_state["ficha_abrir"] = id_restaurante
    at.run()
    abrir_ventana_he_ido(at, id_restaurante)
    elegir = at.multiselect(key=f"comensales_elegidos_{id_restaurante}")
    assert elegir.options == ["Luis · @luis"]                              # solo amigos aceptados y sin correos
    at.session_state["ficha_abrir"] = id_restaurante
    elegir.select(0).run()
    at.session_state["ficha_abrir"] = id_restaurante
    at.button(key=f"visita_guardar_{id_restaurante}").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert [v[:2] for v in multiusuario["visitas_guardadas"]] == [("ana@ejemplo.com", id_restaurante)]
    assert [e[:3] for e in multiusuario["invitaciones_enviadas"]] == [("ana@ejemplo.com", id_restaurante, ["luis@x.com"])]


def test_invitacion_pendiente_se_ve_y_se_puede_quitar(multiusuario):
    multiusuario.update(relaciones=[LUIS], invitados=["luis@x.com"])
    at = correr(seccion="inicio")
    _, id_restaurante, _ = at.session_state["sugerencia"]
    at.session_state["ficha_abrir"] = id_restaurante
    at.run()
    abrir_ventana_he_ido(at, id_restaurante)
    assert any("@luis" in c.value and "pendiente" in c.value for c in at.caption)
    at.session_state["ficha_abrir"] = id_restaurante
    at.button(key=f"comensal_quitar_{id_restaurante}_0").click().run()
    assert multiusuario["invitaciones_borradas"] == [("ana@ejemplo.com", "luis@x.com", id_restaurante)]


def invitacion_de_luis(multiusuario, monkeypatch, id_restaurante):
    maestro = pd.read_excel(EXCEL, sheet_name="Restaurantes")
    monkeypatch.setattr(datos.Supabase, "restaurantes_por_ids", lambda self, ids: (
        maestro[maestro["ID"].isin(ids)].copy(), pd.DataFrame(columns=datos.COLUMNAS_PLATOS)))
    multiusuario.update(relaciones=[LUIS], invitaciones=[{
        "de": "luis@x.com", "restaurante_id": id_restaurante, "fecha": "2026-10-12",
        "restaurantes": {"id": id_restaurante, "datos": {"Nombre": "Casa Pepe"}}}])
    st.cache_data.clear()   # la lista de amigos ya estaba en caché (vacía)


def test_aceptar_invitacion_pone_tus_estrellas_y_comentario(multiusuario, monkeypatch):
    at = correr(seccion="inicio")
    _, id_restaurante, _ = at.session_state["sugerencia"]
    invitacion_de_luis(multiusuario, monkeypatch, id_restaurante)
    at.run()
    assert any("dice que fuisteis juntos a **Casa Pepe** el 12/10/2026" in m.value for m in at.markdown)
    assert multiusuario["visitas_guardadas"] == []                          # hasta que no aceptas, nada
    at.button(key="invitacion_si_0").click().run()                          # abre la ficha con la ventanita
    assert not at.exception, [e.value for e in at.exception]
    assert str(at.date_input(key=f"fecha_visita_{id_restaurante}").value) == "2026-10-12"
    at.session_state["ficha_invitacion"] = id_restaurante                   # (AppTest: se vuelve a abrir)
    at.text_area(key=f"comentario_visita_{id_restaurante}").input("Muy rico")
    at.session_state["ficha_invitacion"] = id_restaurante
    at.button(key=f"visita_guardar_{id_restaurante}").click().run()
    assert not at.exception, [e.value for e in at.exception]
    (u, de, i, nota, comentario, fecha), = multiusuario["invitaciones_aceptadas"]
    assert (u, de, i, comentario, str(fecha)) == ("ana@ejemplo.com", "luis@x.com", id_restaurante, "Muy rico", "2026-10-12")
    assert multiusuario["visitas_guardadas"] == []                          # una sola entrada: la de la invitación


def test_rechazar_invitacion(multiusuario, monkeypatch):
    at = correr(seccion="inicio")
    _, id_restaurante, _ = at.session_state["sugerencia"]
    invitacion_de_luis(multiusuario, monkeypatch, id_restaurante)
    at.run()
    at.button(key="invitacion_no_0").click().run()
    assert multiusuario["invitaciones_borradas"] == [("luis@x.com", "ana@ejemplo.com", id_restaurante)]
    assert multiusuario["visitas_guardadas"] == [] and multiusuario["invitaciones_aceptadas"] == []


def test_al_amigo_le_dice_con_quien_fue(multiusuario):
    multiusuario.update(relaciones=[LUIS], anadido_por="luis@x.com")
    at = correr(seccion="inicio")
    _, id_restaurante, _ = at.session_state["sugerencia"]
    at.session_state["ficha_abrir"] = id_restaurante
    at.run()
    abrir_ventana_he_ido(at, id_restaurante)
    assert any("Fuiste con" in c.value and "@luis" in c.value for c in at.caption)
    assert "luis@x.com" not in str(at)                                     # el correo no sale
