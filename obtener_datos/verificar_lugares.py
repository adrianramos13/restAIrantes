"""
Comprueba en Google Maps si los sitios de Explorar (tabla lugares) siguen abiertos y oculta los que han cerrado
para siempre. Los datos de Overture tardan en enterarse de los cierres; la ficha de Google Maps no.

No necesita sesión de Google (sin ella la ficha también dice "Cerrado permanentemente") ni gasta Jev. Va por los
nunca comprobados y luego por los comprobados hace más de datos.DIAS_ENTRE_VERIFICACIONES días. Solo se oculta
un sitio si Google ha encontrado el mismo (nombre parecido): "Zaga" no es "Reformas Zaga S L".

De cada sitio que es el mismo y sigue abierto guarda además su "ficha rápida" (supabase/012_ficha_rapida.sql):
nota de Google, tipo de cocina y una foto pequeña, que Descubrir enseña al momento sin necesidad de analizarlo.

Lo ejecuta solo GitHub Actions (.github/workflows/procesador.yml): los lunes, y seguido (una ejecución tras otra)
mientras queden sitios sin ficha rápida.

USO (desde la raíz del proyecto):
    python obtener_datos/verificar_lugares.py --minutos 30
"""

import argparse
import asyncio
import difflib
import io
import os
import re
import time
from collections import Counter

import requests

import extraer_resenas
from conexion_supabase import cliente, datos
from servicios import haversine_km

PESTANAS = 3       # sitios a la vez
POR_LOTE = 60      # sitios que se piden a la base de datos de una vez
PARECIDO = 0.75    # de los nombres (0-1) para dar por hecho que Google ha encontrado el mismo sitio
CERCA_M = 250      # m: a esta distancia basta con compartir una palabra distintiva ("Arequepay" / "Restaurante Arequepay")
LEJOS_M = 1000     # m: más lejos nunca es el mismo sitio, aunque se llame igual (otro local u otra ciudad)
# Palabras que no distinguen un sitio de otro (en minúsculas y sin tildes, como datos.texto_busqueda)
GENERICAS = set("""restaurante restaurant bar bares cafeteria cafe coffee taberna meson cerveceria tapas madrid
    pizzeria bistro cocina casa grill kebab lounge cocktail cocteleria express food comida comidas asador sushi
    burger hamburgueseria brasa pollos bocateria churreria panaderia pasteleria heladeria vinoteca tasca house
    club gastrobar gastro plaza calle centro mercado local tienda shop store espana spain the and""".split())
LADO_FOTO = 240    # px: la foto de la ficha rápida, pequeña (~10 KB) para que quepan todas en el almacenamiento
LADO_FOTO_RESTAURANTE = 320   # px: la de un restaurante analizado, algo mayor porque la ficha la enseña grande


def mismo_sitio(nombre, nombre_google, metros=None):
    """¿El sitio que ha abierto Google es el nuestro? Mismo nombre salvo detalles ("Cecibakery Madrid" /
    "Ceci Bakery"), pero no uno que solo lo contiene ("Zaga" / "Reformas Zaga S L"). Con `metros` (distancia
    entre los dos): a <= CERCA_M basta una palabra distintiva en común ("El CEPO" / "Bar El Cepo - Casa de
    comidas"); a > LEJOS_M, nunca."""
    a, b = datos.texto_busqueda(nombre), datos.texto_busqueda(nombre_google)
    if not a or not b or (metros is not None and metros > LEJOS_M):
        return False
    juntos_a, juntos_b = a.replace(" ", ""), b.replace(" ", "")
    corto, largo = sorted((juntos_a, juntos_b), key=len)
    if corto in largo and len(corto) >= len(largo) / 2:
        return True
    if metros is not None and metros <= CERCA_M and (
            any(p in juntos_b for p in _distintivas(a)) or any(p in juntos_a for p in _distintivas(b))):
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= PARECIDO


def _distintivas(texto):
    return {p for p in texto.split() if len(p) >= 4 and p not in GENERICAS}


def metros_entre(lugar, leido):
    """Distancia entre nuestro sitio y el que ha abierto Google (None si falta alguna coordenada)."""
    if None in (lugar.get("lat"), lugar.get("lon"), leido.get("lat"), leido.get("lon")):
        return None
    return haversine_km(lugar["lat"], lugar["lon"], leido["lat"], leido["lon"]) * 1000


def coordenadas_ficha(url):
    """(lat, lon) del sitio de la URL de su ficha: el !3d…!4d… es el sitio exacto; el @… es el centro del mapa."""
    m = re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", url or "")
    return (float(m.group(1)), float(m.group(2))) if m else extraer_resenas.extraer_lat_lon(url)


def veredicto(lugar, leido):
    """'cerrado', 'abierto' o 'no_coincide' (Google ha abierto otro sitio, o ninguno: no se toca)."""
    if not leido or not mismo_sitio(lugar["nombre"], leido["nombre_google"], metros_entre(lugar, leido)):
        return "no_coincide"
    return "cerrado" if "permanentemente" in (leido["estado"] or "").lower() else "abierto"


async def leer_ficha(page, lugar):
    await extraer_resenas.buscar_restaurante(page, lugar["nombre"], (lugar["lat"], lugar["lon"]))
    await extraer_resenas.abrir_ficha_desde_resultados(page, lugar["nombre"])
    ficha = await extraer_resenas.obtener_datos_ficha(page)
    extra = await extraer_resenas.obtener_datos_extra(page)
    lat, lon = coordenadas_ficha(ficha.get("url_google"))
    return {"nombre_google": ficha["nombre_google"], "estado": extra["estado"], "nota": ficha["rating_google"],
            "cocina": extra["cocina"], "foto": extra["foto"], "lat": lat, "lon": lon}


def foto_pequena(url):
    """La foto de Google en JPEG de LADO_FOTO px como mucho (bytes), o None si no se puede."""
    try:
        r = requests.get(re.sub(r"=w\d+-h\d+[^/]*$", "=w400-h400-k-no", url), timeout=15)
        r.raise_for_status()
    except Exception:
        return None
    return reducir_foto(r.content)


def reducir_foto(contenido, lado=LADO_FOTO):
    """La imagen en JPEG de `lado` px como mucho (bytes), o None si no es una imagen."""
    from PIL import Image
    try:
        imagen = Image.open(io.BytesIO(contenido)).convert("RGB")
    except Exception:
        return None
    imagen.thumbnail((lado, lado))
    salida = io.BytesIO()
    imagen.save(salida, "JPEG", quality=72, optimize=True)
    return salida.getvalue()


def ficha_rapida(bd, lugar, leido):
    """{nota_google, cocina_google, foto} para guardar del sitio (la foto se sube al almacenamiento)."""
    ficha = {"nota_google": leido.get("nota"), "cocina_google": leido.get("cocina") or None, "foto": None}
    contenido = foto_pequena(leido["foto"]) if leido.get("foto") else None
    if contenido:
        archivo = f"lugares/{lugar['id']}.jpg"
        try:
            bd.subir_foto(archivo, contenido)
            ficha["foto"] = archivo
        except datos.ErrorSupabase:
            pass
    return ficha


async def verificar(bd, minutos, pestanas=PESTANAS):
    from playwright.async_api import async_playwright
    fin, cuenta = time.monotonic() + minutos * 60, Counter()
    async with async_playwright() as p:
        navegador = await p.chromium.launch(headless=True)
        paginas = [await navegador.new_page(locale="es-ES") for _ in range(pestanas)]
        while time.monotonic() < fin:
            cola = bd.lugares_a_verificar(POR_LOTE)
            if not cola:
                break

            async def trabajador(page):
                while cola and time.monotonic() < fin:
                    lugar = cola.pop(0)
                    try:
                        leido = await leer_ficha(page, lugar)
                    except Exception:   # se apunta igual como comprobado: si no, se atascaría siempre en el mismo
                        leido = None
                    v = veredicto(lugar, leido)
                    ficha = ficha_rapida(bd, lugar, leido) if v == "abierto" and bd.con_ficha_rapida() else None
                    bd.marcar_verificado(lugar["id"], cerrado=v == "cerrado", ficha=ficha)
                    cuenta[v] += 1
                    if v == "cerrado":
                        print(f"  Cerrado: {lugar['nombre']}")

            await asyncio.gather(*(trabajador(pagina) for pagina in paginas))
        await navegador.close()
    return cuenta


def main(argv=None):
    parser = argparse.ArgumentParser(description="Comprueba en Google Maps si los sitios de Explorar siguen abiertos.")
    parser.add_argument("--minutos", type=float, default=30, help="cuánto rato (por defecto 30)")
    parser.add_argument("--pestanas", type=int, default=PESTANAS)
    args = parser.parse_args(argv)
    try:
        cuenta = asyncio.run(verificar(cliente(), args.minutos, max(1, args.pestanas)))
    except datos.ErrorSupabase as e:   # p. ej. aún no se ha ejecutado supabase/010_lugares_al_dia.sql
        raise SystemExit(f"ERROR: {str(e)[:200]}")
    print(f"Comprobados {sum(cuenta.values())}: {cuenta['abierto']} abiertos, {cuenta['cerrado']} cerrados "
          f"(ocultados), {cuenta['no_coincide']} sin encontrar el mismo sitio en Google.")
    # En GitHub Actions: si aún quedan sitios sin ficha rápida, el flujo lanza otra ejecución (carga inicial)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as salida:
            salida.write(f"quedan={'si' if cliente().quedan_sin_ficha() else 'no'}\n")


if __name__ == "__main__":
    main()
