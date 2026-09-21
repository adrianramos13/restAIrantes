"""
V1 (simple): encuesta por terminal + algoritmo de puntuación que elige el
top 5 de restaurantes según tus preferencias, leyendo del excel maestro
unificado (restaurantes_maestro.xlsx, generado por unificar_excels.py).

CRITERIOS:
  - FILTRO DURO (descarta el restaurante si no se cumple):
      · tiempo máximo en coche desde tu ubicación (minutos)
  - PUNTUACIÓN (no descartan, suman puntos para el ranking):
      · encaje de presupuesto
      · coincidencia de tipo de cocina
      · si el plato que pides aparece bien valorado en las reseñas
      · calidad general (rating de Google + sentimiento de las reseñas
        analizadas) — así las mejores valoradas suben solas al top, sin
        tener que pedir un mínimo arbitrario.

USO:
    ESTRUCTURA DE CARPETAS ESPERADA (este archivo vive en algoritmo/):
        proyecto/
          excels/
            restaurantes_maestro.xlsx
          obtener_datos/
            unificar_excels.py
          algoritmo/
            encuesta.py     <- este archivo
            app.py

    1. Ejecuta primero (una sola vez): python obtener_datos/unificar_excels.py
    2. pip install -r requirements.txt
    3. python algoritmo/encuesta.py   (funciona igual desde cualquier
       carpeta: la ruta al excel se calcula a partir de dónde está este
       archivo, no de desde dónde se lanza el comando)

NOTA sobre tiempos en coche: se calculan con el servidor demo gratuito de
OSRM (router.project-osrm.org), sin necesidad de API key. Es un servicio
compartido pensado para uso razonable/no comercial (límite ~1 petición por
segundo), así que agrupamos todos los restaurantes en pocas peticiones en
vez de una por restaurante. Si el servicio no responde, el script usa una
estimación aproximada (distancia en línea recta / velocidad media urbana)
como respaldo.
"""

import re
import sys
import math
import time
from pathlib import Path

import pandas as pd
import requests


# ----------------------- CONFIGURACIÓN ----------------------- #

MAESTRO_XLSX = Path(__file__).resolve().parent.parent / "excels" / "restaurantes_maestro.xlsx"

# Pesos del algoritmo de puntuación (deben sumar 1.0 idealmente, pero no
# es obligatorio; son pesos relativos)
PESO_PRECIO = 0.20
PESO_COCINA = 0.20
PESO_PLATO = 0.30
PESO_CALIDAD = 0.25   # combina rating de Google + sentimiento de reseñas
PESO_NUM_RESENAS = 0.05

TOP_N = 5

OSRM_URL = "https://router.project-osrm.org/table/v1/driving/"
OSRM_BATCH_SIZE = 100   # restaurantes por petición, para no generar URLs enormes
VELOCIDAD_RESPALDO_KMH = 30   # si OSRM falla, estimamos minutos con esta velocidad media

# --------------------------------------------------------------- #


def cargar_datos():
    try:
        maestro = pd.read_excel(MAESTRO_XLSX, sheet_name="Restaurantes")
    except FileNotFoundError:
        sys.exit(
            f"ERROR: no encuentro '{MAESTRO_XLSX}'. Ejecuta primero 'python unificar_excels.py' "
            f"para generarlo a partir de tus excels."
        )

    try:
        df_platos = pd.read_excel(MAESTRO_XLSX, sheet_name="Platos mencionados")
    except Exception:
        print("[AVISO] No se pudo leer 'Platos mencionados' del maestro; no podré buscar por plato concreto.")
        df_platos = pd.DataFrame(columns=["ID_Restaurante", "Plato", "Sentimiento"])

    # --- Diagnóstico rápido (ya no debería haber sorpresas, al venir de un ID fijo) ---
    total = len(maestro)
    con_direccion = maestro["Dirección"].notna().sum()
    con_resumen = maestro["Reseñas buenas"].notna().sum() if "Reseñas buenas" in maestro.columns else 0
    print(f"[DIAGNÓSTICO] {con_direccion}/{total} restaurantes tienen dirección/ubicación.")
    print(f"[DIAGNÓSTICO] {con_resumen}/{total} restaurantes tienen resumen de reseñas analizadas.")

    return maestro, df_platos


def parsear_rango_precio(texto):
    """
    Convierte textos tipo 'De 20 a 30 €', '20-30 €', 'Más de 50 €' en
    (minimo, maximo). Si no se puede parsear, devuelve (None, None).
    """
    if not isinstance(texto, str) or not texto.strip():
        return None, None

    numeros = [int(n) for n in re.findall(r"\d+", texto)]
    if len(numeros) >= 2:
        return min(numeros), max(numeros)
    if len(numeros) == 1:
        if "más" in texto.lower() or "+" in texto:
            return numeros[0], None
        return None, numeros[0]
    return None, None


def solapamiento(min1, max1, min2, max2):
    """
    Puntuación 0-1 de cuánto se solapan dos rangos numéricos. Rangos con
    None en un extremo se tratan como abiertos (sin límite).
    Si algún rango es totalmente desconocido, devuelve un valor neutro.
    """
    if min1 is None and max1 is None:
        return 0.5
    if min2 is None and max2 is None:
        return 0.5

    lo1 = min1 if min1 is not None else 0
    hi1 = max1 if max1 is not None else float("inf")
    lo2 = min2 if min2 is not None else 0
    hi2 = max2 if max2 is not None else float("inf")

    inicio_solape = max(lo1, lo2)
    fin_solape = min(hi1, hi2)
    solape = max(0, fin_solape - inicio_solape)

    ancho_union = max(hi1, hi2) - min(lo1, lo2)
    if ancho_union in (0, float("inf")):
        # Rangos idénticos o con extremos abiertos por ambos lados
        return 1.0 if solape > 0 else 0.0

    return min(1.0, solape / ancho_union)


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def geocodificar_direccion(direccion):
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderServiceError, GeocoderTimedOut

    geolocalizador = Nominatim(user_agent="buscador_restaurantes_pareja")
    try:
        ubicacion = geolocalizador.geocode(direccion, timeout=10)
    except (GeocoderServiceError, GeocoderTimedOut) as e:
        print(f"[ERROR] No se pudo geocodificar la dirección: {e}")
        return None

    if ubicacion is None:
        return None
    return ubicacion.latitude, ubicacion.longitude


def obtener_minutos_coche(ubicacion_usuario, maestro):
    """
    Calcula el tiempo en coche (minutos) desde ubicacion_usuario hasta cada
    restaurante de `maestro`, usando el servicio "table" de OSRM (una sola
    petición calcula la matriz completa origen -> N destinos).

    Se agrupa en lotes de OSRM_BATCH_SIZE para no generar URLs demasiado
    largas y para no abusar del servidor demo gratuito. Si OSRM falla para
    algún lote, se usa una estimación de respaldo (línea recta / velocidad
    media) en vez de dejarlo todo sin dato.

    Devuelve una lista de minutos (o None) alineada por posición con las
    filas de `maestro` (por eso cargar_datos() resetea el índice).
    """
    lat_u, lon_u = ubicacion_usuario
    minutos = [None] * len(maestro)

    indices_validos = [
        i for i in range(len(maestro))
        if pd.notna(maestro.iloc[i]["Latitud"]) and pd.notna(maestro.iloc[i]["Longitud"])
    ]

    total_lotes = (len(indices_validos) + OSRM_BATCH_SIZE - 1) // OSRM_BATCH_SIZE
    print(f"\nCalculando tiempos en coche a {len(indices_validos)} restaurantes "
          f"(en {total_lotes} lote/s)...")

    for lote_num, start in enumerate(range(0, len(indices_validos), OSRM_BATCH_SIZE), start=1):
        lote_idx = indices_validos[start:start + OSRM_BATCH_SIZE]
        coords = [f"{lon_u},{lat_u}"] + [
            f"{maestro.iloc[i]['Longitud']},{maestro.iloc[i]['Latitud']}" for i in lote_idx
        ]
        url = OSRM_URL + ";".join(coords)

        try:
            resp = requests.get(url, params={"sources": "0", "annotations": "duration"}, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            duraciones = data["durations"][0]  # fila: origen -> cada destino (índice 0 es el propio origen)

            for j, idx in enumerate(lote_idx):
                dur_seg = duraciones[j + 1]
                if dur_seg is not None:
                    minutos[idx] = dur_seg / 60.0
        except Exception as e:
            print(f"  [AVISO] Fallo consultando OSRM en el lote {lote_num}/{total_lotes}: {e}")
            print(f"          Uso una estimación aproximada (línea recta / {VELOCIDAD_RESPALDO_KMH} km/h) para este lote.")
            for idx in lote_idx:
                fila = maestro.iloc[idx]
                dist_km = haversine_km(lat_u, lon_u, fila["Latitud"], fila["Longitud"])
                minutos[idx] = (dist_km / VELOCIDAD_RESPALDO_KMH) * 60

        if lote_num < total_lotes:
            time.sleep(1)  # respeta el límite de ~1 petición/segundo del servidor demo de OSRM

    return minutos


def pedir_numero(mensaje, opcional=False):
    while True:
        texto = input(mensaje).strip()
        if not texto and opcional:
            return None
        try:
            return float(texto.replace(",", "."))
        except ValueError:
            print("  Por favor, introduce un número válido.")


def hacer_encuesta(maestro):
    print("\n=== ENCUESTA: ¿qué restaurante buscáis hoy? ===\n")

    presupuesto_min = pedir_numero("Presupuesto mínimo por persona (€, deja en blanco si no importa): ", opcional=True)
    presupuesto_max = pedir_numero("Presupuesto máximo por persona (€): ")

    cocinas_disponibles = sorted(maestro["Tipo de cocina"].dropna().unique().tolist())
    print(f"\nTipos de cocina disponibles en tu lista (algunos ejemplos): "
          f"{', '.join(cocinas_disponibles[:15])}{'...' if len(cocinas_disponibles) > 15 else ''}")
    cocina = input("¿Qué tipo de cocina te apetece? (deja en blanco si no importa): ").strip()

    direccion = None
    ubicacion_usuario = None
    while ubicacion_usuario is None:
        direccion = input("\n¿Desde qué dirección/zona quieres medir el tiempo en coche? (ej. 'Sol, Madrid'): ").strip()
        ubicacion_usuario = geocodificar_direccion(direccion)
        if ubicacion_usuario is None:
            print("  No he podido localizar esa dirección, prueba a ser más específico (calle + ciudad).")

    print(f"  Ubicación detectada: {ubicacion_usuario[0]:.5f}, {ubicacion_usuario[1]:.5f}")
    tiempo_maximo_min = pedir_numero("¿Cuántos minutos en coche estás dispuesto/a a conducir como máximo?: ")

    plato_deseado = input("\n¿Te apetece algún plato concreto? (ej. 'sushi', deja en blanco si no importa): ").strip()

    return {
        "presupuesto_min": presupuesto_min,
        "presupuesto_max": presupuesto_max,
        "cocina": cocina,
        "ubicacion_usuario": ubicacion_usuario,
        "tiempo_maximo_min": tiempo_maximo_min,
        "plato_deseado": plato_deseado,
    }


def puntuacion_plato(id_restaurante, plato_deseado, df_platos):
    """
    Devuelve una puntuación 0-1 según cómo se valora el plato pedido en
    las reseñas de ese restaurante concreto (identificado por ID). 1.0 si
    se menciona bien, penaliza si solo aparece mal valorado, 0.0 si no se
    menciona (neutro real: no penalizamos por falta de datos).
    """
    if not plato_deseado:
        return 0.0  # el usuario no pidió nada concreto, no aplica

    if df_platos.empty or "ID_Restaurante" not in df_platos.columns:
        return 0.0

    menciones = df_platos[
        (df_platos["ID_Restaurante"] == id_restaurante) &
        (df_platos["Plato"].astype(str).str.contains(plato_deseado, case=False, na=False))
    ]
    if menciones.empty:
        return 0.0

    buenas = (menciones["Sentimiento"] == "Buena").sum()
    malas = (menciones["Sentimiento"] == "Mala").sum()
    total = len(menciones)

    # Proporción de menciones positivas, con un pequeño extra si hay varias
    ratio_positivo = buenas / total if total else 0
    bonus_volumen = min(0.2, 0.05 * total)  # más menciones = un poco más de confianza
    return min(1.0, ratio_positivo + bonus_volumen) if buenas >= malas else max(0.0, ratio_positivo - 0.2)


def calcular_score_calidad(fila):
    """
    Combina el rating de Google (60%) con la proporción de reseñas que
    nuestro propio análisis de sentimiento clasificó como "Buena" (40%),
    cuando ese dato está disponible. Así una nota alta pero con reseñas de
    texto mediocres (o viceversa) queda mejor reflejada que usando solo
    las estrellas.
    """
    score_estrellas = (fila["Puntuación"] or 0) / 5.0

    buenas = fila.get("Reseñas buenas", 0)
    malas = fila.get("Reseñas malas", 0)
    neutras = fila.get("Reseñas neutras", 0)
    buenas = 0 if pd.isna(buenas) else buenas
    malas = 0 if pd.isna(malas) else malas
    neutras = 0 if pd.isna(neutras) else neutras

    total_analizadas = buenas + malas + neutras
    if total_analizadas > 0:
        proporcion_buenas = buenas / total_analizadas
        return 0.6 * score_estrellas + 0.4 * proporcion_buenas
    return score_estrellas


def filtrar_y_puntuar(maestro, df_platos, r):
    df = maestro.copy()

    # --- Calcular tiempo en coche a cada restaurante ---
    df["Tiempo en coche (min)"] = obtener_minutos_coche(r["ubicacion_usuario"], df)

    # --- FILTRO DURO: tiempo máximo en coche ---
    antes = len(df)
    df = df[df["Tiempo en coche (min)"].notna() & (df["Tiempo en coche (min)"] <= r["tiempo_maximo_min"])]
    print(f"\nFiltro duro aplicado: {antes} -> {len(df)} restaurantes a "
          f"{r['tiempo_maximo_min']:.0f} min en coche o menos.")

    if df.empty:
        return df

    # --- PUNTUACIÓN ---
    max_resenas = maestro["Nº Reseñas"].max() or 1

    def puntuar_fila(fila):
        min_r, max_r = parsear_rango_precio(fila["Rango de precios"])
        score_precio = solapamiento(min_r, max_r, r["presupuesto_min"], r["presupuesto_max"])

        if r["cocina"]:
            cocina_rest = str(fila["Tipo de cocina"]).lower()
            score_cocina = 1.0 if r["cocina"].lower() in cocina_rest else 0.0
        else:
            score_cocina = 0.5  # neutro si no especifica

        score_plato = puntuacion_plato(fila["ID"], r["plato_deseado"], df_platos)

        score_calidad = calcular_score_calidad(fila)

        num_resenas = fila["Nº Reseñas"] if not pd.isna(fila["Nº Reseñas"]) else 0
        score_resenas = min(1.0, num_resenas / max_resenas)

        total = (
            PESO_PRECIO * score_precio +
            PESO_COCINA * score_cocina +
            PESO_PLATO * score_plato +
            PESO_CALIDAD * score_calidad +
            PESO_NUM_RESENAS * score_resenas
        )
        return total

    df["Score"] = df.apply(puntuar_fila, axis=1)
    df = df.sort_values("Score", ascending=False)
    return df


def formatear_platos(texto):
    """Quita los contadores '(n)' del texto de platos destacados, ej.
    'sushi (10), ramen (3)' -> 'sushi, ramen'."""
    if not isinstance(texto, str):
        return ""
    return re.sub(r"\s*\(\d+\)", "", texto).strip()


def resumen_mencion_plato(id_restaurante, plato_deseado, df_platos):
    """
    A diferencia de 'Platos mejor valorados' (que son los platos más
    destacados del restaurante EN GENERAL), esto busca específicamente
    qué dicen las reseñas analizadas sobre EL PLATO QUE PEDISTE en la
    encuesta, para ese restaurante. Es justo la misma información que usa
    'puntuacion_plato' para calcular el Score, así que lo que ves aquí es
    coherente con por qué ese restaurante ha subido (o no) en el ranking.
    """
    if df_platos.empty or "ID_Restaurante" not in df_platos.columns:
        return "(sin datos de reseñas analizadas)"

    menciones = df_platos[
        (df_platos["ID_Restaurante"] == id_restaurante) &
        (df_platos["Plato"].astype(str).str.contains(plato_deseado, case=False, na=False))
    ]
    if menciones.empty:
        return f"no se menciona explícitamente en las reseñas analizadas"

    buenas = (menciones["Sentimiento"] == "Buena").sum()
    malas = (menciones["Sentimiento"] == "Mala").sum()
    neutras = (menciones["Sentimiento"] == "Neutra").sum()
    partes = []
    if buenas:
        partes.append(f"{buenas} bien")
    if malas:
        partes.append(f"{malas} mal")
    if neutras:
        partes.append(f"{neutras} neutra")
    return f"mencionado {len(menciones)} veces en reseñas ({', '.join(partes)})"


def mostrar_resultados(df_top, r, df_platos):
    if df_top.empty:
        print("\nNo hay ningún restaurante a menos de "
              f"{r['tiempo_maximo_min']:.0f} min en coche. Prueba a ampliar el tiempo.")
        return

    print(f"\n=== TOP {len(df_top)} RESTAURANTES PARA VOSOTROS ===\n")
    for i, (_, fila) in enumerate(df_top.iterrows(), start=1):
        print(f"{i}. {fila['Nombre']}  (score: {fila['Score']:.2f})")
        print(f"   Cocina: {fila['Tipo de cocina']}  |  Precio: {fila['Rango de precios']}  |  "
              f"Rating: {fila['Puntuación']}  ({fila['Nº Reseñas']} reseñas)")
        print(f"   En coche: {fila['Tiempo en coche (min)']:.0f} min  |  Dirección: {fila.get('Dirección', 'N/D')}")

        if r["plato_deseado"]:
            resumen = resumen_mencion_plato(fila["ID"], r["plato_deseado"], df_platos)
            print(f"   Sobre '{r['plato_deseado']}': {resumen}")

        valor = fila.get("Platos mejor valorados")
        if isinstance(valor, str) and valor.strip():
            print(f"   Otros platos destacados del sitio: {formatear_platos(valor)}")
        print()


def main():
    maestro, df_platos = cargar_datos()
    print(f"Cargados {len(maestro)} restaurantes con sus datos combinados.")

    respuestas = hacer_encuesta(maestro)
    df_puntuado = filtrar_y_puntuar(maestro, df_platos, respuestas)
    top5 = df_puntuado.head(TOP_N)

    mostrar_resultados(top5, respuestas, df_platos)


if __name__ == "__main__":
    main()