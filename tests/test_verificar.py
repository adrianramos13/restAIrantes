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


@pytest.mark.parametrize("nuestro, de_google, metros, mismo", [
    ("La Piparra", "La Piparra CC Carrefour Alcobendas", 40, True),   # casos reales de Overture / Google
    ("Lionheart", "Lionheart Shisha Lounge & Cocktail Bar", 120, True),
    ("Arequepay", "Restaurante Arequepay", 7, True),
    ("El CEPO", "BAR EL CEPO - CASA DE COMIDAS RESTAURANTE", 3, True),
    ("Paddys Madrid", "Paddy's Bar Irlandés", 11, True),
    ("Tambayan Cafe Bar", "Bar Tambayan", 2, True),
    ("Restaurante The Captain", "Jewelry Bar Acorazada", 16, False),   # al lado, pero otro sitio
    ("El Meteorito", "BAR CAFETERÍA El FLAMENQUITO", 28, False),
    ("Bar", "Bar Manolo", 10, False),                                 # solo palabras genéricas
    ("La Piparra", "La Piparra CC Carrefour Alcobendas", 600, False),   # ni cerca ni nombre casi igual
    ("La Piparra", "La Piparra CC Carrefour Alcobendas", None, False),  # sin coordenadas: como antes
    ("Zaga", "Reformas Zaga S L", 600, False),
    ("Sanabria", "Sanabria", 323_646, False),                         # se llama igual, pero en otra ciudad
    ("Sanabria", "Sanabria", 300, True),
])
def test_mismo_sitio_cerca(nuestro, de_google, metros, mismo):
    assert vl.mismo_sitio(nuestro, de_google, metros) is mismo


def test_coordenadas_ficha():
    url = "https://www.google.com/maps/place/X/@40.40,-3.70,17z/data=!3m1!4b1!4m6!3m5!8m2!3d40.4312!4d-3.7012!16s"
    assert vl.coordenadas_ficha(url) == (40.4312, -3.7012)                    # el sitio, no el centro del mapa
    assert vl.coordenadas_ficha("https://www.google.com/maps/@40.5,-3.6,15z") == (40.5, -3.6)
    assert vl.coordenadas_ficha(None) == (None, None)


def test_veredicto_por_cercania():
    lugar = {"nombre": "La Piparra", "lat": 40.5, "lon": -3.6}
    leido = {"nombre_google": "La Piparra CC Carrefour", "estado": "", "lat": 40.5003, "lon": -3.6}   # ~33 m
    assert vl.veredicto(lugar, leido) == "abierto"
    assert vl.veredicto(lugar, {**leido, "lat": 40.51}) == "no_coincide"   # ~1,1 km


def test_veredicto():
    lugar = {"nombre": "Margarito Bar"}
    assert vl.veredicto(lugar, {"nombre_google": "Margarito Bar", "estado": "Cerrado permanentemente"}) == "cerrado"
    assert vl.veredicto(lugar, {"nombre_google": "Margarito Bar", "estado": "Cerrado temporalmente"}) == "abierto"
    assert vl.veredicto(lugar, {"nombre_google": "Otro Bar", "estado": "Cerrado permanentemente"}) == "no_coincide"
    assert vl.veredicto(lugar, None) == "no_coincide"


class BDFalsa:
    def __init__(self, lugares):
        self.pendientes, self.marcados, self.fichas, self.fotos = list(lugares), [], {}, {}

    def lugares_a_verificar(self, limite):
        lote, self.pendientes = self.pendientes[:limite], self.pendientes[limite:]
        return lote

    def marcar_verificado(self, lugar_id, cerrado=False, ficha=None):
        self.marcados.append((lugar_id, cerrado))
        self.fichas[lugar_id] = ficha

    def con_ficha_rapida(self):
        return True

    def subir_foto(self, archivo, contenido):
        self.fotos[archivo] = contenido


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
              "b": {"nombre_google": "Bar B", "estado": "", "nota": 4.3, "cocina": "Taberna", "foto": "https://x/f=w100-h100"}}

    async def leer(page, lugar):
        if lugar["id"] == "c":
            raise TimeoutError("Google no ha cargado")
        return fichas[lugar["id"]]

    import playwright.async_api
    monkeypatch.setattr(playwright.async_api, "async_playwright", lambda: Playwright())
    monkeypatch.setattr(vl, "leer_ficha", leer)
    monkeypatch.setattr(vl, "foto_pequena", lambda url: b"jpg")
    bd = BDFalsa([{"id": i, "nombre": f"Bar {i.upper()}"} for i in "abc"])

    cuenta = asyncio.run(vl.verificar(bd, minutos=1, pestanas=2))

    assert sorted(bd.marcados) == [("a", True), ("b", False), ("c", False)]   # el que falla, apuntado igual
    assert cuenta == {"cerrado": 1, "abierto": 1, "no_coincide": 1}
    assert bd.fichas["b"] == {"nota_google": 4.3, "cocina_google": "Taberna", "foto": "lugares/b.jpg"}   # ficha rápida
    assert bd.fotos == {"lugares/b.jpg": b"jpg"} and bd.fichas["a"] is None and bd.fichas["c"] is None


def test_reducir_foto():
    import io
    from PIL import Image
    grande = io.BytesIO()
    Image.new("RGB", (900, 600), "orange").save(grande, "JPEG")
    reducida = Image.open(io.BytesIO(vl.reducir_foto(grande.getvalue(), vl.LADO_FOTO_RESTAURANTE)))
    assert reducida.size == (320, 213) and vl.reducir_foto(b"no es una imagen") is None


def test_foto_pequena(monkeypatch):
    import io
    from PIL import Image
    grande = io.BytesIO()
    Image.new("RGB", (1200, 800), "orange").save(grande, "JPEG")

    class Respuesta:
        content = grande.getvalue()

        def raise_for_status(self):
            pass
    pedidas = []
    monkeypatch.setattr(vl.requests, "get", lambda url, timeout: pedidas.append(url) or Respuesta())
    pequena = Image.open(io.BytesIO(vl.foto_pequena("https://lh3.googleusercontent.com/x=w491-h240-k-no")))
    assert max(pequena.size) <= vl.LADO_FOTO and pedidas == ["https://lh3.googleusercontent.com/x=w400-h400-k-no"]
