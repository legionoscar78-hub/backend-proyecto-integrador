import re
from datetime import date
from typing import Annotated, Literal

from pydantic import (
    AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, computed_field, model_validator,
)

from app.core.fechas import calcular_edad

Sexo = Literal["H", "M"]
TipoDeSangre = Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]

# Estructura de la CURP: 4 letras, fecha AAMMDD, sexo, 2 letras de entidad, 3 consonantes internas,
# homoclave y dígito verificador. Solo se valida el formato, no que la persona exista.
PATRON_CURP = re.compile(r"^[A-Z]{4}\d{6}[HM][A-Z]{2}[B-DF-HJ-NP-TV-Z]{3}[A-Z0-9]\d$")
FECHA_MINIMA = date(1900, 1, 1)
MAX_TELEFONO = 15  # numerotelefonico es varchar(15)


def _curp(valor: str) -> str:
    valor = valor.upper()
    if not PATRON_CURP.fullmatch(valor):
        raise ValueError("La CURP no tiene un formato válido (18 caracteres, por ejemplo HEGG560427MVZRRL04)")
    return valor


def _telefono(valor: str) -> str:
    """Quita espacios, guiones y paréntesis; deja dígitos con un + opcional al inicio."""
    limpio = re.sub(r"[\s\-().]", "", valor)
    if not re.fullmatch(r"\+?\d{7,}", limpio) or len(limpio) > MAX_TELEFONO:
        raise ValueError(f"El teléfono debe tener entre 7 y {MAX_TELEFONO} caracteres: dígitos y un + opcional al inicio")
    return limpio


def _fecha_nacimiento(valor: date) -> date:
    if valor > date.today():
        raise ValueError("La fecha de nacimiento no puede ser futura")
    if valor < FECHA_MINIMA:
        raise ValueError("La fecha de nacimiento no puede ser anterior a 1900")
    return valor


Curp = Annotated[str, StringConstraints(strip_whitespace=True), AfterValidator(_curp)]
Telefono = Annotated[str, StringConstraints(strip_whitespace=True), AfterValidator(_telefono)]
FechaNacimiento = Annotated[date, AfterValidator(_fecha_nacimiento)]
Nombre = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Apellidos = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Notas = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]


class PacienteCrear(BaseModel):
    nombre: Nombre
    apellidos: Apellidos
    curp: Curp
    fecha_nacimiento: FechaNacimiento
    numero_telefonico: Telefono | None = None
    sexo: Sexo
    tipo_de_sangre: TipoDeSangre | None = None
    notas: Notas | None = None


class PacienteActualizar(BaseModel):
    """Actualización parcial: solo cambia lo que se envía. Los campos opcionales de la BD
    (teléfono, tipo de sangre, notas) se borran enviándolos como null."""

    nombre: Nombre | None = None
    apellidos: Apellidos | None = None
    curp: Curp | None = None
    fecha_nacimiento: FechaNacimiento | None = None
    numero_telefonico: Telefono | None = None
    sexo: Sexo | None = None
    tipo_de_sangre: TipoDeSangre | None = None
    notas: Notas | None = None

    @model_validator(mode="after")
    def _obligatorios_no_pueden_ser_null(self):
        for campo in ("nombre", "apellidos", "curp", "fecha_nacimiento", "sexo"):
            if campo in self.model_fields_set and getattr(self, campo) is None:
                raise ValueError(f"{campo} es obligatorio y no puede ser null")
        if not self.model_fields_set:
            raise ValueError("No se envió ningún campo para actualizar")
        return self


class PacienteSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    apellidos: str
    curp: str
    fecha_nacimiento: date
    numero_telefonico: str | None
    sexo: str
    tipo_de_sangre: str | None
    notas: str | None

    @computed_field
    @property
    def edad(self) -> int:
        return calcular_edad(self.fecha_nacimiento)


class PacienteResumen(BaseModel):
    """Lo mínimo para identificar al paciente dentro de otras respuestas (por ejemplo, una cita)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    apellidos: str
