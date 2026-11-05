from pydantic import BaseModel, Field

from app.schemas.comunes import Pagina
from app.schemas.consulta import ConsultaSalida
from app.schemas.paciente import PacienteSalida


class HistorialSalida(BaseModel):
    paciente: PacienteSalida
    consultas: Pagina[ConsultaSalida] = Field(
        description="Solo las consultas que hizo el médico de la sesión, de la más reciente a la más antigua. "
        "Las de otros médicos no aparecen: se abren con su llave en POST /consultas/acceso"
    )
