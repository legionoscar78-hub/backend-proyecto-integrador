from pydantic import BaseModel, ConfigDict, Field


class SintomaSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    usado_por_el_modelo: bool = Field(
        default=False, description="True si el modelo de predicción entiende este síntoma"
    )


class EnfermedadSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    descripcion: str | None


class EnfermedadDetalleSalida(EnfermedadSalida):
    sintomas: list[SintomaSalida] = Field(description="Síntomas asociados a la enfermedad en el catálogo")
