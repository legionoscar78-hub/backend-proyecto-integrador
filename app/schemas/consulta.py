from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.paciente import PacienteResumen

# Límites razonables dentro de lo que caben las columnas: peso numeric(5,2) y altura numeric(4,2)
Peso = Annotated[Decimal, Field(gt=0, le=500, max_digits=5, decimal_places=2, description="Kilogramos")]
Altura = Annotated[Decimal, Field(gt=0, le=2.5, max_digits=3, decimal_places=2, description="Metros, por ejemplo 1.72")]
Notas = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]


class ConsultaCrear(BaseModel):
    paciente_id: int = Field(gt=0)
    enfermedad_id: int = Field(gt=0, description="Diagnóstico que confirma el médico (catálogo de enfermedades)")
    peso: Peso | None = None
    altura: Altura | None = None
    notas: Notas | None = None
    # La edad no se envía: se calcula con la fecha de nacimiento del paciente el día de la consulta


class AccesoPorLlave(BaseModel):
    llave: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] = Field(
        description="Llave que el paciente recibió al hacerse la consulta", examples=["K7QM-2XW9-HP4T-R8ZD"]
    )


class ConsultaActualizar(BaseModel):
    """Corregir el diagnóstico o los datos de la consulta. Solo cambia lo que se envía;
    peso, altura y notas se borran enviándolos como null."""

    enfermedad_id: int | None = Field(default=None, gt=0)
    peso: Peso | None = None
    altura: Altura | None = None
    notas: Notas | None = None

    @model_validator(mode="after")
    def _enfermedad_no_puede_ser_null_y_algo_que_cambiar(self):
        if "enfermedad_id" in self.model_fields_set and self.enfermedad_id is None:
            raise ValueError("enfermedad_id no puede ser null")
        if not self.model_fields_set:
            raise ValueError("No se envió ningún campo para actualizar")
        return self


class EnfermedadResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str


class ConsultaSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    llave: str = Field(description="Llave de acceso: el paciente se la da a otro médico para que pueda ver esta consulta")
    medico_id: int
    paciente: PacienteResumen
    enfermedad: EnfermedadResumen
    fecha_consulta: datetime
    edad: int
    peso: float | None
    altura: float | None
    notas: str | None
