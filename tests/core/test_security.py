from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core import security
from app.core.config import settings


def _token(**cambios):
    """Token con los claims válidos, cambiando o quitando los indicados (valor None = quitar)."""
    ahora = datetime.now(timezone.utc)
    claims = {"sub": "7", "iss": security.EMISOR, "iat": ahora, "exp": ahora + timedelta(minutes=5)}
    claims.update(cambios)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


class TestPassword:
    def test_el_hash_no_contiene_la_contrasena_y_se_verifica(self):
        h = security.hashear_password("Mi-clave-segura-1")
        assert "Mi-clave" not in h and h.startswith("$argon2id$")
        assert security.verificar_password("Mi-clave-segura-1", h)

    def test_contrasena_incorrecta(self):
        assert not security.verificar_password("otra", security.hashear_password("Mi-clave-segura-1"))

    def test_dos_hashes_de_la_misma_contrasena_son_distintos(self):
        assert security.hashear_password("igual-igual") != security.hashear_password("igual-igual")

    def test_hash_invalido_o_inexistente_da_false_sin_lanzar(self):
        assert not security.verificar_password("x", "esto-no-es-un-hash")
        assert not security.verificar_password("x", None)

    def test_usuario_inexistente_nunca_autentica_ni_con_la_contrasena_de_relleno(self):
        assert not security.verificar_password("contrasena-que-nadie-usa", None)

    def test_el_hash_actual_no_pide_rehash(self):
        assert not security.necesita_rehash(security.hashear_password("abc12345"))


class TestToken:
    def test_ida_y_vuelta(self):
        token, segundos = security.crear_token(42)
        assert security.leer_token(token) == 42
        assert segundos == settings.access_token_minutes * 60

    def test_expirado(self):
        pasado = datetime.now(timezone.utc) - timedelta(hours=2)
        with pytest.raises(security.TokenInvalido):
            security.leer_token(security.crear_token(1, ahora=pasado)[0])

    def test_firmado_con_otra_clave(self):
        malo = jwt.encode({"sub": "1", "iss": security.EMISOR, "iat": datetime.now(timezone.utc),
                           "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
                          "otra-clave-distinta-de-32-caracteres-o-mas", algorithm="HS256")
        with pytest.raises(security.TokenInvalido):
            security.leer_token(malo)

    def test_token_modificado(self):
        token = _token()
        cabecera, cuerpo, firma = token.split(".")
        with pytest.raises(security.TokenInvalido):
            security.leer_token(f"{cabecera}.{cuerpo}x.{firma}")

    def test_algoritmo_none_se_rechaza(self):
        sin_firma = jwt.encode({"sub": "1", "iss": security.EMISOR,
                                "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, key=None, algorithm="none")
        with pytest.raises(security.TokenInvalido):
            security.leer_token(sin_firma)

    @pytest.mark.parametrize("quitar", ["sub", "exp", "iat", "iss"])
    def test_faltan_claims_obligatorios(self, quitar):
        with pytest.raises(security.TokenInvalido):
            security.leer_token(_token(**{quitar: None}))

    def test_emisor_distinto(self):
        with pytest.raises(security.TokenInvalido):
            security.leer_token(_token(iss="otro-sistema"))

    def test_sub_que_no_es_un_numero(self):
        with pytest.raises(security.TokenInvalido):
            security.leer_token(_token(sub="abc"))

    @pytest.mark.parametrize("basura", ["", "abc", "a.b.c", "Bearer xyz"])
    def test_basura(self, basura):
        with pytest.raises(security.TokenInvalido):
            security.leer_token(basura)
