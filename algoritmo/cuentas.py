"""
Cuentas con correo y contraseña (además de Google), con Supabase Auth: Supabase guarda las
contraseñas (cifradas), manda el correo de confirmación y el código para recuperar la contraseña.
Sin Streamlit (la app guarda la sesión). Configuración en Supabase: ver README ("Cuentas con
contraseña").

Seguridad: el usuario se identifica por su CORREO, igual que con Google, así que alguien con
contraseña y una cuenta de Google con el mismo correo son la misma persona. Eso solo es seguro si
Supabase obliga a confirmar el correo antes de entrar; si está desactivado, aquí no se deja usar.
"""

import requests

TIMEOUT_S = 20
# Registrarse y pedir el código hacen que Supabase envíe un correo ANTES de responder: con el SMTP lento
# puede tardar, y Supabase corta a los ~35 s (504). Se espera un poco más que él para ver su respuesta.
TIMEOUT_CORREO_S = 45
LARGO_MIN_CONTRASENA = 8


class ErrorCuenta(Exception):
    """Error que se puede enseñar tal cual al usuario."""


# Códigos de error de Supabase Auth -> mensaje para el usuario.
_MENSAJES = {
    "invalid_credentials": "Correo o contraseña incorrectos.",
    "email_not_confirmed": "Todavía no has confirmado tu correo: abre el enlace que te enviamos al registrarte.",
    "user_already_exists": "Ya hay una cuenta con ese correo. Entra con tu contraseña o recupérala.",
    "email_exists": "Ya hay una cuenta con ese correo. Entra con tu contraseña o recupérala.",
    "weak_password": f"La contraseña es demasiado débil: usa al menos {LARGO_MIN_CONTRASENA} caracteres.",
    "over_request_rate_limit": "Demasiados intentos seguidos. Espera unos minutos y vuelve a probar.",
    "over_email_send_rate_limit": "Hemos enviado demasiados correos. Espera unos minutos y vuelve a probar.",
    "otp_expired": "El código no es correcto o ha caducado. Pide otro.",
    "validation_failed": "Revisa el correo: no parece válido.",
}
SIN_CORREO = ("No se ha podido enviar el correo ahora mismo, así que no se ha hecho nada. Inténtalo más tarde; "
              "si sigue pasando, avisa al administrador (tiene que revisar el envío de correos en Supabase).")


def validar_registro(correo, contrasena, nombre):
    correo = (correo or "").strip().lower()
    if "@" not in correo or "." not in correo.split("@")[-1] or len(correo) > 254:
        raise ErrorCuenta("Escribe un correo válido.")
    if len(contrasena or "") < LARGO_MIN_CONTRASENA:
        raise ErrorCuenta(f"La contraseña tiene que tener al menos {LARGO_MIN_CONTRASENA} caracteres.")
    if not (nombre or "").strip():
        raise ErrorCuenta("Escribe tu nombre.")
    return correo


class Cuentas:
    def __init__(self, url, clave):
        self.url = url.rstrip("/") + "/auth/v1"
        self._cabeceras = {"apikey": clave}
        if not clave.startswith("sb_"):   # las claves antiguas son JWT y van también como Bearer
            self._cabeceras["Authorization"] = f"Bearer {clave}"

    def _pedir(self, metodo, ruta, *, json=None, params=None, token=None, envia_correo=False):
        """`envia_correo`: Supabase manda un correo antes de responder (registro, código de recuperación)."""
        cabeceras = dict(self._cabeceras)
        if token:
            cabeceras["Authorization"] = f"Bearer {token}"
        try:
            r = requests.request(metodo, self.url + ruta, json=json, params=params, headers=cabeceras,
                                 timeout=TIMEOUT_CORREO_S if envia_correo else TIMEOUT_S)
        except requests.Timeout as e:
            raise ErrorCuenta(SIN_CORREO if envia_correo else "Supabase no responde ahora mismo. Inténtalo en un momento.") from e
        except requests.RequestException as e:
            raise ErrorCuenta("No se puede conectar ahora mismo. Inténtalo en un momento.") from e
        try:
            cuerpo = r.json() if r.content else {}
        except ValueError:   # p. ej. el 504 "upstream request timeout" de Supabase viene en texto plano
            cuerpo = {}
        if envia_correo and r.status_code >= 500:   # el correo no ha salido (SMTP mal configurado o caído)
            raise ErrorCuenta(SIN_CORREO)
        if not r.ok:
            codigo = cuerpo.get("error_code") or cuerpo.get("error") or ""
            if r.status_code == 429:
                codigo = codigo if codigo in _MENSAJES else "over_request_rate_limit"
            if codigo == "invalid_grant":   # versiones antiguas de Supabase Auth
                codigo = "invalid_credentials"
            raise ErrorCuenta(_MENSAJES.get(codigo, "No se ha podido completar. Inténtalo en un momento."))
        return cuerpo

    def confirmacion_obligatoria(self):
        """¿Obliga Supabase a confirmar el correo antes de entrar? Si no (o no se sabe), las cuentas con
        contraseña no son seguras: cualquiera podría registrarse con el correo de otro y ver su lista."""
        try:
            return self._pedir("GET", "/settings").get("mailer_autoconfirm") is False
        except ErrorCuenta:
            return False

    def registrar(self, correo, contrasena, nombre):
        """Crea la cuenta; Supabase manda el correo de confirmación. No inicia sesión."""
        correo = validar_registro(correo, contrasena, nombre)
        respuesta = self._pedir("POST", "/signup", envia_correo=True,
                                json={"email": correo, "password": contrasena, "data": {"nombre": nombre.strip()}})
        if respuesta.get("access_token"):   # se ha confirmado sola: la confirmación está desactivada
            raise ErrorCuenta("La cuenta se ha creado sin confirmar el correo. El administrador tiene que "
                              "activar 'Confirm email' en Supabase antes de usar cuentas con contraseña.")

    def entrar(self, correo, contrasena):
        return _sesion(self._pedir("POST", "/token", params={"grant_type": "password"},
                                   json={"email": (correo or "").strip().lower(), "password": contrasena or ""}))

    def renovar(self, token_renovacion):
        """Sesión guardada (cookie) -> sesión nueva. Supabase cambia el token de renovación en cada uso."""
        return _sesion(self._pedir("POST", "/token", params={"grant_type": "refresh_token"},
                                   json={"refresh_token": token_renovacion}))

    def salir(self, token_acceso):
        try:
            self._pedir("POST", "/logout", token=token_acceso)
        except ErrorCuenta:
            pass   # si ya había caducado, da igual: la cookie se borra de todas formas

    def pedir_codigo_recuperacion(self, correo):
        """Supabase manda un correo con un código de 6 cifras (plantilla "Reset password" con {{ .Token }})."""
        self._pedir("POST", "/recover", json={"email": (correo or "").strip().lower()}, envia_correo=True)

    def cambiar_contrasena_con_codigo(self, correo, codigo, contrasena_nueva):
        if len(contrasena_nueva or "") < LARGO_MIN_CONTRASENA:
            raise ErrorCuenta(f"La contraseña tiene que tener al menos {LARGO_MIN_CONTRASENA} caracteres.")
        sesion = _sesion(self._pedir("POST", "/verify", json={
            "type": "recovery", "email": (correo or "").strip().lower(), "token": (codigo or "").strip()}))
        self._pedir("PUT", "/user", json={"password": contrasena_nueva}, token=sesion["acceso"])
        return sesion


def _sesion(respuesta):
    usuario = respuesta.get("user") or {}
    if not usuario.get("email") or not usuario.get("email_confirmed_at"):
        raise ErrorCuenta(_MENSAJES["email_not_confirmed"])
    return {"correo": usuario["email"].lower(), "nombre": (usuario.get("user_metadata") or {}).get("nombre"),
            "acceso": respuesta["access_token"], "renovacion": respuesta["refresh_token"]}
