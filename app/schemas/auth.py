import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator

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


Nombre = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Apellidos = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Ciudad = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Efirma = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000)]
PasswordNueva = Annotated[str, Field(min_length=8, max_length=128)]


class RegistroEntrada(BaseModel):
    nombre: Nombre
    apellidos: Apellidos
    ciudad: Ciudad
    efirma: Efirma
    nombre_de_usuario: NombreDeUsuario
    password: PasswordNueva


class MedicoActualizar(BaseModel):
    """Actualización parcial del perfil: solo cambia lo que se envía. Ningún campo admite null
    (todos son obligatorios en la BD). La contraseña se cambia aparte, en PUT /auth/me/password."""

    nombre: Nombre | None = None
    apellidos: Apellidos | None = None
    ciudad: Ciudad | None = None
    efirma: Efirma | None = None
    nombre_de_usuario: NombreDeUsuario | None = None

    @model_validator(mode="after")
    def _sin_nulos_ni_vacio(self):
        for campo in self.model_fields_set:
            if getattr(self, campo) is None:
                raise ValueError(f"{campo} es obligatorio y no puede ser null")
        if not self.model_fields_set:
            raise ValueError("No se envió ningún campo para actualizar")
        return self


class CambioPassword(BaseModel):
    password_actual: str = Field(min_length=1, max_length=128)
    password_nueva: PasswordNueva

    @model_validator(mode="after")
    def _debe_ser_distinta(self):
        if self.password_nueva == self.password_actual:
            raise ValueError("La contraseña nueva debe ser distinta de la actual")
        return self


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
