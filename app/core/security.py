"""Contraseñas (argon2) y tokens de sesión (JWT firmado con HS256)."""
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import settings

ALGORITMO = "HS256"
EMISOR = "mediapoyo-api"

_hasher = PasswordHasher()
# Hash de relleno: al iniciar sesión con un usuario que no existe se verifica contra este, para que
# la respuesta tarde igual que con un usuario real y no se pueda averiguar qué usuarios existen.
_HASH_FICTICIO = _hasher.hash("contrasena-que-nadie-usa")


class TokenInvalido(Exception):
    """El token no existe, está mal formado, expiró o no está firmado con nuestra clave."""


def hashear_password(password: str) -> str:
    return _hasher.hash(password)


def verificar_password(password: str, hash_guardado: str | None) -> bool:
    """True si la contraseña corresponde al hash. Con hash None (usuario inexistente) siempre False,
    pero hace el mismo trabajo que una verificación real."""
    try:
        return _hasher.verify(hash_guardado or _HASH_FICTICIO, password) and hash_guardado is not None
    except (VerificationError, InvalidHashError):
        return False


def necesita_rehash(hash_guardado: str) -> bool:
    """True si el hash se creó con parámetros más débiles que los actuales de argon2."""
    return _hasher.check_needs_rehash(hash_guardado)


def crear_token(medico_id: int, ahora: datetime | None = None) -> tuple[str, int]:
    """Token de sesión del médico. Devuelve (token, segundos_de_vigencia)."""
    ahora = ahora or datetime.now(timezone.utc)
    vigencia = timedelta(minutes=settings.access_token_minutes)
    claims = {"sub": str(medico_id), "iss": EMISOR, "iat": ahora, "exp": ahora + vigencia}
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITMO), int(vigencia.total_seconds())


def leer_token(token: str) -> int:
    """Id del médico dueño del token. Lanza TokenInvalido si no es válido."""
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[ALGORITMO],  # fijo: nunca se acepta el algoritmo que declare el token
            issuer=EMISOR,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
        return int(claims["sub"])
    except (jwt.PyJWTError, ValueError) as error:
        raise TokenInvalido(str(error)) from error
