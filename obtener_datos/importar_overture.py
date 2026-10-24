"""
Importa a Supabase (tabla lugares, supabase/009_lugares.sql) los restaurantes, bares y cafeterías de una
zona, desde los datos abiertos de Overture Maps: gratis y sin clave, DuckDB los lee directamente de su
almacenamiento público (solo baja lo de la zona pedida). Es lo que la app enseña en "Explorar".

Los que ya están en el catálogo (porque venían en la lista de alguien) se enlazan con él al importar:
mismo sitio (a menos de DISTANCIA_ENLACE_M) y nombre parecido. Así salen ya como "analizados".
Volver a importar una zona actualiza sus datos sin tocar lo que se ha pedido o analizado.

USO (desde la raíz del proyecto):
    python obtener_datos/importar_overture.py --zona madrid
    python obtener_datos/importar_overture.py --caja -3.80 40.35 -3.60 40.50   # oeste sur este norte
    python obtener_datos/importar_overture.py --zona madrid --sin-subir         # solo cuenta, no toca Supabase

REQUISITOS: pip install duckdb (ver requirements.txt) y las credenciales de Supabase (conexion_supabase.py).
"""

import argparse
import difflib
import math

import numpy as np
import pandas as pd
import requests

from conexion_supabase import cliente, datos

CATALOGO_OVERTURE = "https://stac.overturemaps.org/catalog.json"
RUTA_LUGARES = "s3://overturemaps-us-west-2/release/{version}/theme=places/type=place/*"
ZONAS = {   # oeste, sur, este, norte
    "madrid": (-4.58, 39.88, -3.05, 41.17),                 # Comunidad de Madrid (y un poco alrededor)
    "espana": (-9.40, 35.90, 4.40, 43.80),                  # península y Baleares
    "canarias": (-18.20, 27.60, -13.40, 29.50),
}
# Sitios para comer o tomar algo (basic_category de Overture). Fuera tiendas, bodegas, cerveceras...
CATEGORIAS_BASICAS = ("restaurant", "casual_eatery", "fast_food_restaurant", "bar", "cafe", "coffee_shop")
CONFIANZA_MINIMA = 0.5        # por debajo, Overture no está seguro de que el sitio exista
DISTANCIA_ENLACE_M = 150      # para enlazar con un restaurante del catálogo
PARECIDO_MINIMO = 0.7         # de los nombres (0-1), para enlazar: con 0,6 se cuelan vecinos ("Bar X" / "Bar Y")

ETIQUETAS = {   # categoría de Overture (taxonomy.primary) -> lo que se enseña en la app
    "spanish_restaurant": "Española", "tapas_bar": "Tapas", "italian_restaurant": "Italiana",
    "pizza_restaurant": "Pizzería", "chinese_restaurant": "China", "japanese_restaurant": "Japonesa",
    "sushi_restaurant": "Sushi", "mexican_restaurant": "Mexicana", "peruvian_restaurant": "Peruana",
    "argentine_restaurant": "Argentina", "indian_restaurant": "India", "thai_restaurant": "Tailandesa",
    "vietnamese_restaurant": "Vietnamita", "korean_restaurant": "Coreana", "asian_restaurant": "Asiática",
    "mediterranean_restaurant": "Mediterránea", "seafood_restaurant": "Marisquería", "steakhouse": "Asador",
    "barbecue_restaurant": "Brasa", "burger_restaurant": "Hamburguesas", "chicken_restaurant": "Pollos",
    "doner_kebab_restaurant": "Kebab", "turkish_restaurant": "Turca", "american_restaurant": "Americana",
    "french_restaurant": "Francesa", "greek_restaurant": "Griega", "lebanese_restaurant": "Libanesa",
    "venezuelan_restaurant": "Venezolana", "colombian_restaurant": "Colombiana", "vegan_restaurant": "Vegana",
    "vegetarian_restaurant": "Vegetariana", "breakfast_and_brunch_restaurant": "Desayunos y brunch",
    "bar_and_grill_restaurant": "Bar restaurante", "gastropub": "Gastrobar", "pub": "Pub",
    "cocktail_bar": "Coctelería", "wine_bar": "Vinoteca", "beer_bar": "Cervecería", "bakery": "Panadería",
    "sandwich_shop": "Bocadillos", "ice_cream_shop": "Heladería", "dessert_shop": "Postres",
}
POR_TIPO = {"restaurant": "Restaurante", "casual_eatery": "Comida informal", "fast_food_restaurant": "Comida rápida",
            "bar": "Bar", "cafe": "Cafetería", "coffee_shop": "Cafetería"}


def etiqueta_categoria(primaria, basica):
    """Categoría en español: la concreta si la conocemos; si no, la del tipo de sitio."""
    return ETIQUETAS.get(primaria) or POR_TIPO.get(basica) or "Restaurante"


def ultima_version():
    return requests.get(CATALOGO_OVERTURE, timeout=30).json()["latest"]


def leer_overture(caja, version):
    """DataFrame con los sitios de comer de la caja (oeste, sur, este, norte). Tarda ~1 min por zona grande."""
    import duckdb
    oeste, sur, este, norte = caja
    con = duckdb.connect()
    con.sql("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
    return con.execute(f"""
        SELECT id, names.primary AS nombre, taxonomy.primary AS primaria, basic_category AS basica,
               (bbox.ymin + bbox.ymax) / 2 AS lat, (bbox.xmin + bbox.xmax) / 2 AS lon,
               addresses[1].freeform AS direccion, addresses[1].locality AS ciudad, addresses[1].country AS pais,
               websites[1] AS web, phones[1] AS telefono, confidence AS confianza
        FROM read_parquet('{RUTA_LUGARES.format(version=version)}')
        WHERE bbox.xmin BETWEEN ? AND ? AND bbox.ymin BETWEEN ? AND ?
          AND basic_category IN {CATEGORIAS_BASICAS}
          AND coalesce(operating_status, 'open') <> 'permanently_closed'
          AND confidence >= ? AND names.primary IS NOT NULL
    """, [oeste, este, sur, norte, CONFIANZA_MINIMA]).df()


def _texto(valor):
    return None if valor is None or (isinstance(valor, float) and math.isnan(valor)) else str(valor)


def filas_lugares(df):
    """Filas para la tabla lugares (todas con las mismas columnas, como pide PostgREST en un upsert)."""
    return [{"id": f.id, "nombre": f.nombre, "nombre_busqueda": datos.texto_busqueda(f.nombre),
             "categoria": etiqueta_categoria(f.primaria, f.basica), "lat": float(f.lat), "lon": float(f.lon),
             "direccion": _texto(f.direccion), "ciudad": _texto(f.ciudad), "pais": _texto(f.pais),
             "web": _texto(f.web), "telefono": _texto(f.telefono),
             "confianza": None if pd.isna(f.confianza) else round(float(f.confianza), 3)}
            for f in df.itertuples()]


def _parecido(a, b):
    a, b = datos.texto_busqueda(a), datos.texto_busqueda(b)
    if not a or not b:
        return 0.0
    return 1.0 if a in b or b in a else difflib.SequenceMatcher(None, a, b).ratio()


def enlazar(lugares, catalogo):
    """{id del lugar: id del restaurante} para los restaurantes del catálogo que están en `lugares`: el lugar
    más parecido de nombre entre los que hay a menos de DISTANCIA_ENLACE_M."""
    if lugares.empty or catalogo.empty or "Latitud" not in catalogo:
        return {}
    lat, lon = lugares["lat"].to_numpy(), lugares["lon"].to_numpy()
    enlaces = {}
    for r in catalogo.dropna(subset=["Latitud", "Longitud"]).itertuples():
        # distancia aproximada (basta a esta escala): grados -> metros
        dy = (lat - r.Latitud) * 111_320
        dx = (lon - r.Longitud) * 111_320 * math.cos(math.radians(r.Latitud))
        cerca = np.flatnonzero(dx * dx + dy * dy <= DISTANCIA_ENLACE_M ** 2)
        if not len(cerca):
            continue
        parecidos = [_parecido(lugares["nombre"].iat[i], r.Nombre) for i in cerca]
        mejor = int(np.argmax(parecidos))
        if parecidos[mejor] >= PARECIDO_MINIMO:
            enlaces[lugares["id"].iat[cerca[mejor]]] = int(r.ID)
    return enlaces


def main(argv=None):
    parser = argparse.ArgumentParser(description="Importa sitios de comer de Overture Maps a Supabase (Explorar).")
    zona = parser.add_mutually_exclusive_group(required=True)
    zona.add_argument("--zona", choices=sorted(ZONAS))
    zona.add_argument("--caja", type=float, nargs=4, metavar=("OESTE", "SUR", "ESTE", "NORTE"))
    parser.add_argument("--version", help="versión de Overture (por defecto, la última)")
    parser.add_argument("--sin-subir", action="store_true", help="solo lee y cuenta; no toca Supabase")
    args = parser.parse_args(argv)

    version = args.version or ultima_version()
    caja = ZONAS[args.zona] if args.zona else tuple(args.caja)
    print(f"Leyendo Overture {version} en {caja}...")
    df = leer_overture(caja, version).drop_duplicates("id")
    print(f"  {len(df)} sitios. Por tipo: {df['basica'].value_counts().to_dict()}")
    if args.sin_subir:
        return

    bd = cliente()
    catalogo, _ = bd.todos_los_restaurantes()
    enlaces = enlazar(df, catalogo)
    filas = filas_lugares(df)
    sueltos = [f for f in filas if f["id"] not in enlaces]
    enlazados = [{**f, "restaurante_id": enlaces[f["id"]], "estado_analisis": "analizado"}
                 for f in filas if f["id"] in enlaces]
    bd.guardar_lugares(sueltos)      # sin estado: si ya estaban (pedidos, analizados), no se toca
    bd.guardar_lugares(enlazados)
    print(f"  Guardados {len(filas)} lugares; {len(enlazados)} enlazados con restaurantes del catálogo "
          f"(de {len(catalogo)}).")


if __name__ == "__main__":
    main()
