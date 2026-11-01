"""Acceso a datos del catálogo de enfermedades."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.enfermedad import Enfermedad
from app.repositories.busqueda import filtro_por_palabras


def obtener(db: Session, enfermedad_id: int) -> Enfermedad | None:
    return db.get(Enfermedad, enfermedad_id)


def obtener_con_sintomas(db: Session, enfermedad_id: int) -> Enfermedad | None:
    return db.scalar(
        select(Enfermedad).options(selectinload(Enfermedad.sintomas)).where(Enfermedad.id == enfermedad_id)
    )


def ids_por_nombre(db: Session, nombres: list[str]) -> dict[str, int]:
    """{nombre: id} de las enfermedades que existen con esos nombres exactos."""
    if not nombres:
        return {}
    filas = db.execute(select(Enfermedad.nombre, Enfermedad.id).where(Enfermedad.nombre.in_(nombres)))
    return {nombre: id_ for nombre, id_ in filas}


def listar(db: Session, buscar: str | None, limit: int, offset: int) -> tuple[list[Enfermedad], int]:
    filtros = filtro_por_palabras(buscar, [Enfermedad.nombre])
    total = db.scalar(select(func.count()).select_from(Enfermedad).where(*filtros))
    items = db.scalars(
        select(Enfermedad).where(*filtros).order_by(Enfermedad.nombre, Enfermedad.id).limit(limit).offset(offset)
    ).all()
    return list(items), total
