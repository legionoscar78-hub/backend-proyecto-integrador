# Importar todos los modelos aquí hace que queden registrados en Base.metadata,
# que es lo que Alembic necesita para detectar las tablas.
from app.models.consulta import Consulta, consulta_sintoma
from app.models.enfermedad import Enfermedad
from app.models.enfermedad_detalle import EnfermedadDetalle
from app.models.medico import Medico
from app.models.paciente import Paciente
from app.models.prediccion import Prediccion, PrediccionDetalle
from app.models.sintoma import Sintoma

__all__ = [
    "Consulta",
    "consulta_sintoma",
    "Enfermedad",
    "EnfermedadDetalle",
    "Medico",
    "Paciente",
    "Prediccion",
    "PrediccionDetalle",
    "Sintoma",
]
