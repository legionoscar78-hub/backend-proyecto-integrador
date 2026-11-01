# Importar todos los modelos aquí hace que queden registrados en Base.metadata,
# que es lo que Alembic necesita para detectar las tablas.
from app.models.cita import Cita
from app.models.consulta import Consulta
from app.models.enfermedad import Enfermedad
from app.models.enfermedad_detalle import EnfermedadDetalle
from app.models.medico import Medico
from app.models.paciente import Paciente
from app.models.sintoma import Sintoma

__all__ = [
    "Cita",
    "Consulta",
    "Enfermedad",
    "EnfermedadDetalle",
    "Medico",
    "Paciente",
    "Sintoma",
]
