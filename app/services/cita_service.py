"""Reglas de negocio de las citas. No conoce HTTP: los errores del dominio llegan al router.

Cada cita pertenece al médico que la agenda; los demás médicos no la ven."""
from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.cita import Cita
from app.models.medico import Medico
from app.repositories import cita_repo, paciente_repo
from app.schemas.cita import CitaActualizar, CitaCrear
from app.services.paciente_service import PacienteNoEncontrado


class CitaNoEncontrada(Exception):
    """No hay una cita con ese id entre las del médico."""


class HorarioOcupado(Exception):
    """El médico ya tiene otra cita a esa fecha y hora."""


class FechaEnElPasado(Exception):
    """No se puede agendar una cita en un día anterior a hoy."""


def _exigir_fecha_vigente(fecha: date) -> None:
    if fecha < date.today():
        raise FechaEnElPasado(fecha)


def _exigir_paciente(db: Session, paciente_id: int) -> None:
    if paciente_repo.obtener(db, paciente_id) is None:
        raise PacienteNoEncontrado(paciente_id)


def agendar(db: Session, medico: Medico, datos: CitaCrear) -> Cita:
    _exigir_fecha_vigente(datos.fecha_cita)
    _exigir_paciente(db, datos.paciente_id)
    if cita_repo.horario_ocupado(db, medico.id, datos.fecha_cita, datos.hora_cita):
        raise HorarioOcupado()

    cita = Cita(medico_id=medico.id, **datos.model_dump())
    try:
        cita_repo.agregar(db, cita)
        db.commit()
    except IntegrityError:
        db.rollback()
        _exigir_paciente(db, datos.paciente_id)  # ¿lo borraron justo ahora?
        raise HorarioOcupado()  # si no, otra cita simultánea tomó el horario: decide la restricción UNIQUE
    return cita_repo.obtener(db, cita.id, medico.id)


def obtener(db: Session, medico: Medico, cita_id: int) -> Cita:
    cita = cita_repo.obtener(db, cita_id, medico.id)
    if cita is None:
        raise CitaNoEncontrada(cita_id)
    return cita


def listar(
    db: Session, medico: Medico, desde: date | None, hasta: date | None, paciente_id: int | None,
    limit: int, offset: int,
) -> tuple[list[Cita], int]:
    return cita_repo.listar(db, medico.id, desde, hasta, paciente_id, limit, offset)


def actualizar(db: Session, medico: Medico, cita_id: int, datos: CitaActualizar) -> Cita:
    cita = obtener(db, medico, cita_id)
    cambios = datos.model_dump(exclude_unset=True)
    fecha = cambios.get("fecha_cita", cita.fecha_cita)
    hora = cambios.get("hora_cita", cita.hora_cita)

    if "fecha_cita" in cambios:
        _exigir_fecha_vigente(fecha)
    if "paciente_id" in cambios:
        _exigir_paciente(db, cambios["paciente_id"])
    if ("fecha_cita" in cambios or "hora_cita" in cambios) and cita_repo.horario_ocupado(
        db, medico.id, fecha, hora, excluir_cita_id=cita.id
    ):
        raise HorarioOcupado()

    for campo, valor in cambios.items():
        setattr(cita, campo, valor)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if "paciente_id" in cambios:
            _exigir_paciente(db, cambios["paciente_id"])
        raise HorarioOcupado()
    return cita_repo.obtener(db, cita_id, medico.id)


def cancelar(db: Session, medico: Medico, cita_id: int) -> None:
    cita = obtener(db, medico, cita_id)
    cita_repo.eliminar(db, cita)
    db.commit()
