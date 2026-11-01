from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MAX_SINTOMAS = 40
AVISO = (
    "Resultado orientativo generado por un modelo estadístico. No es un diagnóstico y no "
    "sustituye el criterio del médico."
)

NombreSintoma = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]


class PrediccionEntrada(BaseModel):
    sintomas: list[NombreSintoma] = Field(
        min_length=1,
        max_length=MAX_SINTOMAS,
        description="Nombres de los síntomas como están en el catálogo (sintomas.nombresintoma, en español). También se aceptan en inglés.",
        examples=[["dolor de cabeza", "náusea"]],
    )
    top_n: int = Field(default=5, ge=1, le=10, description="Cuántas enfermedades devolver.")


class SugerenciaSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    posicion: int = Field(description="1 = la más probable")
    enfermedad: str = Field(description="Nombre en inglés (clave del catálogo)")
    enfermedad_es: str
    cie10_codigo: str
    probabilidad: float = Field(ge=0, le=1)


class PrediccionSalida(BaseModel):
    modelo_version: str
    sugerencias: list[SugerenciaSalida]
    aviso: str = AVISO


class ErrorSintomasDesconocidos(BaseModel):
    mensaje: str
    sintomas: list[str]


class EstadoModelo(BaseModel):
    disponible: bool
    error: str | None = None
    version: str | None = None
    fecha_entrenamiento: str | None = None
    n_sintomas: int | None = None
    n_enfermedades: int | None = None
    metricas_test: dict | None = None
