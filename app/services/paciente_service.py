"""Reglas de negocio de los pacientes. No conoce HTTP: los errores del dominio llegan al router.

El esquema (docs/ScriptDb.sql) no liga pacientes con médicos: el directorio de pacientes es
compartido y cualquier médico con sesión puede consultarlo y editarlo."""
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.paciente import Paciente
from app.repositories import paciente_repo
from app.schemas.paciente import PacienteActualizar, PacienteCrear


class PacienteNoEncontrado(Exception):
    """No hay un paciente con ese id."""


class CurpYaRegistrada(Exception):
    """Ya existe otro paciente con esa CURP."""


class PacienteConRegistros(Exception):
    """El paciente tiene citas o consultas y no se puede borrar."""


def crear(db: Session, datos: PacienteCrear) -> Paciente:
    if paciente_repo.obtener_por_curp(db, datos.curp):
        raise CurpYaRegistrada(datos.curp)
    paciente = Paciente(**datos.model_dump())
    try:
        paciente_repo.agregar(db, paciente)
        db.commit()
    except IntegrityError:
        db.rollback()  # dos altas simultáneas con la misma CURP: decide la restricción UNIQUE
        raise CurpYaRegistrada(datos.curp)
    return paciente


def obtener(db: Session, paciente_id: int) -> Paciente:
    paciente = paciente_repo.obtener(db, paciente_id)
    if paciente is None:
        raise PacienteNoEncontrado(paciente_id)
    return paciente


def listar(db: Session, buscar: str | None, limit: int, offset: int) -> tuple[list[Paciente], int]:
    return paciente_repo.listar(db, buscar, limit, offset)


def actualizar(db: Session, paciente_id: int, datos: PacienteActualizar) -> Paciente:
    paciente = obtener(db, paciente_id)
    cambios = datos.model_dump(exclude_unset=True)

    nueva_curp = cambios.get("curp")
    if nueva_curp and nueva_curp != paciente.curp and paciente_repo.obtener_por_curp(db, nueva_curp):
        raise CurpYaRegistrada(nueva_curp)

    for campo, valor in cambios.items():
        setattr(paciente, campo, valor)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise CurpYaRegistrada(nueva_curp)
    return paciente


def eliminar(db: Session, paciente_id: int) -> None:
    """Borra al paciente solo si no tiene citas ni consultas: no se pierde historial por accidente."""
    paciente = obtener(db, paciente_id)
    if paciente_repo.tiene_citas_o_consultas(db, paciente_id):
        raise PacienteConRegistros(paciente_id)
    try:
        paciente_repo.eliminar(db, paciente)
        db.commit()
    except IntegrityError:  # le crearon una cita justo ahora: la FK RESTRICT lo impide
        db.rollback()
        raise PacienteConRegistros(paciente_id)
