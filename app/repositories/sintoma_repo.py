"""Acceso a datos del catálogo de síntomas."""
from collections.abc import Collection

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.sintoma import Sintoma
from app.repositories.busqueda import filtro_por_palabras


def listar(
    db: Session, buscar: str | None, solo_nombres: Collection[str] | None, limit: int, offset: int
) -> tuple[list[Sintoma], int]:
    """Síntomas ordenados por nombre. Con `solo_nombres` se devuelven solo los que tengan uno de esos nombres."""
    filtros = filtro_por_palabras(buscar, [Sintoma.nombre])
    if solo_nombres is not None:
        filtros.append(Sintoma.nombre.in_(list(solo_nombres)))
    total = db.scalar(select(func.count()).select_from(Sintoma).where(*filtros))
    items = db.scalars(
        select(Sintoma).where(*filtros).order_by(Sintoma.nombre, Sintoma.id).limit(limit).offset(offset)
    ).all()
    return list(items), total
