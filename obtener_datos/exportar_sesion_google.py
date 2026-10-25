"""
Guarda la sesión de Google del Chrome del procesador (origen/perfil_chrome/) en origen/sesion_google.json, para
que el procesador en la nube (GitHub Actions) pueda sacar las reseñas con ella: sin sesión, Google Maps no las
enseña. Ese archivo da acceso a la cuenta de Google: usa una cuenta SOLO para esto (no la personal), no lo
compartas y bórralo después de copiarlo al secreto GOOGLE_SESION de GitHub (ver el README).

USO (desde la raíz del proyecto):
    python obtener_datos/exportar_sesion_google.py
La primera vez se abre Chrome para que inicies sesión (con la cuenta para el procesador).
"""

import asyncio
import json
from pathlib import Path

import extraer_html

MAPS = "https://www.google.com/maps?hl=es"
SALIDA = Path(__file__).resolve().parent.parent / "origen" / "sesion_google.json"   # en .gitignore


async def exportar():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        contexto = await extraer_html._abrir_chrome_con_sesion(p)
        pagina = contexto.pages[0] if contexto.pages else await contexto.new_page()
        await pagina.goto(MAPS, wait_until="load")
        await extraer_html._asegurar_sesion(pagina, MAPS)
        estado = await contexto.storage_state()
        await contexto.close()
    # Solo las cookies de Google: es lo que hace falta y cabe en un secreto de GitHub (máx. 48 KB).
    return {"cookies": [c for c in estado["cookies"] if "google" in c["domain"]], "origins": []}


def main():
    sesion = asyncio.run(exportar())
    SALIDA.write_text(json.dumps(sesion), encoding="utf-8")
    print(f"Guardada en {SALIDA} ({len(sesion['cookies'])} cookies).")
    print("Ahora cópiala al secreto GOOGLE_SESION del repositorio en GitHub (Settings -> Secrets and variables ->")
    print("Actions -> New repository secret) pegando el contenido del archivo, o con:")
    print("    gh secret set GOOGLE_SESION < origen/sesion_google.json")
    print("y después BORRA el archivo.")


if __name__ == "__main__":
    main()
