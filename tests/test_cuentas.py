"""Cuentas con correo y contraseña (algoritmo/cuentas.py) con un Supabase Auth falso: sin red."""

import pytest

import cuentas
from cuentas import Cuentas, ErrorCuenta

USUARIO = {"email": "Ana@Ejemplo.com", "email_confirmed_at": "2026-10-13T10:00:00Z",
           "user_metadata": {"nombre": "Ana"}}
SESION = {"access_token": "acc", "refresh_token": "ren", "user": USUARIO}


class Respuesta:
    def __init__(self, cuerpo, estado=200):
        self._cuerpo, self.status_code = cuerpo, estado
        self.ok, self.content = estado < 400, b"x"

    def json(self):
        return self._cuerpo


@pytest.fixture
def auth(monkeypatch):
    """Supabase Auth falso: `respuestas[ruta]` = (cuerpo, código). Apunta las peticiones en `pedidas`."""
    estado = {"respuestas": {}, "pedidas": []}

    def request(metodo, url, json=None, params=None, headers=None, timeout=None):
        ruta = url.split("/auth/v1", 1)[1]
        estado["pedidas"].append((metodo, ruta, json, params, headers))
        return Respuesta(*estado["respuestas"].get(ruta, ({}, 200)))
    monkeypatch.setattr(cuentas.requests, "request", request)
    estado["cuentas"] = Cuentas("https://x.supabase.co", "sb_secret_abc")
    return estado


def test_registrar_pide_confirmar_el_correo(auth):
    auth["respuestas"]["/signup"] = ({"id": "u1", "email": "ana@ejemplo.com"}, 200)
    auth["cuentas"].registrar(" Ana@Ejemplo.com ", "secreta123", " Ana ")
    metodo, ruta, cuerpo, _, cabeceras = auth["pedidas"][-1]
    assert (metodo, ruta) == ("POST", "/signup")
    assert cuerpo == {"email": "ana@ejemplo.com", "password": "secreta123", "data": {"nombre": "Ana"}}
    assert cabeceras == {"apikey": "sb_secret_abc"}


def test_registrar_rechaza_si_supabase_no_obliga_a_confirmar(auth):
    auth["respuestas"]["/signup"] = (SESION, 200)   # devuelve sesión: se ha confirmado sola
    with pytest.raises(ErrorCuenta, match="Confirm email"):
        auth["cuentas"].registrar("ana@ejemplo.com", "secreta123", "Ana")


@pytest.mark.parametrize("correo, contrasena, nombre", [
    ("sin-arroba", "secreta123", "Ana"), ("ana@ejemplo", "secreta123", "Ana"),
    ("ana@ejemplo.com", "corta", "Ana"), ("ana@ejemplo.com", "secreta123", "  "),
])
def test_registrar_valida_antes_de_llamar(auth, correo, contrasena, nombre):
    with pytest.raises(ErrorCuenta):
        auth["cuentas"].registrar(correo, contrasena, nombre)
    assert auth["pedidas"] == []


def test_entrar(auth):
    auth["respuestas"]["/token"] = (SESION, 200)
    sesion = auth["cuentas"].entrar("ANA@ejemplo.com", "secreta123")
    assert sesion == {"correo": "ana@ejemplo.com", "nombre": "Ana", "acceso": "acc", "renovacion": "ren"}
    assert auth["pedidas"][-1][3] == {"grant_type": "password"}


@pytest.mark.parametrize("cuerpo, estado, texto", [
    ({"error_code": "invalid_credentials"}, 400, "incorrectos"),
    ({"error": "invalid_grant"}, 400, "incorrectos"),
    ({"error_code": "email_not_confirmed"}, 400, "confirmado"),
    ({}, 429, "Demasiados intentos"),
    ({"error_code": "algo_raro"}, 500, "No se ha podido"),
])
def test_errores_con_mensaje_para_el_usuario(auth, cuerpo, estado, texto):
    auth["respuestas"]["/token"] = (cuerpo, estado)
    with pytest.raises(ErrorCuenta, match=texto):
        auth["cuentas"].entrar("ana@ejemplo.com", "x")


def test_sesion_sin_correo_confirmado_no_vale(auth):
    auth["respuestas"]["/token"] = ({**SESION, "user": {**USUARIO, "email_confirmed_at": None}}, 200)
    with pytest.raises(ErrorCuenta, match="confirmado"):
        auth["cuentas"].renovar("ren")


def test_confirmacion_obligatoria(auth):
    auth["respuestas"]["/settings"] = ({"mailer_autoconfirm": False}, 200)
    assert auth["cuentas"].confirmacion_obligatoria() is True
    auth["respuestas"]["/settings"] = ({"mailer_autoconfirm": True}, 200)
    assert auth["cuentas"].confirmacion_obligatoria() is False
    auth["respuestas"]["/settings"] = ({}, 500)   # si no se sabe, no se arriesga
    assert auth["cuentas"].confirmacion_obligatoria() is False


def test_sin_red(monkeypatch):
    def sin_red(*a, **k):
        raise cuentas.requests.ConnectionError("sin red")
    monkeypatch.setattr(cuentas.requests, "request", sin_red)
    with pytest.raises(ErrorCuenta, match="conectar"):
        Cuentas("https://x.supabase.co", "k").entrar("ana@ejemplo.com", "secreta123")


def test_cambiar_contrasena_con_codigo(auth):
    auth["respuestas"]["/verify"] = (SESION, 200)
    auth["cuentas"].cambiar_contrasena_con_codigo("ana@ejemplo.com", " 123456 ", "nueva-secreta")
    (_, r1, c1, _, _), (m2, r2, c2, _, h2) = auth["pedidas"]
    assert (r1, c1) == ("/verify", {"type": "recovery", "email": "ana@ejemplo.com", "token": "123456"})
    assert (m2, r2, c2, h2["Authorization"]) == ("PUT", "/user", {"password": "nueva-secreta"}, "Bearer acc")
    with pytest.raises(ErrorCuenta):
        auth["cuentas"].cambiar_contrasena_con_codigo("ana@ejemplo.com", "123456", "corta")
