"""Comprobador de sitios cerrados (obtener_datos/verificar_lugares.py), sin navegador ni base de datos reales."""

import asyncio
import sys
from pathlib import Path

import pytest

pytest.importorskip("playwright")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "obtener_datos"))
import verificar_lugares as vl  # noqa: E402


@pytest.mark.parametrize("nuestro, de_google, mismo", [
    ("Margarito Bar", "Margarito Bar", True),
    ("Cecibakery Madrid", "Ceci Bakery", True),           # mismo nombre con otros espacios
    ("Asia Restaurante", "Asia Restaurante Majadahonda", True),
    ("Zaga", "Reformas Zaga S L", False),                 # solo lo contiene: es otro sitio
    ("El Cocedero", "El Cocedero de La Trucha", True),    # la mitad del nombre: se da por el mismo
    ("Bar", "Bar Manolo", False),                         # menos de la mitad: no
    ("Casa Pepe", "", False),
])
def test_mismo_sitio(nuestro, de_google, mismo):
    assert vl.mismo_sitio(nuestro, de_google) is mismo


def test_veredicto():
    lugar = {"nombre": "Margarito Bar"}
    assert vl.veredicto(lugar, {"nombre_google": "Margarito Bar", "estado": "Cerrado permanentemente"}) == "cerrado"
    assert vl.veredicto(lugar, {"nombre_google": "Margarito Bar", "estado": "Cerrado temporalmente"}) == "abierto"
    assert vl.veredicto(lugar, {"nombre_google": "Otro Bar", "estado": "Cerrado permanentemente"}) == "no_coincide"
    assert vl.veredicto(lugar, None) == "no_coincide"


class BDFalsa:
    def __init__(self, lugares):
        self.pendientes, self.marcados = list(lugares), []

    def lugares_a_verificar(self, limite):
        lote, self.pendientes = self.pendientes[:limite], self.pendientes[limite:]
        return lote

    def marcar_verificado(self, lugar_id, cerrado=False):
        self.marcados.append((lugar_id, cerrado))


def test_verificar_marca_todos_y_oculta_solo_los_cerrados(monkeypatch):
    class Navegador:
        async def new_page(self, **k):
            return object()

        async def close(self):
            pass

    class Playwright:
        class chromium:
            @staticmethod
            async def launch(**k):
                return Navegador()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    fichas = {"a": {"nombre_google": "Bar A", "estado": "Cerrado permanentemente"},
              "b": {"nombre_google": "Bar B", "estado": ""}}

    async def leer(page, lugar):
        if lugar["id"] == "c":
            raise TimeoutError("Google no ha cargado")
        return fichas[lugar["id"]]

    import playwright.async_api
    monkeypatch.setattr(playwright.async_api, "async_playwright", lambda: Playwright())
    monkeypatch.setattr(vl, "leer_ficha", leer)
    bd = BDFalsa([{"id": i, "nombre": f"Bar {i.upper()}"} for i in "abc"])

    cuenta = asyncio.run(vl.verificar(bd, minutos=1, pestanas=2))

    assert sorted(bd.marcados) == [("a", True), ("b", False), ("c", False)]   # el que falla, apuntado igual
    assert cuenta == {"cerrado": 1, "abierto": 1, "no_coincide": 1}
