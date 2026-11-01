"""Acceso a datos de la tabla pacientes. Solo consultas: las reglas de negocio van en los services."""
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.models.cita import Cita
from app.models.consulta import Consulta
from app.models.paciente import Paciente
from app.repositories.busqueda import filtro_por_palabras


def obtener(db: Session, paciente_id: int) -> Paciente | None:
    return db.get(Paciente, paciente_id)


def obtener_por_curp(db: Session, curp: str) -> Paciente | None:
    return db.scalar(select(Paciente).where(Paciente.curp == curp))


def listar(db: Session, buscar: str | None, limit: int, offset: int) -> tuple[list[Paciente], int]:
    """Pacientes ordenados por apellidos y nombre, y el total que cumple el filtro.

    `buscar` se separa en palabras y cada una debe aparecer en el nombre, los apellidos o la CURP
    (sin distinguir mayúsculas; los acentos sí cuentan).
    """
    filtros = filtro_por_palabras(buscar, [Paciente.nombre, Paciente.apellidos, Paciente.curp])
    total = db.scalar(select(func.count()).select_from(Paciente).where(*filtros))
    items = db.scalars(
        select(Paciente).where(*filtros)
        .order_by(Paciente.apellidos, Paciente.nombre, Paciente.id)
        .limit(limit).offset(offset)
    ).all()
    return list(items), total


def tiene_citas_o_consultas(db: Session, paciente_id: int) -> bool:
    return bool(db.scalar(select(
        exists().where(Cita.paciente_id == paciente_id) | exists().where(Consulta.paciente_id == paciente_id)
    )))


def agregar(db: Session, paciente: Paciente) -> Paciente:
    """Inserta el paciente. Puede lanzar IntegrityError si la CURP ya existe."""
    db.add(paciente)
    db.flush()
    return paciente


def eliminar(db: Session, paciente: Paciente) -> None:
    db.delete(paciente)
    db.flush()
