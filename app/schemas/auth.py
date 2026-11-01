import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

PATRON_USUARIO = re.compile(r"^[a-z0-9._-]+$")


def _usuario_valido(valor: str) -> str:
    """Se guarda siempre en minúsculas: 'Juan' y 'juan' serían dos cuentas casi idénticas."""
    valor = valor.lower()
    if not PATRON_USUARIO.fullmatch(valor):
        raise ValueError("Solo se permiten letras, números, punto, guion y guion bajo")
    return valor


NombreDeUsuario = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=50),
    AfterValidator(_usuario_valido),
]


class RegistroEntrada(BaseModel):
    nombre: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    apellidos: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
    ciudad: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    efirma: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000)]
    nombre_de_usuario: NombreDeUsuario
    password: str = Field(min_length=8, max_length=128)


class LoginEntrada(BaseModel):
    nombre_de_usuario: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    password: str = Field(min_length=1, max_length=128)


class TokenSalida(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Segundos que dura la sesión")


class MedicoSalida(BaseModel):
    """Perfil público del médico. Nunca incluye la contraseña ni la firma electrónica."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    apellidos: str
    ciudad: str
    nombre_de_usuario: str
