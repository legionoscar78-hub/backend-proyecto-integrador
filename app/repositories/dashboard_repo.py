"""Consultas de agregación para el dashboard. Devuelven conteos, nunca datos de pacientes."""
from datetime import datetime

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.models.consulta import Consulta
from app.models.enfermedad import Enfermedad
from app.models.medico import Medico


def _rango(anio: int):
    return Consulta.fecha_consulta >= datetime(anio, 1, 1), Consulta.fecha_consulta < datetime(anio + 1, 1, 1)


def casos_por_mes_y_enfermedad(db: Session, anio: int) -> list[tuple[int, int, str, int]]:
    """(mes, enfermedad_id, nombre, casos) de todas las consultas del año."""
    mes = extract("month", Consulta.fecha_consulta)
    filas = db.execute(
        select(mes, Enfermedad.id, Enfermedad.nombre, func.count(Consulta.id))
        .join(Enfermedad, Enfermedad.id == Consulta.enfermedad_id)
        .where(*_rango(anio))
        .group_by(mes, Enfermedad.id, Enfermedad.nombre)
    ).all()
    return [(int(m), eid, nombre, int(n)) for m, eid, nombre, n in filas]


def casos_por_region_mes_enfermedad(
    db: Session, anio: int, enfermedad_ids: list[int]
) -> list[tuple[str, int, int, int]]:
    """(ciudad del médico, mes, enfermedad_id, casos) del año, solo para las enfermedades indicadas.
    La ciudad viene tal como la escribió el médico (sin espacios en los extremos)."""
    if not enfermedad_ids:
        return []
    mes = extract("month", Consulta.fecha_consulta)
    ciudad = func.trim(Medico.ciudad)
    filas = db.execute(
        select(ciudad, mes, Consulta.enfermedad_id, func.count(Consulta.id))
        .join(Medico, Medico.id == Consulta.medico_id)
        .where(*_rango(anio), Consulta.enfermedad_id.in_(enfermedad_ids))
        .group_by(ciudad, mes, Consulta.enfermedad_id)
    ).all()
    return [(c, int(m), eid, int(n)) for c, m, eid, n in filas]
