"""
Cuánto ocupa la base de datos de Supabase (y las fotos) frente a los límites del plan gratuito, para verlo venir
con tiempo. Necesita supabase/012_ficha_rapida.sql (la función tamano_bd).

USO (desde la raíz del proyecto):
    python obtener_datos/espacio.py
    python obtener_datos/espacio.py --reducir-fotos [--limite 5]   # recomprime las fotos grandes de restaurantes
"""

import argparse

import requests

from conexion_supabase import cliente, datos
from verificar_lugares import LADO_FOTO_RESTAURANTE, reducir_foto

LIMITE_BD_MB = 500      # plan gratuito de Supabase: base de datos
LIMITE_FOTOS_MB = 1024  # plan gratuito de Supabase: almacenamiento de archivos
AVISO = 0.8             # a partir del 80 % se avisa
REDUCIR_DESDE_KB = 40   # las fotos que ya ocupan menos se dejan como están


def informe(tamanos):
    """Líneas de texto con lo que ocupa cada cosa (de {qué: bytes})."""
    mb = {que: b / 1024 / 1024 for que, b in tamanos.items()}
    lineas = []
    for que, limite in (("base de datos", LIMITE_BD_MB), ("fotos", LIMITE_FOTOS_MB)):
        uso = mb.get(que, 0)
        aviso = "  <-- ¡AVISO! cerca del límite" if uso >= AVISO * limite else ""
        lineas.append(f"{que.capitalize()}: {uso:.1f} MB de {limite} MB ({uso / limite:.0%}){aviso}")
    lineas.append("Tablas que más ocupan:")
    tablas = sorted(((q[6:], m) for q, m in mb.items() if q.startswith("tabla ")), key=lambda t: -t[1])
    lineas += [f"  {nombre}: {m:.1f} MB" for nombre, m in tablas[:8]]
    return lineas


def reducir_fotos(bd, limite=None):
    """Recomprime a LADO_FOTO_RESTAURANTE px las fotos de restaurantes (raíz del almacenamiento; no las de la ficha
    rápida ni las de perfil) de más de REDUCIR_DESDE_KB. Devuelve (cuántas, MB ahorrados)."""
    grandes = [f for f in bd.fotos_en_storage() if f["size"] > REDUCIR_DESDE_KB * 1024][:limite]
    ahorro = 0
    for i, foto in enumerate(grandes, 1):
        r = requests.get(bd.url_foto(foto["name"]), timeout=30)
        r.raise_for_status()
        nueva = reducir_foto(r.content, LADO_FOTO_RESTAURANTE)
        if nueva and len(nueva) < len(r.content):
            bd.subir_foto(foto["name"], nueva)
            ahorro += len(r.content) - len(nueva)
        if i % 100 == 0:
            print(f"  {i}/{len(grandes)} · ahorrados {ahorro / 2**20:.1f} MB")
    return len(grandes), ahorro / 2**20


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reducir-fotos", action="store_true", help="recomprime las fotos grandes de restaurantes")
    parser.add_argument("--limite", type=int, help="con --reducir-fotos: solo las N primeras (para probar)")
    args = parser.parse_args()
    if args.reducir_fotos:
        cuantas, mb = reducir_fotos(cliente(), args.limite)
        print(f"Fotos reducidas: {cuantas} · ahorrados {mb:.1f} MB")
    try:
        tamanos = cliente().tamano()
    except datos.ErrorSupabase as e:
        raise SystemExit(f"ERROR: no se puede medir ({str(e)[:150]}). ¿Has ejecutado supabase/012_ficha_rapida.sql?")
    print("\n".join(informe(tamanos)))


if __name__ == "__main__":
    main()
