"""
Procesa las listas que los usuarios piden desde la app ("Mi lista" en modo multiusuario).

Para cada lista: la descarga de Google Maps (con TU sesión de Google, que es la que enseña los
precios), reutiliza los restaurantes que ya están en el catálogo compartido (solo refresca nota,
precio, cocina y si está cerrado: no se vuelven a analizar ni cuestan nada) y analiza los nuevos
con los scripts de siempre: foto (extraer_html.py), reseñas (extraer_resenas.py) y clasificación
con Jev (clasificar_restaurantes_jev.py). Al final guarda la lista del usuario en Supabase.

USO (desde la raíz del proyecto):
    python obtener_datos/procesar_solicitudes.py           # las listas pendientes
    python obtener_datos/procesar_solicitudes.py --todas   # vuelve a procesar todas (para refrescarlas)

REQUISITOS:
    - Credenciales de Supabase (ver conexion_supabase.py).
    - Sesión de Google guardada: la primera vez se abre Chrome para que inicies sesión.
    - TYPESAFE_API_KEY (solo si hay restaurantes nuevos que clasificar).
    - Chrome visible: no lo cierres mientras trabaja.
"""

import argparse
import asyncio
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from bs4 import BeautifulSoup

import extraer_html
import extraer_resenas
from conexion_supabase import cliente, datos

# Datos que enseña la propia lista y pueden cambiar con el tiempo: se refrescan en los
# restaurantes que ya están en el catálogo, sin volver a analizarlos.
CAMPOS_DE_LA_LISTA = ("Puntuación", "Nº Reseñas", "Rango de precios", "Tipo de cocina", "Imagen URL")


class ErrorLista(Exception):
    """Fallo de una lista concreta: se marca con error y se sigue con las demás."""


def descargar_filas(enlace):
    html = asyncio.run(extraer_html._descargar_html_lista(enlace))
    return extraer_html.extraer_restaurantes(BeautifulSoup(html, "lxml"))


def datos_actualizados(existente, fila_lista):
    nuevos = dict(existente.get("datos") or {})
    for campo in CAMPOS_DE_LA_LISTA:
        if fila_lista.get(campo) not in ("", None):
            nuevos[campo] = datos.valor_para_json(fila_lista[campo])
    nuevos["Estado"] = fila_lista.get("Estado") or ""   # si ya no sale "Cerrado...", es que ha reabierto
    return nuevos


PESTANAS = 3   # restaurantes a la vez al sacar reseñas (--pestanas); si Google pone pegas, bajar a 1
MAPS = "https://www.google.com/maps?hl=es"


async def _resenas_de(nombres, pestanas=None):
    """Reseñas (hasta 30) de cada restaurante, con TU sesión de Google (sin sesión, Google Maps
    solo enseña ~5 por sitio) y en varias pestañas a la vez. Devuelve las filas en el orden de
    `nombres`, igual que si se hicieran de uno en uno."""
    from playwright.async_api import async_playwright
    pendientes = list(enumerate(nombres, start=1))
    por_indice = {}
    async with async_playwright() as p:
        contexto = await extraer_html._abrir_chrome_con_sesion(p)
        primera = contexto.pages[0] if contexto.pages else await contexto.new_page()
        await primera.goto(MAPS, wait_until="load")
        await extraer_html._asegurar_sesion(primera, MAPS)
        paginas = [primera] + [await contexto.new_page() for _ in range(max(1, pestanas or PESTANAS) - 1)]

        async def trabajador(page):
            while pendientes:   # cada pestaña coge el siguiente restaurante libre
                i, nombre = pendientes.pop(0)
                por_indice[i] = await extraer_resenas.procesar_restaurante(page, nombre, i, len(nombres))

        await asyncio.gather(*(trabajador(pagina) for pagina in paginas))
        await contexto.close()
    return [fila for i in sorted(por_indice) for fila in por_indice[i]]


def analizar_nuevos(filas):
    """Restaurantes que no están en el catálogo -> filas del catálogo, con el proceso de siempre
    (foto, reseñas y Jev) sobre excels temporales: no se toca excels/."""
    if not os.environ.get("TYPESAFE_API_KEY"):
        raise ErrorLista("falta la variable de entorno TYPESAFE_API_KEY para clasificar los restaurantes nuevos")
    import clasificar_restaurantes_jev as clasif

    import time
    t0 = time.time()
    extraer_html.descargar_imagenes(filas)   # rellena "Imagen archivo" y deja cada foto en imagenes/
    t_fotos = time.time()
    resenas = asyncio.run(_resenas_de([f["Nombre"] for f in filas]))
    t_resenas = time.time()
    print(f"  Tiempos: fotos {t_fotos - t0:.0f} s | reseñas {t_resenas - t_fotos:.0f} s "
          f"({(t_resenas - t_fotos) / max(1, len(filas)):.0f} s por restaurante, {PESTANAS} pestañas)")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        extraer_html.guardar_excel(filas, tmp / "v1.xlsx")
        pd.DataFrame(resenas).to_excel(tmp / "v2.xlsx", index=False)
        clasif.RESTAURANTES_XLSX, clasif.RESENAS_XLSX, clasif.SALIDA_XLSX = tmp / "v1.xlsx", tmp / "v2.xlsx", tmp / "salida.xlsx"
        try:
            rest, preparadas = clasif.cargar_y_preparar(None)
        except SystemExit:   # ninguna reseña útil (p. ej. solo direcciones sueltas): sin clasificación
            return datos.filas_catalogo_desde_excel(clasif.cargar_restaurantes_base(),
                                                     pd.DataFrame(columns=datos.COLUMNAS_PLATOS))
        clasif._comprobar_conexion()
        clasif.ejecutar(SimpleNamespace(reiniciar=False, hilos=clasif.HILOS_DEFECTO, verbose=False), rest, preparadas)
        clasif._cerrar_clientes()
        df_rest = pd.read_excel(tmp / "salida.xlsx", sheet_name="Restaurantes")
        df_platos = pd.read_excel(tmp / "salida.xlsx", sheet_name="Platos mencionados")
    return datos.filas_catalogo_desde_excel(df_rest, df_platos)


def subir_fotos(bd, filas_catalogo):
    for fila in filas_catalogo:
        ruta = extraer_html.IMAGENES_DIR / (fila["imagen"] or "")
        if fila["imagen"] and ruta.is_file():
            bd.subir_foto(fila["imagen"], ruta.read_bytes())
        else:
            fila["imagen"] = None


def procesar_lista(bd, lista):
    """Descarga y guarda la lista de un usuario. Devuelve un resumen; lanza ErrorLista si falla."""
    enlace = (lista.get("enlace") or "").strip()
    if not datos.enlace_lista_valido(enlace):   # se abre con TU sesión de Google: solo Google Maps
        raise ErrorLista("el enlace no es de una lista de Google Maps")
    bd.marcar(lista["id"], "procesando")

    filas = descargar_filas(enlace)
    if not filas:
        raise ErrorLista("la lista no tiene ningún restaurante (¿es una lista compartida de Google Maps?)")
    claves = [datos.clave_restaurante(f["Nombre"]) for f in filas]
    existentes = bd.restaurantes_por_clave(claves)

    actualizados, nuevos, vistas = [], [], set()
    for clave, fila in zip(claves, filas):
        if not clave or clave in vistas:
            continue
        vistas.add(clave)
        if clave in existentes:
            e = existentes[clave]
            actualizados.append({"clave": clave, "datos": datos_actualizados(e, fila),
                                 "platos": e.get("platos") or [], "imagen": e.get("imagen")})
        else:
            nuevos.append(fila)

    print(f"  {len(vistas)} restaurantes: {len(actualizados)} ya en el catálogo, {len(nuevos)} nuevos.")
    catalogo_nuevo = analizar_nuevos(nuevos) if nuevos else []
    subir_fotos(bd, catalogo_nuevo)
    ids = bd.guardar_restaurantes(actualizados + catalogo_nuevo)
    bd.reemplazar_lista(lista["id"], list(dict.fromkeys(ids[c] for c in claves if c in ids)))   # orden de Google, sin repetidos
    resumen = f"{len(vistas)} restaurantes ({len(catalogo_nuevo)} nuevos)"
    bd.marcar(lista["id"], "lista", resumen)
    return resumen


def main(argv=None):
    global PESTANAS
    parser = argparse.ArgumentParser(description="Procesa las listas pedidas desde la app.")
    parser.add_argument("--todas", action="store_true", help="vuelve a procesar todas las listas, no solo las pendientes")
    parser.add_argument("--vigilar", type=int, metavar="MINUTOS", nargs="?", const=10,
                        help="no termina: cada MINUTOS (10 por defecto) procesa las listas pendientes que haya")
    parser.add_argument("--pestanas", type=int, default=PESTANAS,
                        help=f"restaurantes a la vez al sacar reseñas (por defecto {PESTANAS}; 1 si Google pone pegas)")
    args = parser.parse_args(argv)
    PESTANAS = max(1, args.pestanas)

    bd = cliente()
    if args.vigilar:
        import time
        print(f"Vigilando listas pendientes cada {args.vigilar} min (Ctrl+C para parar)...")
        while True:
            pendientes = bd.listas_pendientes()
            if pendientes:
                procesar_varias(bd, pendientes)
            time.sleep(args.vigilar * 60)
    listas = bd.listas_con_enlace() if args.todas else bd.listas_pendientes()
    if not listas:
        print("No hay listas pendientes.")
        return
    procesar_varias(bd, listas)


def procesar_varias(bd, listas):
    for lista in listas:
        print(f"\n=== {lista['usuario']} ===")
        try:
            print(f"  OK: {procesar_lista(bd, lista)}")
        except KeyboardInterrupt:
            bd.marcar(lista["id"], "pendiente", "interrumpido; se volverá a intentar")
            raise
        except (Exception, SystemExit) as e:   # SystemExit: p. ej. no se inició sesión en Google a tiempo
            print(f"  ERROR: {e}")
            try:
                bd.marcar(lista["id"], "error", str(e)[:300])
            except datos.ErrorSupabase:
                pass


if __name__ == "__main__":
    main()
