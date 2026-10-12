"""
Modo de la app y usuario actual. Va aparte de app.py para que los tests puedan sustituirlo.

- Modo LOCAL (el de siempre): sin [auth] y [supabase] en los secrets, o con la variable de
  entorno RESTAIRANTES_MODO=local (la usan los tests). Una sola lista: excels/ e imagenes/.
- Modo MULTIUSUARIO: con [auth] (login de Google) y [supabase] en los secrets. Cada usuario
  entra con su cuenta de Google y ve su propia lista, guardada en Supabase.
"""

import os

import streamlit as st


def config_multiusuario():
    """{"url", "clave_servicio", "permitidos"} si la app va en modo multiusuario; None si va en local."""
    if os.environ.get("RESTAIRANTES_MODO") == "local":
        return None
    try:
        secretos = st.secrets
        if "auth" not in secretos or "supabase" not in secretos:
            return None
        return {
            "url": secretos["supabase"]["url"],
            "clave_servicio": secretos["supabase"]["clave_servicio"],
            # vacío = cualquier cuenta de Google puede entrar
            "permitidos": [c.strip().lower() for c in secretos.get("usuarios_permitidos", [])],
        }
    except Exception:   # sin archivo de secrets, st.secrets lanza al leerlo
        return None


def usuario_actual():
    """Correo (en minúsculas) del usuario con sesión iniciada, o None."""
    return st.user.email.lower() if st.user.is_logged_in and st.user.get("email") else None
