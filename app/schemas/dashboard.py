from pydantic import BaseModel, Field


class EnfermedadCasos(BaseModel):
    enfermedad_id: int
    nombre: str
    casos: int = Field(ge=0, description="Número de consultas con ese diagnóstico")


class TopDelMes(BaseModel):
    mes: int = Field(ge=1, le=12)
    enfermedades: list[EnfermedadCasos] = Field(description="Las 5 más diagnosticadas del mes, de más a menos (vacío si no hubo consultas)")


class TotalAnualRegion(BaseModel):
    region: str = Field(description="Ciudad del médico que atendió")
    total: int = Field(ge=0, description="Casos del año de las 5 enfermedades, sumados")
    enfermedades: list[EnfermedadCasos] = Field(description="Casos del año por cada una de las 5 (con 0 si no hubo), en el orden de `top_anual`")


class CasosMes(BaseModel):
    mes: int = Field(ge=1, le=12)
    casos: int = Field(ge=0)


class CasosMensualesRegion(BaseModel):
    region: str
    meses: list[CasosMes] = Field(description="Siempre los 12 meses, con 0 donde no hubo casos")


class DashboardSalida(BaseModel):
    anio: int
    total_consultas: int = Field(ge=0, description="Consultas del año en todas las regiones (de cualquier enfermedad)")
    top_anual: list[EnfermedadCasos] = Field(description="Las 5 enfermedades más diagnosticadas del año: son 'esas 5' de las dos listas de abajo")
    top_por_mes: list[TopDelMes] = Field(description="Los 12 meses, cada uno con sus 5 enfermedades más diagnosticadas")
    total_anual_por_region: list[TotalAnualRegion] = Field(description="De mayor a menor total")
    casos_mensuales_por_region: list[CasosMensualesRegion] = Field(description="Casos de las 5 enfermedades de `top_anual`, mes a mes, por región")
