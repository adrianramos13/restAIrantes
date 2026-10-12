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

    def analizar(filas):
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

    async def procesar(page, nombre, i, total):
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
