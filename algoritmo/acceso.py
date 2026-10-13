"""
Entrar con correo y contraseña (además de Google): formularios, sesión y cookie. La parte de
Supabase Auth está en cuentas.py; aquí solo lo que necesita Streamlit.

La sesión con contraseña vive en st.session_state["cuenta"] mientras la pestaña está abierta. Para no
pedir la contraseña cada vez, el token de renovación se guarda en una cookie (30 días) y al volver a
abrir la app se cambia por una sesión nueva (cuentas.renovar).
"""

import urllib.parse
from pathlib import Path

import streamlit as st

from cuentas import ErrorCuenta
from datos import validar_nombre

COOKIE_SESION = "restairantes_sesion"
DURACION_COOKIE_S = 30 * 24 * 3600
_COMPONENTES = Path(__file__).resolve().parent / "componentes"

_HTML_COOKIE = (_COMPONENTES / "cookie.html").read_text(encoding="utf-8")
_JS_COOKIE = (_COMPONENTES / "cookie.js").read_text(encoding="utf-8")


def _cookie(**kwargs):
    # Se registra en cada uso, como los componentes de app.py (que se registran en cada ejecución):
    # registrado una sola vez al importar este módulo, deja de existir si Streamlit reinicia su registro.
    st.components.v2.component("cookie_sesion", html=_HTML_COOKIE, js=_JS_COOKIE)(**kwargs)


def usuario_con_contrasena(cuentas):
    """Sesión con contraseña ({correo, nombre, acceso, renovacion}) de esta pestaña o, si no hay, la
    guardada en la cookie. None si no hay ninguna."""
    sesion = st.session_state.get("cuenta")
    if sesion is None and not st.session_state.get("cookie_borrar"):
        guardada = st.context.cookies.get(COOKIE_SESION)
        if isinstance(guardada, str) and guardada:   # sin navegador (AppTest) no hay cookies de verdad
            try:
                sesion = cuentas.renovar(urllib.parse.unquote(guardada))
            except ErrorCuenta:   # caducada, cerrada en otro sitio o sin red: hay que volver a entrar
                st.session_state["cookie_borrar"] = True
            else:
                st.session_state["cuenta"] = sesion
    return sesion


def sincronizar_cookie():
    """Deja la cookie como la sesión: con el token de renovación actual, o borrada al salir."""
    sesion = st.session_state.get("cuenta")
    if sesion:
        _cookie(key="cookie_sesion", data={"nombre": COOKIE_SESION, "valor": sesion["renovacion"],
                                           "segundos": DURACION_COOKIE_S})
    elif st.session_state.get("cookie_borrar"):
        _cookie(key="cookie_sesion", data={"nombre": COOKIE_SESION, "valor": None})


def _empezar(sesion):
    st.session_state["cuenta"] = sesion
    st.session_state.pop("cookie_borrar", None)
    st.rerun()


def cerrar_sesion(cuentas):
    """Callback de "Cerrar sesión": con contraseña, cierra la sesión en Supabase y borra la cookie;
    con Google, st.logout()."""
    sesion = st.session_state.pop("cuenta", None)
    if sesion is None:
        st.logout()
        return
    cuentas.salir(sesion["acceso"])
    st.session_state["cookie_borrar"] = True


def formulario_cuentas(cuentas):
    """Entrar / Crear cuenta / Recuperar contraseña, debajo del botón de Google."""
    modo = st.segmented_control("Cuenta", ["Entrar", "Crear cuenta"], default="Entrar", key="modo_acceso",
                                label_visibility="collapsed", width="stretch") or "Entrar"
    if modo == "Entrar":
        _formulario_entrar(cuentas)
        _recuperar_contrasena(cuentas)
    else:
        _formulario_registro(cuentas)


def _formulario_entrar(cuentas):
    with st.form("entrar", border=False):
        correo = st.text_input("Correo", autocomplete="email", key="entrar_correo")
        contrasena = st.text_input("Contraseña", type="password", autocomplete="current-password",
                                   key="entrar_contrasena")
        if st.form_submit_button("Entrar", type="primary", width="stretch"):
            try:
                sesion = cuentas.entrar(correo, contrasena)
            except ErrorCuenta as e:
                st.error(str(e))
            else:
                _empezar(sesion)


def _formulario_registro(cuentas):
    with st.form("registro", border=False):
        nombre = st.text_input("Nombre", max_chars=40, key="registro_nombre", autocomplete="name")
        correo = st.text_input("Correo", key="registro_correo", autocomplete="email")
        contrasena = st.text_input("Contraseña", type="password", key="registro_contrasena",
                                   autocomplete="new-password", help="Al menos 8 caracteres.")
        repetida = st.text_input("Repite la contraseña", type="password", key="registro_repetida",
                                 autocomplete="new-password")
        if st.form_submit_button("Crear cuenta", type="primary", width="stretch"):
            if contrasena != repetida:
                st.error("Las dos contraseñas no coinciden.")
                return
            try:
                cuentas.registrar(correo, contrasena, validar_nombre(nombre))
            except (ErrorCuenta, ValueError) as e:
                st.error(str(e))
            else:
                st.success(f"¡Listo! Te hemos enviado un correo a {correo.strip().lower()}. Ábrelo para confirmar "
                           "tu cuenta y después entra con tu contraseña.")


def _recuperar_contrasena(cuentas):
    with st.expander("¿Has olvidado tu contraseña?"):
        correo = st.text_input("Correo de tu cuenta", key="recuperar_correo", autocomplete="email")
        if st.button("Enviarme un código", width="stretch", key="pedir_codigo"):
            try:
                cuentas.pedir_codigo_recuperacion(correo)
            except ErrorCuenta as e:
                st.error(str(e))
            else:   # no se dice si el correo tiene cuenta o no
                st.session_state["codigo_pedido"] = True
                st.info("Si hay una cuenta con ese correo, te llegará un código de 6 cifras.")
        if not st.session_state.get("codigo_pedido"):
            return
        codigo = st.text_input("Código del correo", max_chars=10, key="recuperar_codigo")
        nueva = st.text_input("Contraseña nueva", type="password", key="recuperar_nueva",
                              autocomplete="new-password")
        if st.button("Cambiar contraseña y entrar", type="primary", width="stretch", key="cambiar_contrasena"):
            try:
                sesion = cuentas.cambiar_contrasena_con_codigo(correo, codigo, nueva)
            except ErrorCuenta as e:
                st.error(str(e))
            else:
                st.session_state.pop("codigo_pedido", None)
                _empezar(sesion)
