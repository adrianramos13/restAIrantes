"""
Lo que comparten las rutas de la API (principal.py y social.py): configuración, conexión a Supabase, quién
eres (por tu token), tu lista con caché corta y el límite de peticiones.
"""

import os
import sys
import threading
import time
import tomllib
from functools import lru_cache
from pathlib import Path as Ruta
from typing import Annotated

RAIZ = Ruta(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "algoritmo"))
from fastapi import Depends, Header, HTTPException, Path, Request  # noqa: E402

import datos  # noqa: E402
from cuentas import Cuentas, ErrorCuenta  # noqa: E402

SEG_TOKEN = 300            # cuánto se recuerda de quién es un token sin volver a preguntar a Supabase
SEG_LISTA = 60             # cuánto se recuerda la lista de un usuario (se olvida al cambiarla)
NO_SE_PUEDE = "No se ha podido hacer ahora mismo. Inténtalo en un momento."
ID_MAX = 2**31 - 1   # ids de restaurantes: enteros de Postgres
Id = Annotated[int, Path(ge=1, le=ID_MAX)]


@lru_cache
def configuracion():
    ruta = RAIZ / ".streamlit" / "secrets.toml"
    s = tomllib.loads(ruta.read_text(encoding="utf-8")) if ruta.is_file() else {}
    c = {"url": os.environ.get("SUPABASE_URL") or s.get("supabase", {}).get("url"),
         "clave": os.environ.get("SUPABASE_CLAVE_SERVICIO") or s.get("supabase", {}).get("clave_servicio"),
         "fotos_url": os.environ.get("R2_URL_PUBLICA") or s.get("r2", {}).get("url_publica"),
         "ors": os.environ.get("ORS_API_KEY") or s.get("ORS_API_KEY")}
    if not c["url"] or not c["clave"]:
        raise RuntimeError("Falta la configuración de Supabase (SUPABASE_URL y SUPABASE_CLAVE_SERVICIO).")
    return c


@lru_cache
def obtener_bd():
    c = configuracion()
    return datos.Supabase(c["url"], c["clave"], fotos_url=c["fotos_url"])


@lru_cache
def obtener_cuentas():
    c = configuracion()
    return Cuentas(c["url"], c["clave"])


_tokens = {}   # token -> ({id, correo, nombre}, hasta cuándo vale)


def usuario_actual(authorization: str | None = Header(None), cuentas=Depends(obtener_cuentas)):
    """{id, correo, nombre} del dueño del token "Authorization: Bearer ..."; 401 si no hay o no vale."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Inicia sesión.")
    token, ahora = authorization[7:].strip(), time.monotonic()
    if not token:   # sin token, Supabase recibiría la clave de servicio en su lugar (cuentas._pedir)
        raise HTTPException(401, "Inicia sesión.")
    guardado = _tokens.get(token)
    if guardado and guardado[1] > ahora:
        return guardado[0]
    try:
        usuario = cuentas.usuario(token)
    except ErrorCuenta as e:
        raise HTTPException(401, str(e)) from e
    if len(_tokens) > 10_000:
        _tokens.clear()
    _tokens[token] = (usuario, ahora + SEG_TOKEN)
    return usuario


def olvidar_tokens_de(correo):
    """Tras borrar una cuenta: sus tokens dejan de valer aquí al momento (no a los 5 minutos)."""
    for token in [t for t, (u, _) in _tokens.items() if u["correo"] == correo]:
        _tokens.pop(token, None)


# ----------------------- la lista del usuario (con caché corta) ----------------------- #

_listas = {}   # correo -> ((maestro, df_platos, lista), hasta cuándo vale)


def mi_lista(bd, correo):
    guardada = _listas.get(correo)
    if guardada and guardada[1] > time.monotonic():
        return guardada[0]
    datos_lista = bd.restaurantes_de(correo)
    _listas[correo] = (datos_lista, time.monotonic() + SEG_LISTA)
    return datos_lista


def olvidar_lista(correo):
    _listas.pop(correo, None)


# ----------------------- límite de peticiones ----------------------- #
# ponytail: en memoria y por proceso; con varios procesos o servidores, pasarlo a Redis o al proxy.

_usos = {}   # (nombre, quién) -> momentos de sus últimas peticiones
_cerrojo = threading.Lock()


def limite(nombre, veces, segundos):
    """Dependencia: más de `veces` peticiones de `nombre` en `segundos` de la misma sesión (o IP, sin sesión) -> 429."""
    def comprobar(request: Request, authorization: str | None = Header(None)):
        quien = authorization or (request.client.host if request.client else "?")
        ahora = time.monotonic()
        with _cerrojo:
            if len(_usos) > 50_000:
                _usos.clear()
            usos = [t for t in _usos.get((nombre, quien), ()) if t > ahora - segundos]
            if len(usos) >= veces:
                raise HTTPException(429, "Vas muy rápido: espera un momento y vuelve a probar.")
            _usos[(nombre, quien)] = usos + [ahora]
    return comprobar


def validado(funcion, *args, **kwargs):
    """Llama a una función de datos.py y convierte sus ValueError (mensajes para el usuario) en un 400."""
    try:
        return funcion(*args, **kwargs)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
