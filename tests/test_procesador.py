"""Procesador de listas (obtener_datos/procesar_solicitudes.py) con una base de datos falsa en
memoria y sin navegador: descarga y análisis sustituidos. Necesita las dependencias del proceso
de datos (bs4, playwright); si no están, se salta."""

import sys
from pathlib import Path

import pytest

pytest.importorskip("bs4")
pytest.importorskip("playwright")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "obtener_datos"))
import procesar_solicitudes as ps  # noqa: E402

ENLACE = "https://maps.app.goo.gl/5QLC8VhBqetTCbjGA"


class BDFalsa:
    def __init__(self, catalogo=None, listas=None):
        self.catalogo = dict(catalogo or {})          # clave -> fila
        self.listas = listas or []
        self.estados, self.contenido, self.siguiente_id = [], {}, 100

    def marcar(self, lista_id, estado, mensaje=None):
        self.estados.append((lista_id, estado))

    def restaurantes_por_clave(self, claves):
        return {c: self.catalogo[c] for c in claves if c in self.catalogo}

    def guardar_restaurantes(self, filas):
        for f in filas:
            anterior = self.catalogo.get(f["clave"], {})
            self.catalogo[f["clave"]] = {**f, "id": anterior.get("id") or self._nuevo_id()}
        return {f["clave"]: self.catalogo[f["clave"]]["id"] for f in filas}

    def reemplazar_lista(self, lista_id, ids):
        self.contenido[lista_id] = list(ids)

    def subir_foto(self, archivo, contenido):
        pass

    def listas_pendientes(self):
        return self.listas

    def lugares_pendientes(self):
        return getattr(self, "lugares", [])

    def marcar_lugar(self, lugar_id, estado, restaurante_id=None, mensaje=None):
        self.estados.append((lugar_id, estado, restaurante_id))

    def _nuevo_id(self):
        self.siguiente_id += 1
        return self.siguiente_id


def fila_lista(nombre, **extra):
    return {"Nombre": nombre, "Puntuación": 4.5, "Nº Reseñas": 100, "Rango de precios": "20-30 €",
            "Tipo de cocina": "Restaurante", "Estado": "", "Imagen URL": "https://x/foto", **extra}


@pytest.fixture
def analizados(monkeypatch):
    """Sustituye el análisis de restaurantes nuevos (fotos, reseñas, Jev) y apunta a cuáles se piden."""
    pedidos = []

    def analizar(filas, resenas=None):
        pedidos.extend(f["Nombre"] for f in filas)
        return [{"clave": ps.datos.clave_restaurante(f["Nombre"]), "datos": {"Nombre": f["Nombre"]},
                 "platos": [], "imagen": None} for f in filas]

    monkeypatch.setattr(ps, "analizar_nuevos", analizar)
    return pedidos


def test_reutiliza_el_catalogo_y_analiza_solo_los_nuevos(monkeypatch, analizados):
    existente = {"id": 7, "clave": "casa pepe", "imagen": "casa-pepe.jpg",
                 "platos": [{"Plato": "cachopo", "Sentimiento": "Buena"}],
                 "datos": {"Nombre": "Casa Pepe", "Rango de precios": "10-20 €", "Estado": "Cerrado temporalmente",
                           "Categoría (Jev)": "Española"}}
    bd = BDFalsa(catalogo={"casa pepe": existente})
    monkeypatch.setattr(ps, "descargar_filas", lambda enlace: [
        fila_lista("Nuevo Sitio"), fila_lista("Casa Pepe"), fila_lista("Nuevo  Sitio")])   # el 3º repite clave

    resumen = ps.procesar_lista(bd, {"id": 1, "usuario": "ana@ejemplo.com", "enlace": ENLACE})

    assert analizados == ["Nuevo Sitio"]                                   # Casa Pepe no se re-analiza
    actualizado = bd.catalogo["casa pepe"]
    assert actualizado["datos"]["Rango de precios"] == "20-30 €"           # refrescado desde la lista
    assert actualizado["datos"]["Estado"] == ""                            # ha reabierto
    assert actualizado["datos"]["Categoría (Jev)"] == "Española"           # el análisis se conserva
    assert actualizado["platos"] and actualizado["imagen"] == "casa-pepe.jpg"
    assert bd.contenido[1] == [bd.catalogo["nuevo sitio"]["id"], 7]        # orden de Google, sin repetidos
    assert bd.estados == [(1, "procesando"), (1, "lista")]
    assert resumen == "2 restaurantes (1 nuevos)"


def test_resenas_en_varias_pestanas_mantienen_el_orden(monkeypatch):
    import asyncio
    import random

    class PaginaFalsa:
        async def goto(self, *a, **k):
            pass

    class ContextoFalso:
        def __init__(self):
            self.pages = [PaginaFalsa()]

        async def new_page(self):
            self.pages.append(PaginaFalsa())
            return self.pages[-1]

        async def close(self):
            pass

    contexto = ContextoFalso()
    usadas, vistos = set(), []

    async def abrir(p):
        return contexto

    async def asegurar(page, url):
        pass

    async def procesar(page, nombre, i, total, cerca=None):
        usadas.add(id(page))
        vistos.append(nombre)
        await asyncio.sleep(random.uniform(0, 0.02))   # terminan en distinto orden
        return [{"Restaurante": nombre, "Texto": f"reseña {k}"} for k in range(2)]

    class PlaywrightFalso:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *a):
            return False

    import playwright.async_api
    monkeypatch.setattr(playwright.async_api, "async_playwright", lambda: PlaywrightFalso())
    monkeypatch.setattr(ps.extraer_html, "_abrir_chrome_con_sesion", abrir)
    monkeypatch.setattr(ps.extraer_html, "_asegurar_sesion", asegurar)
    monkeypatch.setattr(ps.extraer_resenas, "procesar_restaurante", procesar)

    nombres = [f"Sitio {n}" for n in range(10)]
    filas = asyncio.run(ps._resenas_de(nombres, pestanas=3))
    assert sorted(vistos) == sorted(nombres) and len(vistos) == 10      # cada uno, una vez
    assert len(usadas) == 3                                             # se han usado las 3 pestañas
    assert [f["Restaurante"] for f in filas] == [n for n in nombres for _ in range(2)]   # orden original


def test_enlace_no_valido_no_abre_el_navegador(monkeypatch, analizados):
    monkeypatch.setattr(ps, "descargar_filas", lambda enlace: pytest.fail("no debería descargar nada"))
    with pytest.raises(ps.ErrorLista):
        ps.procesar_lista(BDFalsa(), {"id": 1, "usuario": "x", "enlace": "https://evil.com/lista"})


def test_lista_vacia_es_un_error(monkeypatch, analizados):
    monkeypatch.setattr(ps, "descargar_filas", lambda enlace: [])
    with pytest.raises(ps.ErrorLista):
        ps.procesar_lista(BDFalsa(), {"id": 1, "usuario": "x", "enlace": ENLACE})


def test_un_fallo_no_para_las_demas_listas(monkeypatch, analizados):
    listas = [{"id": 1, "usuario": "mala@ejemplo.com", "enlace": "https://evil.com"},
              {"id": 2, "usuario": "buena@ejemplo.com", "enlace": ENLACE}]
    bd = BDFalsa(listas=listas)
    monkeypatch.setattr(ps, "cliente", lambda: bd)
    monkeypatch.setattr(ps, "descargar_filas", lambda enlace: [fila_lista("Sitio")])
    ps.main([])
    assert (1, "error") in bd.estados
    assert (2, "lista") in bd.estados and bd.contenido[2]


# ---------------------------------------------------------------- Explorar: restaurantes sueltos

def lugar(id_, nombre, lat=40.42, lon=-3.70):
    return {"id": id_, "nombre": nombre, "lat": lat, "lon": lon, "categoria": "Japonesa"}


@pytest.fixture
def fichas(monkeypatch):
    """Sustituye la búsqueda en Google Maps: lo que "se lee" de cada ficha (o que no se encuentra)."""
    leidos = []

    async def resenas(nombres, pestanas=None, cercas=None):
        leidos.extend(zip(nombres, cercas))
        return [{"Restaurante": n, "Estado": "NO ENCONTRADO"} if n == "Fantasma" else
                {"Restaurante": n, "Estado": "CERRADO"} if n == "Cerrado Ya" else
                {"Restaurante": n, "Estado": "OK", "Rating Google": 4.4, "Ficha precio": "20-30 €",
                 "Ficha cocina": "", "Ficha foto": "https://lh3.googleusercontent.com/x", "Texto": "rico"}
                for n in nombres]
    monkeypatch.setattr(ps, "_resenas_de", resenas)
    return leidos


def test_lugares_ya_en_el_catalogo_se_enlazan_sin_analizar(analizados, fichas):
    mismo = {"id": 7, "clave": "kabuki", "datos": {"Nombre": "Kabuki", "Latitud": 40.4201, "Longitud": -3.7001}}
    otro = {"id": 8, "clave": "casa pepe", "datos": {"Nombre": "Casa Pepe", "Latitud": 41.6, "Longitud": -0.9}}
    bd = BDFalsa(catalogo={"kabuki": mismo, "casa pepe": otro})

    ps.procesar_lugares(bd, [lugar("a", "Kabuki"), lugar("b", "Casa Pepe"), lugar("c", "Fantasma"),
                             lugar("d", "Casa  Pepe")])   # "d" repite nombre con "b": a la próxima vuelta

    assert ("a", "analizado", 7) in bd.estados and "Kabuki" not in analizados   # mismo sitio: sin pagar
    assert analizados == ["Casa Pepe"]                                         # Fantasma no se encontró
    assert fichas == [("Casa Pepe", (40.42, -3.70)), ("Fantasma", (40.42, -3.70))]   # buscados por coordenadas
    assert ("c", "error", None) in bd.estados
    nuevo = bd.catalogo["casa pepe @b"]                                        # mismo nombre, otra ciudad
    assert ("b", "analizado", nuevo["id"]) in bd.estados and bd.catalogo["casa pepe"] is otro
    assert not [e for e in bd.estados if e[0] == "d"]                          # sigue pendiente


def test_fila_desde_ficha_usa_la_categoria_de_overture_si_google_no_la_da():
    fila = ps.fila_desde_ficha(lugar("a", "Kabuki"), [{"Rating Google": 4.4, "Nº reseñas Google": 120,
                                                        "Ficha cocina": "", "Ficha precio": "30-40 €"}])
    assert fila == {"Nombre": "Kabuki", "Puntuación": 4.4, "Nº Reseñas": 120, "Rango de precios": "30-40 €",
                    "Tipo de cocina": "Japonesa", "Estado": "", "Imagen URL": ""}


def test_un_fallo_al_analizar_no_deja_lugares_en_procesando(monkeypatch, fichas):
    def falla(filas, resenas=None):
        raise RuntimeError("Jev caído")
    monkeypatch.setattr(ps, "analizar_nuevos", falla)
    bd = BDFalsa()
    ps.procesar_lugares(bd, [lugar("a", "Nuevo")])
    assert bd.estados[-1] == ("a", "error", None)


def test_un_sitio_cerrado_se_oculta_sin_pasar_por_jev(analizados, fichas):
    bd = BDFalsa()
    ps.procesar_lugares(bd, [lugar("x", "Cerrado Ya")])
    assert analizados == [] and bd.estados[-1] == ("x", "cerrado", None)
