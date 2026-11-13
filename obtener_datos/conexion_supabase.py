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


CAMPOS_R2 = ("cuenta", "clave_id", "clave_secreta", "bucket")


def _secretos():
    ruta = RAIZ / ".streamlit" / "secrets.toml"
    return tomllib.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}


def config_r2(secretos):
    """(url_publica, {cuenta, clave_id, clave_secreta, bucket}) de Cloudflare R2: variables R2_URL_PUBLICA, R2_CUENTA,
    R2_CLAVE_ID, R2_CLAVE_SECRETA y R2_BUCKET o la sección [r2] de secrets.toml. Incompleto = (None, None): las fotos
    siguen en Supabase Storage."""
    seccion = secretos.get("r2", {})
    leer = lambda campo: os.environ.get(f"R2_{campo.upper()}") or seccion.get(campo)   # noqa: E731
    r2 = {campo: leer(campo) for campo in CAMPOS_R2}
    if not (leer("url_publica") and all(r2.values())):
        return None, None
    return leer("url_publica"), r2


def cliente():
    url, clave = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_CLAVE_SERVICIO")
    secretos = _secretos()
    if not (url and clave):
        secciones = secretos.get("supabase", {})
        url, clave = url or secciones.get("url"), clave or secciones.get("clave_servicio")
    if not (url and clave):
        raise SystemExit(
            "ERROR: faltan las credenciales de Supabase. Ponlas en .streamlit/secrets.toml:\n"
            '  [supabase]\n  url = "https://xxxx.supabase.co"\n  clave_servicio = "..."\n'
            "o en las variables de entorno SUPABASE_URL y SUPABASE_CLAVE_SERVICIO.")
    fotos_url, r2 = config_r2(secretos)
    return datos.Supabase(url, clave, fotos_url=fotos_url, r2=r2)
