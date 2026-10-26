"""
Crea la sesión de Google para el procesador en la nube (GitHub Actions) y la guarda en origen/sesion_google.json:
sin sesión, Google Maps no enseña las reseñas. Ese archivo da acceso a la cuenta de Google: usa una cuenta SOLO
para esto (no la personal), no lo compartas y bórralo después de copiarlo al secreto GOOGLE_SESION de GitHub.

Se inicia sesión en el Chromium de Playwright (el mismo navegador que usa la nube), con un perfil propio
(origen/perfil_nube/), y NO en Chrome: Chrome ata la sesión de Google a su perfil y, sacada de ahí, Google la
rechaza (lo comprobamos: con las cookies del Chrome del procesador, Maps pedía "Iniciar sesión"). Antes de
guardarla se comprueba que funciona fuera de ese perfil, como en la nube.

USO (desde la raíz del proyecto):
    python obtener_datos/exportar_sesion_google.py
Se abre una ventana: inicia sesión con la cuenta para el procesador (solo la primera vez).
"""

import asyncio
import json
from pathlib import Path

import extraer_html

MAPS = "https://www.google.com/maps?hl=es"
ORIGEN = Path(__file__).resolve().parent.parent / "origen"
PERFIL = ORIGEN / "perfil_nube"            # en .gitignore
SALIDA = ORIGEN / "sesion_google.json"     # en .gitignore


async def exportar(p):
    contexto = await p.chromium.launch_persistent_context(
        str(PERFIL), headless=False, locale="es-ES", viewport={"width": 1280, "height": 860},
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation", "--no-sandbox"])   # si no, Google pone pegas al iniciar sesión
    pagina = contexto.pages[0] if contexto.pages else await contexto.new_page()
    await pagina.goto(MAPS, wait_until="load")
    await extraer_html._asegurar_sesion(pagina, MAPS)
    estado = await contexto.storage_state()
    await contexto.close()
    # Solo las cookies de Google: es lo que hace falta y cabe en un secreto de GitHub (máx. 48 KB).
    return {"cookies": [c for c in estado["cookies"] if "google" in c["domain"]], "origins": []}


async def funciona(p, sesion):
    """¿Vale la sesión en un navegador nuevo y sin ventana, como en GitHub Actions?"""
    navegador = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    pagina = await (await navegador.new_context(storage_state=sesion, locale="es-ES")).new_page()
    await pagina.goto(MAPS, wait_until="load")
    await pagina.wait_for_timeout(3000)
    vale = await extraer_html._con_sesion(pagina)
    await navegador.close()
    return vale


async def exportar_y_comprobar():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        sesion = await exportar(p)
        return sesion, await funciona(p, sesion)


def main():
    sesion, vale = asyncio.run(exportar_y_comprobar())
    if not vale:
        raise SystemExit("ERROR: Google no acepta esta sesión fuera de esta ventana, así que en la nube tampoco "
                         "valdría. No se ha guardado nada. Prueba a cerrar sesión en esa ventana y volver a entrar.")
    SALIDA.write_text(json.dumps(sesion), encoding="utf-8")
    print(f"Sesión comprobada (vale fuera de este ordenador) y guardada en {SALIDA}.")
    print("Ahora cópiala al secreto GOOGLE_SESION del repositorio en GitHub (Settings -> Secrets and variables ->")
    print("Actions -> GOOGLE_SESION -> Update) pegando el contenido del archivo, y después BORRA el archivo.")


if __name__ == "__main__":
    main()
