"""Consulta del catálogo de enfermedades y síntomas (lo que el médico elige en pantalla)."""
from sqlalchemy.orm import Session

from app.ml import predictor
from app.ml.predictor import ModeloNoDisponible
from app.models.enfermedad import Enfermedad
from app.models.sintoma import Sintoma
from app.repositories import enfermedad_repo, sintoma_repo
from app.services.consulta_service import EnfermedadNoEncontrada


def _nombres_del_modelo(obligatorio: bool = False) -> set[str] | None:
    """Nombres (como están en la BD) de los síntomas que entiende el modelo; None si no está cargado.
    Con obligatorio=True lanza ModeloNoDisponible en vez de devolver None."""
    try:
        return set(predictor.obtener().nombres_para_mostrar)
    except ModeloNoDisponible:
        if obligatorio:
            raise
        return None


def listar_enfermedades(db: Session, buscar: str | None, limit: int, offset: int) -> tuple[list[Enfermedad], int]:
    return enfermedad_repo.listar(db, buscar, limit, offset)


def obtener_enfermedad(db: Session, enfermedad_id: int) -> tuple[Enfermedad, set[str] | None]:
    """La enfermedad con sus síntomas, y los nombres que entiende el modelo (None si no hay modelo)."""
    enfermedad = enfermedad_repo.obtener_con_sintomas(db, enfermedad_id)
    if enfermedad is None:
        raise EnfermedadNoEncontrada(enfermedad_id)
    enfermedad.sintomas.sort(key=lambda s: s.nombre)
    return enfermedad, _nombres_del_modelo()


def listar_sintomas(
    db: Session, buscar: str | None, solo_modelo: bool, limit: int, offset: int
) -> tuple[list[Sintoma], int, set[str] | None]:
    """Con solo_modelo=True devuelve únicamente los síntomas que el modelo entiende (ModeloNoDisponible si no hay modelo)."""
    del_modelo = _nombres_del_modelo(obligatorio=solo_modelo)
    items, total = sintoma_repo.listar(db, buscar, del_modelo if solo_modelo else None, limit, offset)
    return items, total, del_modelo
