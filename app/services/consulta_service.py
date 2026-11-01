"""Reglas de negocio de las consultas. No conoce HTTP: los errores del dominio llegan al router.

Una consulta guarda el diagnóstico que el médico confirmó (no lo que sugirió el modelo). Es del
médico que la hizo: los demás no la ven, salvo que el paciente les dé la llave de la consulta, que
permite verla (solo lectura) aunque la haya hecho otro médico. No se borra: es parte del expediente."""
import re
import secrets
from datetime import date, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.fechas import calcular_edad
from app.models.consulta import Consulta
from app.models.medico import Medico
from app.repositories import consulta_repo, enfermedad_repo, paciente_repo
from app.schemas.consulta import ConsultaActualizar, ConsultaCrear
from app.services.paciente_service import PacienteNoEncontrado

INTENTOS_DE_LLAVE = 3
# Alfabeto de 31 caracteres sin los que se confunden al dictarlos o copiarlos (0/O, 1/I/L).
# 16 caracteres = unos 79 bits al azar: no se puede adivinar probando.
ALFABETO_LLAVE = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LARGO_LLAVE = 16


class ConsultaNoEncontrada(Exception):
    """No hay una consulta con ese id entre las del médico."""


class EnfermedadNoEncontrada(Exception):
    """La enfermedad del diagnóstico no existe en el catálogo."""


class LlaveInvalida(Exception):
    """La llave no corresponde a ninguna consulta."""


class NoSePudoGenerarLlave(Exception):
    """Se agotaron los intentos de generar una llave única (no debería pasar)."""


def nueva_llave() -> str:
    """Llave de acceso al azar, en grupos de 4 para dictarla: XXXX-XXXX-XXXX-XXXX."""
    caracteres = "".join(secrets.choice(ALFABETO_LLAVE) for _ in range(LARGO_LLAVE))
    return "-".join(caracteres[i:i + 4] for i in range(0, LARGO_LLAVE, 4))


def normalizar_llave(texto: str) -> str:
    """Acepta la llave con minúsculas, espacios o sin guiones y la devuelve en el formato guardado."""
    limpia = re.sub(r"[^A-Za-z0-9]", "", texto).upper()
    if len(limpia) != LARGO_LLAVE:
        return limpia  # no puede coincidir con ninguna; se busca tal cual y no aparece
    return "-".join(limpia[i:i + 4] for i in range(0, LARGO_LLAVE, 4))


def _exigir_enfermedad(db: Session, enfermedad_id: int) -> None:
    if enfermedad_repo.obtener(db, enfermedad_id) is None:
        raise EnfermedadNoEncontrada(enfermedad_id)


def crear(db: Session, medico: Medico, datos: ConsultaCrear) -> Consulta:
    paciente = paciente_repo.obtener(db, datos.paciente_id)
    if paciente is None:
        raise PacienteNoEncontrado(datos.paciente_id)
    _exigir_enfermedad(db, datos.enfermedad_id)

    ahora = datetime.now()
    edad = calcular_edad(paciente.fecha_nacimiento, ahora.date())
    for _ in range(INTENTOS_DE_LLAVE):
        consulta = Consulta(
            medico_id=medico.id, paciente_id=datos.paciente_id, enfermedad_id=datos.enfermedad_id,
            edad=edad, peso=datos.peso, altura=datos.altura, notas=datos.notas, llave=nueva_llave(),
        )
        try:
            consulta_repo.agregar(db, consulta)
            db.commit()
        except IntegrityError:
            db.rollback()
            # ¿borraron al paciente o la enfermedad justo ahora? Si no, la llave chocó: se reintenta
            if paciente_repo.obtener(db, datos.paciente_id) is None:
                raise PacienteNoEncontrado(datos.paciente_id)
            _exigir_enfermedad(db, datos.enfermedad_id)
            continue
        return consulta_repo.obtener(db, consulta.id, medico.id)
    raise NoSePudoGenerarLlave()


def obtener(db: Session, medico: Medico, consulta_id: int) -> Consulta:
    consulta = consulta_repo.obtener(db, consulta_id, medico.id)
    if consulta is None:
        raise ConsultaNoEncontrada(consulta_id)
    return consulta


def obtener_por_llave(db: Session, llave: str) -> Consulta:
    """La consulta que abre esa llave, sea de quien sea. Solo para leer: modificarla sigue siendo del médico que la hizo."""
    consulta = consulta_repo.obtener_por_llave(db, normalizar_llave(llave))
    if consulta is None:
        raise LlaveInvalida()
    return consulta


def listar(
    db: Session, medico: Medico, paciente_id: int | None, enfermedad_id: int | None,
    desde: date | None, hasta: date | None, limit: int, offset: int,
) -> tuple[list[Consulta], int]:
    return consulta_repo.listar(db, medico.id, paciente_id, enfermedad_id, desde, hasta, limit, offset)


def actualizar(db: Session, medico: Medico, consulta_id: int, datos: ConsultaActualizar) -> Consulta:
    consulta = obtener(db, medico, consulta_id)
    cambios = datos.model_dump(exclude_unset=True)
    if "enfermedad_id" in cambios:
        _exigir_enfermedad(db, cambios["enfermedad_id"])

    for campo, valor in cambios.items():
        setattr(consulta, campo, valor)
    try:
        db.commit()
    except IntegrityError:  # la enfermedad se borró justo ahora
        db.rollback()
        raise EnfermedadNoEncontrada(cambios.get("enfermedad_id"))
    return consulta_repo.obtener(db, consulta_id, medico.id)
