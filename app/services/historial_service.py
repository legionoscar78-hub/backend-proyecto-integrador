"""Historial de un paciente visto por un médico.

Cualquier médico puede ver a cualquier paciente (el directorio es compartido), pero el historial solo
trae las consultas que ese médico hizo. Las de otros médicos no se listan ni se cuentan: se abren una
por una con su llave (consulta_service.obtener_por_llave). Así no se revela ni que existen."""
from datetime import date

from sqlalchemy.orm import Session

from app.models.consulta import Consulta
from app.models.medico import Medico
from app.models.paciente import Paciente
from app.repositories import consulta_repo
from app.services import paciente_service


def obtener(
    db: Session, medico: Medico, paciente_id: int, desde: date | None, hasta: date | None, limit: int, offset: int,
) -> tuple[Paciente, list[Consulta], int]:
    """(paciente, consultas del médico a ese paciente, total). Lanza PacienteNoEncontrado."""
    paciente = paciente_service.obtener(db, paciente_id)
    consultas, total = consulta_repo.listar(db, medico.id, paciente_id, None, desde, hasta, limit, offset)
    return paciente, consultas, total
