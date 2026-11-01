"""Acceso a datos de la tabla medicos. Solo consultas: las reglas de negocio van en los services."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.medico import Medico


def obtener_por_id(db: Session, medico_id: int) -> Medico | None:
    return db.get(Medico, medico_id)


def obtener_por_usuario(db: Session, nombre_de_usuario: str) -> Medico | None:
    return db.scalar(select(Medico).where(Medico.nombre_de_usuario == nombre_de_usuario))


def agregar(db: Session, medico: Medico) -> Medico:
    """Inserta el médico. Puede lanzar IntegrityError si el nombre de usuario ya existe."""
    db.add(medico)
    db.flush()  # asigna el id y dispara las restricciones sin cerrar la transacción
    return medico
