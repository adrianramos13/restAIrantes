"""
Copia las fotos de restaurantes y sitios de Supabase Storage a Cloudflare R2 (las de perfil se quedan en Supabase).

Solo copia las que aún no están en R2, así que se puede relanzar las veces que haga falta (p. ej. justo después de
cambiar la app a R2, para recoger las que se subieron a Supabase mientras tanto). No borra nada de Supabase.

Necesita la sección [r2] completa en .streamlit/secrets.toml (o las variables R2_*):
    python obtener_datos/migrar_fotos_r2.py            # copia lo que falta
    python obtener_datos/migrar_fotos_r2.py --probar   # solo cuenta lo que falta
"""

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from conexion_supabase import cliente, datos

CARPETAS = ("", "lugares/")   # raíz = restaurantes analizados; lugares/ = ficha rápida. perfiles/ no se migra
HILOS = 4                     # con más, Supabase empieza a cortar descargas


def pendientes(bd):
    """Archivos de Supabase Storage (de CARPETAS) que aún no están en R2."""
    en_supabase = [f["name"] for carpeta in CARPETAS for f in bd.fotos_en_storage(carpeta)]
    ya = bd.fotos_en_r2()
    return [nombre for nombre in en_supabase if nombre not in ya]


def copiar(bd, nombre, intentos=4):
    for intento in range(intentos):   # Supabase corta a ratos cuando se le piden muchas seguidas
        r = requests.get(datos.url_foto(bd.url, nombre), timeout=30)
        if r.ok:
            return bd.subir_foto(nombre, r.content)
        if intento + 1 < intentos:
            time.sleep(2 ** intento)
    raise RuntimeError(f"HTTP {r.status_code}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--probar", action="store_true", help="solo cuenta las fotos que faltan en R2")
    parser.add_argument("--hilos", type=int, default=HILOS)
    args = parser.parse_args()
    bd = cliente()
    if not bd.r2:
        sys.exit("ERROR: falta la sección [r2] completa (url_publica, cuenta, clave_id, clave_secreta, bucket).")
    faltan = pendientes(bd)
    print(f"Faltan {len(faltan)} fotos en R2.")
    if args.probar or not faltan:
        return
    hechas, fallos = 0, []
    with ThreadPoolExecutor(args.hilos) as hilos:
        tareas = {hilos.submit(copiar, bd, nombre): nombre for nombre in faltan}
        for tarea in as_completed(tareas):
            try:
                tarea.result()
                hechas += 1
            except Exception as e:   # una foto rota no para la copia: se reintenta al relanzar
                fallos.append(f"{tareas[tarea]}: {type(e).__name__} {e}")
            if (hechas + len(fallos)) % 500 == 0:
                print(f"  {hechas + len(fallos)}/{len(faltan)}")
    print(f"Copiadas {hechas}; fallos {len(fallos)}.")
    for fallo in fallos[:20]:
        print("  ", fallo)
    if fallos:
        print("Relanza el script para reintentar las que han fallado.")


if __name__ == "__main__":
    main()
