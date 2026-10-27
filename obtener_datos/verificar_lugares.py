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

PESTANAS = 3       # sitios a la vez
POR_LOTE = 60      # sitios que se piden a la base de datos de una vez
PARECIDO = 0.75    # de los nombres (0-1) para dar por hecho que Google ha encontrado el mismo sitio
LADO_FOTO = 240    # px: la foto de la ficha rápida, pequeña (~10 KB) para que quepan todas en el almacenamiento


def mismo_sitio(nombre, nombre_google):
    """¿El sitio que ha abierto Google es el nuestro? Mismo nombre salvo detalles ("Cecibakery Madrid" /
    "Ceci Bakery"), pero no uno que solo lo contiene ("Zaga" / "Reformas Zaga S L")."""
    a, b = datos.texto_busqueda(nombre), datos.texto_busqueda(nombre_google)
    if not a or not b:
        return False
    corto, largo = sorted((a.replace(" ", ""), b.replace(" ", "")), key=len)
    if corto in largo and len(corto) >= len(largo) / 2:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= PARECIDO


def veredicto(lugar, leido):
    """'cerrado', 'abierto' o 'no_coincide' (Google ha abierto otro sitio, o ninguno: no se toca)."""
    if not leido or not mismo_sitio(lugar["nombre"], leido["nombre_google"]):
        return "no_coincide"
    return "cerrado" if "permanentemente" in (leido["estado"] or "").lower() else "abierto"


async def leer_ficha(page, lugar):
    await extraer_resenas.buscar_restaurante(page, lugar["nombre"], (lugar["lat"], lugar["lon"]))
    await extraer_resenas.abrir_ficha_desde_resultados(page, lugar["nombre"])
    ficha = await extraer_resenas.obtener_datos_ficha(page)
    extra = await extraer_resenas.obtener_datos_extra(page)
    return {"nombre_google": ficha["nombre_google"], "estado": extra["estado"], "nota": ficha["rating_google"],
            "cocina": extra["cocina"], "foto": extra["foto"]}


def foto_pequena(url):
    """La foto de Google en JPEG de LADO_FOTO px como mucho (bytes), o None si no se puede."""
    from PIL import Image
    try:
        r = requests.get(re.sub(r"=w\d+-h\d+[^/]*$", "=w400-h400-k-no", url), timeout=15)
        r.raise_for_status()
        imagen = Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception:
        return None
    imagen.thumbnail((LADO_FOTO, LADO_FOTO))
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
