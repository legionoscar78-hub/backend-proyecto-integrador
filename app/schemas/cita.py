from datetime import date, time
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.schemas.paciente import PacienteResumen


def _sin_segundos(valor: time) -> time:
    """Las citas se agendan por minuto: 10:00:30 y 10:00:00 serían dos horarios 'distintos' para la BD."""
    return valor.replace(second=0, microsecond=0, tzinfo=None)


Hora = Annotated[time, AfterValidator(_sin_segundos)]


class CitaCrear(BaseModel):
    paciente_id: int = Field(gt=0)
    fecha_cita: date
    hora_cita: Hora


class CitaActualizar(BaseModel):
    """Reprogramar la cita o cambiarle el paciente. Solo cambia lo que se envía."""

    paciente_id: int | None = Field(default=None, gt=0)
    fecha_cita: date | None = None
    hora_cita: Hora | None = None

    @model_validator(mode="after")
    def _sin_nulls_y_con_algo_que_cambiar(self):
        for campo in self.model_fields_set:
            if getattr(self, campo) is None:
                raise ValueError(f"{campo} no puede ser null")
        if not self.model_fields_set:
            raise ValueError("No se envió ningún campo para actualizar")
        return self


class CitaSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    medico_id: int
    paciente: PacienteResumen
    fecha_cita: date
    hora_cita: time
