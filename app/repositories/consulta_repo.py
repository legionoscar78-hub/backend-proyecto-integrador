"""Acceso a datos de la tabla consultas. Todas las consultas filtran por médico: una consulta
solo es visible y modificable por el médico que la hizo."""
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.consulta import Consulta


def obtener(db: Session, consulta_id: int, medico_id: int) -> Consulta | None:
    return db.scalar(
        select(Consulta).options(joinedload(Consulta.paciente), joinedload(Consulta.enfermedad))
        .where(Consulta.id == consulta_id, Consulta.medico_id == medico_id)
    )


def obtener_por_llave(db: Session, llave: str) -> Consulta | None:
    """La consulta con esa llave, de cualquier médico (la llave es lo que autoriza el acceso)."""
    return db.scalar(
        select(Consulta).options(joinedload(Consulta.paciente), joinedload(Consulta.enfermedad))
        .where(Consulta.llave == llave)
    )


def listar(
    db: Session, medico_id: int, paciente_id: int | None, enfermedad_id: int | None,
    desde: date | None, hasta: date | None, limit: int, offset: int,
) -> tuple[list[Consulta], int]:
    """Consultas del médico, de la más reciente a la más antigua, y el total que cumple el filtro.
    `desde` y `hasta` son fechas completas (incluyen todo el día)."""
    filtros = [Consulta.medico_id == medico_id]
    if paciente_id is not None:
        filtros.append(Consulta.paciente_id == paciente_id)
    if enfermedad_id is not None:
        filtros.append(Consulta.enfermedad_id == enfermedad_id)
    if desde is not None:
        filtros.append(Consulta.fecha_consulta >= datetime.combine(desde, time.min))
    if hasta is not None:
        filtros.append(Consulta.fecha_consulta < datetime.combine(hasta + timedelta(days=1), time.min))

    total = db.scalar(select(func.count()).select_from(Consulta).where(*filtros))
    items = db.scalars(
        select(Consulta).options(joinedload(Consulta.paciente), joinedload(Consulta.enfermedad))
        .where(*filtros)
        .order_by(Consulta.fecha_consulta.desc(), Consulta.id.desc())
        .limit(limit).offset(offset)
    ).all()
    return list(items), total


def agregar(db: Session, consulta: Consulta) -> Consulta:
    """Inserta la consulta. Puede lanzar IntegrityError (llave repetida, paciente o enfermedad inexistentes)."""
    db.add(consulta)
    db.flush()
    return consulta
