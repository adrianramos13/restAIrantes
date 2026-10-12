"""
Conexión a Supabase para los scripts de obtener_datos/ (migración y procesador de listas).

Credenciales: variables de entorno SUPABASE_URL y SUPABASE_CLAVE_SERVICIO o, si no están, la
sección [supabase] de .streamlit/secrets.toml (la misma que usa la app). La clave de servicio
da acceso total a la base de datos: solo en tu ordenador y en los secrets de Streamlit.
"""

import os
import sys
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "algoritmo"))
import datos  # noqa: E402  (algoritmo/datos.py, compartido con la app)


def cliente():
    url, clave = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_CLAVE_SERVICIO")
    if not (url and clave):
        ruta = RAIZ / ".streamlit" / "secrets.toml"
        if ruta.exists():
            secciones = tomllib.loads(ruta.read_text(encoding="utf-8")).get("supabase", {})
            url, clave = url or secciones.get("url"), clave or secciones.get("clave_servicio")
    if not (url and clave):
        raise SystemExit(
            "ERROR: faltan las credenciales de Supabase. Ponlas en .streamlit/secrets.toml:\n"
            '  [supabase]\n  url = "https://xxxx.supabase.co"\n  clave_servicio = "..."\n'
            "o en las variables de entorno SUPABASE_URL y SUPABASE_CLAVE_SERVICIO.")
    return datos.Supabase(url, clave)
