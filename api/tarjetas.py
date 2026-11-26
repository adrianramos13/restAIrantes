"""
Filas del catálogo (DataFrames de datos.py) -> JSON para la app móvil. Nunca salen correos: los usuarios
solo se ven por nombre y @alias.
"""

import re

import pandas as pd

from logica import COL_ANADIDO, etiqueta_cocina, platos_destacados


def texto(valor):
    return valor.strip() if isinstance(valor, str) and valor.strip() else None


def numero(valor):
    try:
        return None if valor is None or pd.isna(valor) else float(valor)
    except (TypeError, ValueError):
        return None


def foto(fila, bd, lado=400):
    """Foto principal: la guardada en R2/Supabase; si no hay, la de Google (puede haber caducado)."""
    archivo = texto(fila.get("Imagen archivo"))
    if archivo:
        return bd.url_foto(archivo)
    url = texto(fila.get("Imagen URL"))
    return re.sub(r"=w\d+-h\d+", f"=w{lado}-h{lado}", url) if url else None


def cerrado(fila):
    """'Cerrado temporalmente' / 'Cerrado permanentemente', o None si está abierto."""
    estado = texto(fila.get("Estado")) or ""
    return estado if "cerrado" in estado.lower() else None


def tarjeta(fila, bd):
    """Lo que enseña una tarjeta de restaurante (listas, resultados, mapa)."""
    resenas = numero(fila.get("Nº Reseñas"))
    return {
        "id": int(fila["ID"]), "nombre": str(fila["Nombre"]), "cocina": etiqueta_cocina(fila),
        "precio": texto(fila.get("Rango de precios")), "nota": numero(fila.get("Puntuación")),
        "resenas": int(resenas) if resenas is not None else None, "foto": foto(fila, bd),
        "cerrado": cerrado(fila), "lat": numero(fila.get("Latitud")), "lon": numero(fila.get("Longitud")),
        "anadido_en": texto(fila.get(COL_ANADIDO)),
    }


def tarjetas(df, bd):
    return [tarjeta(fila, bd) for _, fila in df.iterrows()] if not df.empty else []


def ficha(fila, bd):
    """La tarjeta más lo que solo sale en la ficha."""
    return {**tarjeta(fila, bd), "direccion": texto(fila.get("Dirección")),
            "platos": platos_destacados(fila.get("Platos mejor valorados"))}


def visita(fila):
    """Una visita ("He ido") de un DataFrame de datos.visitas_a_dataframe, sin el correo de nadie."""
    return {"restaurante_id": int(fila["ID"]), "nota": numero(fila.get("Nota visita")),
            "comentario": texto(fila.get("Comentario visita")), "fecha": texto(fila.get("Fecha visita")),
            "quien": texto(fila.get("Amigo"))}


def lugar(l, bd):
    """Un sitio de Descubrir (tabla lugares), con su ficha rápida si la tiene."""
    web = l.get("web")
    return {
        "id": l["id"], "nombre": l["nombre"], "lat": l["lat"], "lon": l["lon"],
        "cocina": l.get("cocina_google") or l.get("categoria"), "direccion": l.get("direccion"),
        "ciudad": l.get("ciudad"), "telefono": l.get("telefono"),
        "web": web if isinstance(web, str) and web.startswith(("https://", "http://")) else None,
        "estado": l.get("estado_analisis"), "restaurante_id": l.get("restaurante_id"),
        "nota": l.get("nota_google"), "foto": bd.url_foto(l["foto"]) if l.get("foto") else None,
    }
