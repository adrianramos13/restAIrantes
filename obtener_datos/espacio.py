"""
Cuánto ocupa la base de datos de Supabase (y las fotos) frente a los límites del plan gratuito, para verlo venir
con tiempo. Necesita supabase/012_ficha_rapida.sql (la función tamano_bd).

USO (desde la raíz del proyecto):
    python obtener_datos/espacio.py
"""

from conexion_supabase import cliente, datos

LIMITE_BD_MB = 500      # plan gratuito de Supabase: base de datos
LIMITE_FOTOS_MB = 1024  # plan gratuito de Supabase: almacenamiento de archivos
AVISO = 0.8             # a partir del 80 % se avisa


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


def main():
    try:
        tamanos = cliente().tamano()
    except datos.ErrorSupabase as e:
        raise SystemExit(f"ERROR: no se puede medir ({str(e)[:150]}). ¿Has ejecutado supabase/012_ficha_rapida.sql?")
    print("\n".join(informe(tamanos)))


if __name__ == "__main__":
    main()
