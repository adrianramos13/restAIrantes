"""
Servicios externos: geocodificar la dirección (Nominatim) y calcular los minutos hasta cada
restaurante (OSRM en coche, OpenRouteService andando), con respaldo en línea recta si fallan.
Sin Streamlit: la clave de OpenRouteService la pasa quien llama.
"""

import math
import time

import pandas as pd
import requests

OSRM_URL = "https://router.project-osrm.org/table/v1/driving/"
OSRM_BATCH_SIZE = 100
VELOCIDAD_RESPALDO_COCHE_KMH = 30
ORS_URL = "https://api.openrouteservice.org/v2/matrix/foot-walking"
ORS_BATCH_SIZE = 50
VELOCIDAD_RESPALDO_ANDANDO_KMH = 5
CAJA_MADRID = [(41.17, -4.58), (39.88, -3.05)]   # Comunidad de Madrid (esquinas NO y SE)


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def geocodificar_direccion(direccion):
    """Devuelve el Location de geopy (o None si no la encuentra). Solo busca dentro de la
    Comunidad de Madrid y añade "Madrid" al texto: sin eso, "Chueca" acababa en Toledo y
    "Calle Princesa 1" en Marbella. Si el servicio falla, la excepción sube (no es lo mismo
    que "no existe esa dirección")."""
    from geopy.geocoders import Nominatim

    consulta = direccion if "madrid" in direccion.lower() else f"{direccion}, Madrid"
    geolocalizador = Nominatim(user_agent="app_restaurantes_pareja")
    return geolocalizador.geocode(consulta, timeout=10, viewbox=CAJA_MADRID, bounded=True)


def obtener_minutos_coche(ubicacion_usuario, maestro):
    lat_u, lon_u = ubicacion_usuario
    minutos = [None] * len(maestro)

    indices_validos = [
        i for i in range(len(maestro))
        if pd.notna(maestro.iloc[i]["Latitud"]) and pd.notna(maestro.iloc[i]["Longitud"])
    ]

    for start in range(0, len(indices_validos), OSRM_BATCH_SIZE):
        lote_idx = indices_validos[start:start + OSRM_BATCH_SIZE]
        coords = [f"{lon_u},{lat_u}"] + [
            f"{maestro.iloc[i]['Longitud']},{maestro.iloc[i]['Latitud']}" for i in lote_idx
        ]
        url = OSRM_URL + ";".join(coords)
        try:
            resp = requests.get(url, params={"sources": "0", "annotations": "duration"}, timeout=30)
            resp.raise_for_status()
            duraciones = resp.json()["durations"][0]
            for j, idx in enumerate(lote_idx):
                dur_seg = duraciones[j + 1]
                if dur_seg is not None:
                    minutos[idx] = dur_seg / 60.0
        except Exception:
            for idx in lote_idx:
                fila = maestro.iloc[idx]
                dist_km = haversine_km(lat_u, lon_u, fila["Latitud"], fila["Longitud"])
                minutos[idx] = (dist_km / VELOCIDAD_RESPALDO_COCHE_KMH) * 60

        if start + OSRM_BATCH_SIZE < len(indices_validos):
            time.sleep(1)

    return minutos


def obtener_minutos_a_pie(ubicacion_usuario, maestro, api_key):
    """
    Igual que obtener_minutos_coche pero vía OpenRouteService (perfil
    foot-walking). El modo a pie de la matriz de ORS falla a veces con un
    error 6099 ('Unable to compute a distance/duration matrix') en ciertas
    coordenadas -es un bug conocido de su lado, no nuestro-, así que ante
    cualquier fallo caemos también a una estimación por distancia en línea
    recta a velocidad media andando (5 km/h).
    """
    lat_u, lon_u = ubicacion_usuario
    minutos = [None] * len(maestro)

    indices_validos = [
        i for i in range(len(maestro))
        if pd.notna(maestro.iloc[i]["Latitud"]) and pd.notna(maestro.iloc[i]["Longitud"])
    ]

    def respaldo_haversine(idx):
        fila = maestro.iloc[idx]
        dist_km = haversine_km(lat_u, lon_u, fila["Latitud"], fila["Longitud"])
        return (dist_km / VELOCIDAD_RESPALDO_ANDANDO_KMH) * 60

    if not api_key:   # sin clave: línea recta (quien llama avisa al usuario)
        for idx in indices_validos:
            minutos[idx] = respaldo_haversine(idx)
        return minutos

    headers = {"Authorization": api_key, "Content-Type": "application/json"}

    for start in range(0, len(indices_validos), ORS_BATCH_SIZE):
        lote_idx = indices_validos[start:start + ORS_BATCH_SIZE]
        locations = [[lon_u, lat_u]] + [
            [maestro.iloc[i]["Longitud"], maestro.iloc[i]["Latitud"]] for i in lote_idx
        ]
        body = {"locations": locations, "sources": [0], "metrics": ["duration"]}
        try:
            resp = requests.post(ORS_URL, json=body, headers=headers, timeout=30)
            resp.raise_for_status()
            duraciones = resp.json()["durations"][0]
            for j, idx in enumerate(lote_idx):
                dur_seg = duraciones[j + 1]
                minutos[idx] = dur_seg / 60.0 if dur_seg is not None else respaldo_haversine(idx)
        except Exception:
            for idx in lote_idx:
                minutos[idx] = respaldo_haversine(idx)

        if start + ORS_BATCH_SIZE < len(indices_validos):
            time.sleep(2)

    return minutos

