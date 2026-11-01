"""Acceso a datos de la tabla citas. Todas las consultas filtran por médico: una cita solo es
visible y modificable por el médico al que pertenece."""
from datetime import date, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.cita import Cita


def obtener(db: Session, cita_id: int, medico_id: int) -> Cita | None:
    return db.scalar(
        select(Cita).options(joinedload(Cita.paciente))
        .where(Cita.id == cita_id, Cita.medico_id == medico_id)
    )


def horario_ocupado(db: Session, medico_id: int, fecha: date, hora: time, excluir_cita_id: int | None = None) -> bool:
    consulta = select(Cita.id).where(
        Cita.medico_id == medico_id, Cita.fecha_cita == fecha, Cita.hora_cita == hora
    )
    if excluir_cita_id is not None:
        consulta = consulta.where(Cita.id != excluir_cita_id)
    return db.scalar(consulta.limit(1)) is not None


def listar(
    db: Session, medico_id: int, desde: date | None, hasta: date | None, paciente_id: int | None,
    limit: int, offset: int,
) -> tuple[list[Cita], int]:
    """Citas del médico, de la más próxima a la más lejana, y el total que cumple el filtro."""
    filtros = [Cita.medico_id == medico_id]
    if desde is not None:
        filtros.append(Cita.fecha_cita >= desde)
    if hasta is not None:
        filtros.append(Cita.fecha_cita <= hasta)
    if paciente_id is not None:
        filtros.append(Cita.paciente_id == paciente_id)

    total = db.scalar(select(func.count()).select_from(Cita).where(*filtros))
    items = db.scalars(
        select(Cita).options(joinedload(Cita.paciente)).where(*filtros)
        .order_by(Cita.fecha_cita, Cita.hora_cita, Cita.id)
        .limit(limit).offset(offset)
    ).all()
    return list(items), total


def agregar(db: Session, cita: Cita) -> Cita:
    """Inserta la cita. Puede lanzar IntegrityError (horario repetido o paciente inexistente)."""
    db.add(cita)
    db.flush()
    return cita


def eliminar(db: Session, cita: Cita) -> None:
    db.delete(cita)
    db.flush()
