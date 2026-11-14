"""
Fotos extra de cada restaurante analizado (supabase/015_fotos_extra.sql): la principal a 800 px + 3 de «Comida y
bebida» + 1 de «Ambiente» de su galería de Google Maps, subidas a R2 como restaurantes/<id>/1.jpg ... 5.jpg.

Necesita la sesión de Google (sin ella, Google enseña una sola foto), así que va dentro del Chrome del procesador:
- mientras se analiza un lote, en una pestaña más, a la vez que las reseñas (`mientras`);
- cuando el procesador no tiene nada que analizar (descanso, tope de Jev, nada pedido), en tandas propias (`tanda`).
Los restaurantes recién analizados entran solos en la cola (fotos_en vacío).
"""

import asyncio
import random
import re
import time

import requests

import extraer_html
import extraer_resenas
from conexion_supabase import datos
from verificar_lugares import reducir_foto

LADO = 800                 # px: ~80 KB por foto; 5 por restaurante caben de sobra en los 10 GB gratis de R2
POR_TANDA = 20             # restaurantes por tanda cuando el procesador está libre
PESTANAS_TANDA = 2
DESCANSO_MIN = 4           # entre tandas propias (el análisis ya tiene sus descansos)
ESPERA_S = (3, 8)          # entre uno y otro, para no parecer un robot ante Google
MAX_VACIOS_SEGUIDOS = 8    # sin ninguna foto tantas veces seguidas: ¿se ha perdido la sesión? -> se deja para luego


def url_grande(url, lado=LADO):
    """La URL de Google pidiendo la foto a `lado` px (sin recortar)."""
    return re.sub(r"=[swh]\d+[^/]*$", "", url) + f"=w{lado}-h{lado}-k-no"


def descargar(url):
    try:
        r = requests.get(url_grande(url), timeout=20)
        r.raise_for_status()
    except requests.RequestException:
        return None
    return reducir_foto(r.content, LADO)


def subir(bd, restaurante_id, urls):
    """Descarga y sube las fotos (en orden, sin huecos). Devuelve los archivos subidos."""
    archivos = []
    for url in urls:
        contenido = descargar(url) if url else None
        if contenido:
            archivo = f"restaurantes/{restaurante_id}/{len(archivos) + 1}.jpg"
            bd.subir_foto(archivo, contenido)
            archivos.append(archivo)
    return archivos


class Galeria:
    def __init__(self, bd):
        self.bd = bd
        self.saltados = set()   # sin ninguna foto en esta ejecución: se reintentan al reiniciar el procesador
        self.vacios_seguidos = 0
        self.hechos = 0
        self.descanso_hasta = 0.0

    def siguientes(self, n):
        filas = self.bd.restaurantes_sin_fotos(n + len(self.saltados))
        return [f for f in filas if f["id"] not in self.saltados][:n]

    async def uno(self, page, r):
        cerca = (r["lat"], r["lon"]) if r.get("lat") is not None and r.get("lon") is not None else None
        if not await extraer_resenas.buscar_restaurante(page, r["nombre"], cerca):
            self.bd.guardar_fotos(r["id"], [])   # no está en Google Maps: no se vuelve a buscar
            return
        await extraer_resenas.abrir_ficha_desde_resultados(page, r["nombre"])
        g = await extraer_resenas.obtener_fotos_galeria(page)
        urls = [g["principal"]] + g["comida"] + g["ambiente"]
        if not g["comida"] and not g["ambiente"]:   # sin galería: puede ser un fallo pasajero o la sesión
            self.saltados.add(r["id"])
            self.vacios_seguidos += 1
            return
        archivos = await asyncio.to_thread(subir, self.bd, r["id"], urls)   # sin bloquear las pestañas de reseñas
        self.bd.guardar_fotos(r["id"], archivos)
        self.vacios_seguidos, self.hechos = 0, self.hechos + 1

    async def trabajar(self, page, cola, parar=None):
        """Va sacando de `cola` hasta vaciarla o hasta que `parar` (asyncio.Event) se active. Nunca lanza: un fallo
        aquí no puede tirar el análisis que va a la vez."""
        while cola and not (parar and parar.is_set()) and self.vacios_seguidos < MAX_VACIOS_SEGUIDOS:
            r = cola.pop(0)
            try:
                await self.uno(page, r)
            except Exception as e:   # noqa: BLE001
                self.saltados.add(r["id"])
                print(f"  Fotos: error con {r['nombre']}: {str(e)[:120]}")
            await asyncio.sleep(random.uniform(*ESPERA_S))

    async def mientras(self, page, parar):
        """En una pestaña más del Chrome del análisis, hasta que el análisis acabe (`parar`)."""
        try:
            cola = await asyncio.to_thread(self.siguientes, POR_TANDA)
        except datos.ErrorSupabase:
            return
        antes = self.hechos
        await self.trabajar(page, cola, parar)
        if self.hechos > antes:
            print(f"  Fotos: {self.hechos - antes} restaurantes con fotos nuevas (a la vez que el análisis).")

    def tanda(self):
        """Con el procesador libre: abre Chrome y saca las fotos de POR_TANDA restaurantes. Devuelve si hizo algo."""
        if self.vacios_seguidos >= MAX_VACIOS_SEGUIDOS or time.monotonic() < self.descanso_hasta:
            return False
        cola = self.siguientes(POR_TANDA)
        if not cola:
            return False
        antes = self.hechos
        asyncio.run(self._tanda(cola))
        self.descanso_hasta = time.monotonic() + DESCANSO_MIN * 60
        print(f"Fotos: {self.hechos - antes} de {len(cola)} restaurantes con fotos nuevas.")
        if self.vacios_seguidos >= MAX_VACIOS_SEGUIDOS:
            print(f"Fotos: PARADO tras {MAX_VACIOS_SEGUIDOS} restaurantes seguidos sin galería (¿se ha perdido la "
                  "sesión de Google?). Se reintenta al reiniciar el procesador.")
        return True

    async def _tanda(self, cola):
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            contexto = await extraer_html._abrir_chrome_con_sesion(p)
            primera = contexto.pages[0] if contexto.pages else await contexto.new_page()
            paginas = [primera] + [await contexto.new_page() for _ in range(PESTANAS_TANDA - 1)]
            await asyncio.gather(*(self.trabajar(pagina, cola) for pagina in paginas))
            await contexto.close()
