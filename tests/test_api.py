"""API de la app móvil (api/principal.py) con una base de datos falsa en memoria: sin red ni Supabase."""

import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient  # noqa: E402

import amigos  # noqa: E402
import cuentas  # noqa: E402
from api import principal  # noqa: E402
import base  # noqa: E402  (api/base.py: lo añade al path api/principal.py)
import social  # noqa: E402

YO, OTRA, TERCERA = "yo@ejemplo.com", "otra@ejemplo.com", "tercera@ejemplo.com"


def _restaurante(id_, nombre, cocina, precio, nota, lat, lon):
    return {"id": id_, "imagen": f"restaurantes/{id_}.jpg", "platos": [{"Plato": "croquetas", "Sentimiento": "Buena"}],
            "datos": {"Nombre": nombre, "Categoría (Jev)": cocina, "Rango de precios": precio, "Puntuación": nota,
                      "Nº Reseñas": 100, "Latitud": lat, "Longitud": lon, "Dirección": "Calle Falsa 1",
                      "Platos mejor valorados": "croquetas (5), tortilla (2)"}}


CATALOGO = {1: _restaurante(1, "Casa Pepe", "Española", "10-20 €", 4.5, 40.42, -3.70),
            2: _restaurante(2, "Sushi Ya", "Japonesa", "30-40 €", 4.1, 40.43, -3.69)}


class BDFalsa:
    def __init__(self):
        self.visitas, self.eatlist, self.quitados = {}, [], []
        self.amistades = {OTRA: ("pendiente", False)}   # otro -> (estado, enviada por mí)
        self.invitaciones, self.invitados, self.perfil, self.borrado = [], [], {}, None

    def url_foto(self, archivo):
        return f"https://fotos.ejemplo/{archivo}"

    def perfil_de(self, usuario):
        return {"nombre": "Yo", "alias": "yo", "foto": None, **self.perfil} if usuario == YO else None

    def guardar_perfil(self, usuario, nombre, preferencias=None):
        from datos import preferencias_validas
        self.perfil["nombre"] = nombre
        if preferencias is not None:
            self.perfil["preferencias"] = preferencias_validas(preferencias)
        return {"usuario": usuario, "nombre": nombre, **self.perfil}

    def directorio(self, excepto, limite=1000):
        return [{"usuario": OTRA, "nombre": "Otra", "alias": "otra"},
                {"usuario": TERCERA, "nombre": "Tercera Persona", "alias": "tercera"}]

    def solicitar_amistad(self, de, a):
        self.amistades[a] = ("pendiente", True)
        return "pendiente"

    def responder_solicitud(self, usuario, de, aceptar):
        self.amistades[de] = ("aceptada", False)

    def quitar_amistad(self, usuario, otro):
        self.amistades.pop(otro, None)

    def amistades_aceptadas_de(self, usuarios):
        return []

    def invitaciones_para(self, usuario):
        return self.invitaciones

    def borrar_invitacion(self, de, para, restaurante_id):
        self.invitaciones = [i for i in self.invitaciones if (i["de"], i["restaurante_id"]) != (de, restaurante_id)]

    def aceptar_invitacion(self, usuario, de, restaurante_id, nota=None, comentario=None, fecha=None):
        self.registrar_visita(usuario, restaurante_id, nota, comentario, fecha)
        self.borrar_invitacion(de, usuario, restaurante_id)

    def invitar_comensales(self, usuario, restaurante_id, amigos, fecha=None):
        self.invitados += list(amigos)

    def borrar_usuario(self, usuario):
        self.borrado = usuario

    def restaurantes_de(self, usuario):
        from datos import filas_a_dataframes
        filas = [{"posicion": n, "anadido_en": "2026-01-02T10:00:00+00:00", "restaurantes": CATALOGO[i]}
                 for n, i in enumerate((1, 2)) if i not in self.quitados]
        maestro, platos = filas_a_dataframes(filas)
        return maestro, platos, {"id": 7, "estado": "lista", "mensaje": None}

    def restaurantes_por_ids(self, ids):
        from datos import filas_a_dataframes
        return filas_a_dataframes([{"posicion": n, "restaurantes": CATALOGO[i]} for n, i in enumerate(ids) if i in CATALOGO])

    def relaciones_de(self, usuario):
        nombres = {OTRA: "Otra", TERCERA: "Tercera Persona"}
        return [{"usuario": o, "nombre": nombres[o], "alias": nombres[o].split()[0].lower(), "foto": None,
                 "estado": e, "enviada": env} for o, (e, env) in self.amistades.items()]

    def eatlist_de(self, usuario):
        return [{"posicion": n, "restaurantes": CATALOGO[i]} for n, i in enumerate(self.eatlist, 1)]

    def guardar_eatlist(self, usuario, ids):
        self.eatlist = list(ids)

    def fotos_de(self, restaurante_id):
        return ["galeria/1-1.jpg"]

    def visitas_de(self, usuarios, limite=10, desde=None):
        return [{"usuario": YO, "nota": v["nota"], "comentario": v["comentario"], "creado_en": "2026-01-03T14:00:00+01:00",
                 "restaurantes": CATALOGO[rid]} for rid, v in self.visitas.items()]

    def registrar_visita(self, usuario, restaurante_id, nota=None, comentario=None, fecha=None, anadido_por=None):
        from datos import momento_visita, validar_comentario, validar_nota
        momento_visita(fecha)   # como la de verdad: fecha futura -> ValueError
        self.visitas[restaurante_id] = {"nota": validar_nota(nota), "comentario": validar_comentario(comentario)}

    def quitar_visita(self, usuario, restaurante_id):
        self.visitas.pop(restaurante_id, None)

    def resenas_de(self, restaurante_id, limite=100):
        return [{"usuario": OTRA, "nota": 4.0, "comentario": "Muy rico", "creado_en": "2026-01-04T14:00:00+01:00"}]

    def perfiles_de(self, usuarios):
        return {OTRA: {"nombre": "Otra", "alias": "otra"}}

    def quitar_de_lista(self, lista_id, restaurante_id):
        self.quitados.append(restaurante_id)

    def con_deslizar(self):
        return False


class CuentasFalsas:
    borrados = []

    def usuario(self, token):
        if token != "bueno":
            raise cuentas.ErrorCuenta("La sesión ha caducado.")
        return {"id": "id-yo", "correo": YO, "nombre": "Yo"}

    def entrar(self, correo, contrasena):
        raise cuentas.ErrorCuenta("Correo o contraseña incorrectos.")

    def borrar_usuario(self, id_usuario):
        self.borrados.append(id_usuario)


@pytest.fixture
def cliente(monkeypatch):
    bd = BDFalsa()
    principal.app.dependency_overrides = {principal.obtener_bd: lambda: bd,
                                          principal.obtener_cuentas: lambda: CuentasFalsas()}
    principal._tokens.clear()
    principal._listas.clear()
    base._usos.clear()
    social._mazos.clear()
    CuentasFalsas.borrados = []
    amigos.limpiar_cache()
    # tiempos de viaje: el primero a 10 min y el segundo a 40 (sin llamar a OSRM)
    monkeypatch.setattr(principal, "obtener_minutos_coche", lambda origen, maestro: [10, 40][:len(maestro)])
    c = TestClient(principal.app, headers={"Authorization": "Bearer bueno"})
    c.bd = bd
    yield c
    principal.app.dependency_overrides = {}


def test_sin_sesion_o_token_malo_da_401(cliente):
    assert TestClient(principal.app).get("/yo").status_code == 401
    assert cliente.get("/yo", headers={"Authorization": "Bearer malo"}).status_code == 401


def test_yo(cliente):
    yo = cliente.get("/yo").json()
    assert yo["alias"] == "yo" and yo["lista"]["total"] == 2 and yo["solicitudes"] == 1
    assert yo["preferencias"]["transporte"] == "En coche"


def test_inicio_fotos_de_la_cinta_y_sin_idea_con_pocas_menciones(cliente):
    r = cliente.get("/inicio").json()
    assert sorted(r["portada"]) == ["https://fotos.ejemplo/restaurantes/1.jpg", "https://fotos.ejemplo/restaurantes/2.jpg"]
    assert r["idea"] is None   # cada plato sale una vez: sugerencia_plato pide al menos 2 menciones buenas


def test_buscar_solo_los_que_cumplen_todo(cliente):
    r = cliente.post("/buscar", json={"lat": 40.42, "lon": -3.70, "minutos": 20}).json()
    assert [x["nombre"] for x in r["resultados"]] == ["Casa Pepe"]   # Sushi Ya está a 40 min
    assert r["resultados"][0]["minutos"] == 10 and r["resultados"][0]["foto"] == "https://fotos.ejemplo/restaurantes/1.jpg"
    r = cliente.post("/buscar", json={"lat": 40.42, "lon": -3.70, "minutos": 60, "cocina": "Japonesa"}).json()
    assert [x["nombre"] for x in r["resultados"]] == ["Sushi Ya"]


def test_buscar_valida_lo_que_llega(cliente):
    assert cliente.post("/buscar", json={"lat": 40.4, "lon": -3.7, "minutos": 500}).status_code == 422


def test_lista_con_filtros_y_resumen(cliente):
    r = cliente.get("/lista", params={"presupuesto_max": 25}).json()
    assert [x["nombre"] for x in r["restaurantes"]] == ["Casa Pepe"] and r["total"] == 2
    assert r["resumen"]["cocinas"] == {"Española": 1, "Japonesa": 1}
    assert r["restaurantes"][0]["anadido_en"].startswith("2026-01-02")


def test_ficha(cliente):
    f = cliente.get("/restaurantes/1", params={"plato": "croquetas"}).json()
    assert f["en_mi_lista"] and f["platos"] == ["croquetas", "tortilla"] and f["num_resenas"] == 1
    assert f["fotos"] == ["https://fotos.ejemplo/galeria/1-1.jpg"] and "Mencionado 1 veces" in f["sobre_plato"]
    assert cliente.get("/restaurantes/99").status_code == 404


def test_resenas_sin_correos(cliente):
    texto = cliente.get("/restaurantes/1/resenas").text
    assert "Muy rico" in texto and "@ejemplo.com" not in texto


def test_he_ido_guardar_y_quitar(cliente):
    assert cliente.put("/visitas/1", json={"nota": 4.5, "comentario": "Genial"}).json()["ok"]
    assert cliente.get("/restaurantes/1").json()["mi_visita"]["nota"] == 4.5
    assert cliente.put("/visitas/1", json={"nota": 9}).status_code == 422
    cliente.delete("/visitas/1")
    assert cliente.get("/visitas").json() == {"visitas": []}


def test_eatlist(cliente):
    cliente.put("/eatlist", json={"ids": [2, 1]})
    assert [x["id"] for x in cliente.get("/eatlist").json()["restaurantes"]] == [2, 1]
    assert cliente.get("/restaurantes/2").json()["en_eatlist"]


def test_quitar_de_mi_lista(cliente):
    cliente.delete("/lista/2")
    assert cliente.get("/yo").json()["lista"]["total"] == 1


def test_enlace_de_lista_no_valido(cliente):
    assert cliente.post("/lista/enlace", json={"enlace": "https://malicioso.com"}).status_code == 400


def test_plato_con_simbolos_no_rompe_la_busqueda(cliente):   # se busca como texto, no como expresión regular
    r = cliente.post("/buscar", json={"lat": 40.42, "lon": -3.70, "minutos": 60, "plato": "(a+)+$"})
    assert r.status_code == 200 and r.json()["resultados"] == []


def test_token_vacio_da_401(cliente):
    assert cliente.get("/yo", headers={"Authorization": "Bearer  "}).status_code == 401


def test_visita_con_fecha_futura_da_400_con_mensaje(cliente):
    r = cliente.put("/visitas/1", json={"nota": 4, "fecha": "2999-01-01"})
    assert r.status_code == 400 and "no ha llegado" in r.json()["detail"]


def test_ids_fuera_de_rango_y_lugares_raros(cliente):
    assert cliente.get("/restaurantes/0").status_code == 422
    assert cliente.post("/lugares/a,b)/analizar").status_code in (404, 422)
    assert cliente.get("/lugares", params={"lat": "nan", "lon": 3}).status_code == 422


def test_avisar_cerrado(cliente, monkeypatch):
    avisados = []
    monkeypatch.setattr(cliente.bd, "lugar_por_id", lambda i: {"id": i} if i == "a" else None, raising=False)
    monkeypatch.setattr(cliente.bd, "avisar_cerrado", avisados.append, raising=False)
    assert cliente.post("/lugares/zz/cerrado").status_code == 404
    assert cliente.post("/lugares/a/cerrado").json() == {"ok": True} and avisados == ["a"]


def test_tus_datos_cabecera_y_tarjetas(cliente):
    cliente.put("/visitas/1", json={"nota": 4.5})
    d = cliente.get("/yo/datos").json()
    assert (d["idos"], d["en_lista"], d["amigos"]) == (1, 2, 0)
    textos = [t["texto"] for t in d["tarjetas"]]
    assert "De tu lista ya probado" in textos and "Tu nota media" in textos
    assert next(t for t in d["tarjetas"] if t["texto"] == "De tu lista ya probado")["valor"] == "50 %"


def test_lugares_en_zona_con_filtro_de_cocina_e_icono(cliente, monkeypatch):
    pedidos = []
    sitios = [{"id": "a", "nombre": "Sushi Uno", "lat": 40.42, "lon": -3.70, "categoria": "Japonesa", "estado_analisis": None},
              {"id": "b", "nombre": "Bar Pepe", "lat": 40.421, "lon": -3.70, "categoria": "Bar", "estado_analisis": None}]

    def buscar_lugares(texto="", cerca=None, radio_km=2.0, limite=200):
        pedidos.append(radio_km)
        return sitios
    monkeypatch.setattr(cliente.bd, "buscar_lugares", buscar_lugares, raising=False)
    import explorar
    explorar._en_zona.clear()
    r = cliente.get("/lugares", params={"lat": 40.42, "lon": -3.70, "zona": True, "cocinas": ["Japonesa"]}).json()
    assert pedidos == [explorar.RADIO_ZONA_KM]            # zona: todo lo que hay a ~1 km
    assert [l["id"] for l in r["lugares"]] == ["a"] and r["lugares"][0]["icono"] == "🍣"
    assert r["cocinas"] == ["Bar", "Japonesa"] and r["total"] == 2   # las opciones salen de todo lo encontrado
    assert cliente.get("/lugares", params={"zona": True}).json()["lugares"] == []   # zona sin punto: nada


# ----------------------- amigos, notificaciones, perfil y cuenta (api/social.py) ----------------------- #

def _sin_correos(respuesta):
    assert "@ejemplo.com" not in respuesta.text
    return respuesta.json()


def test_buscar_personas_sin_correos_y_con_su_estado(cliente):
    r = _sin_correos(cliente.get("/personas", params={"q": "perso"}))
    assert [(p["alias"], p["estado"]) for p in r["personas"]] == [("tercera", "nuevo")]
    assert _sin_correos(cliente.get("/personas", params={"q": "@otra"}))["personas"][0]["estado"] == "recibida"


def test_solicitud_aceptar_y_perfil_de_amigo(cliente):
    assert cliente.post("/personas/tercera/amistad").json() == {"estado": "enviada"}
    assert _sin_correos(cliente.get("/amigos"))["enviadas"][0]["alias"] == "tercera"
    assert set(cliente.get("/personas/otra").json()) == {"alias", "nombre", "inicial", "color", "foto", "estado"}
    cliente.post("/personas/otra/aceptar")
    perfil = _sin_correos(cliente.get("/personas/otra"))
    assert perfil["estado"] == "amigo" and "afinidad" in perfil and perfil["en_comun_total"] == 2
    assert cliente.get("/personas/nadie").status_code == 404


def test_solo_se_invita_a_amigos_y_se_quita_de_la_eatlist(cliente):
    cliente.put("/eatlist", json={"ids": [1]})
    assert cliente.put("/visitas/1", json={"nota": 4, "con": ["otra"]}).status_code == 400   # aún no es amiga
    cliente.bd.amistades[OTRA] = ("aceptada", False)
    amigos.limpiar_cache()
    assert cliente.put("/visitas/1", json={"nota": 4, "con": ["otra"]}).json()["invitados"] == 1
    assert cliente.bd.invitados == [OTRA] and cliente.get("/eatlist").json()["restaurantes"] == []


def test_notificacion_aceptar(cliente):
    cliente.bd.amistades[OTRA] = ("aceptada", False)
    cliente.bd.invitaciones = [{"de": OTRA, "restaurante_id": 2, "fecha": "2026-01-05",
                                "restaurantes": {"id": 2, "datos": CATALOGO[2]["datos"]}}]
    n = _sin_correos(cliente.get("/notificaciones"))["notificaciones"]
    assert n[0]["de"]["alias"] == "otra" and n[0]["restaurante"] == "Sushi Ya"
    assert cliente.get("/yo").json()["notificaciones"] == 1
    assert cliente.post("/notificaciones/otra/2", json={"nota": 5}).json() == {"ok": True}
    assert cliente.bd.visitas[2]["nota"] == 5 and cliente.get("/notificaciones").json()["notificaciones"] == []
    assert cliente.post("/notificaciones/otra/2", json={}).status_code == 404


def test_editar_perfil_valida(cliente):
    assert cliente.put("/yo/nombre", json={"nombre": "<b>"}).status_code == 400
    assert cliente.put("/yo/nombre", json={"nombre": "  Ana  "}).json() == {"ok": True}
    assert cliente.bd.perfil["nombre"] == "Ana"
    assert cliente.put("/yo/alias", json={"alias": "a"}).status_code == 400
    r = cliente.put("/yo/preferencias", json={"transporte": "A pie", "tiempo": 15, "presupuesto": [10, 40]}).json()
    assert r["preferencias"]["transporte"] == "A pie" and r["preferencias"]["tiempo"] == 15
    assert cliente.put("/yo/foto", json={"imagen": "data:text/html;base64,AAAA"}).status_code == 400


def test_borrar_cuenta_pide_confirmacion(cliente):
    assert cliente.post("/yo/borrar", json={"confirmacion": "si"}).status_code == 422
    assert cliente.post("/yo/borrar", json={"confirmacion": "BORRAR"}).json() == {"ok": True}
    assert cliente.bd.borrado == YO and CuentasFalsas.borrados == ["id-yo"]


def test_limite_de_intentos_al_entrar(cliente):
    codigos = [cliente.post("/auth/entrar", json={"correo": "a@b.es", "contrasena": "x"}).status_code for _ in range(11)]
    assert codigos[:10] == [400] * 10 and codigos[10] == 429


def test_food_match_sin_migracion_da_404(cliente):
    assert cliente.get("/deslizar").status_code == 404
