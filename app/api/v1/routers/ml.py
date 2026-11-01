from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_medico
from app.models.medico import Medico
from app.ml.features import SintomaDesconocido
from app.ml.predictor import ModeloNoDisponible
from app.schemas.prediccion import (
    EstadoModelo, PrediccionEntrada, PrediccionSalida, SugerenciaSalida,
)
from app.services import prediccion_service

router = APIRouter()  # /predecir exige sesión de médico; /estado es público


@router.post(
    "/predecir",
    response_model=PrediccionSalida,
    responses={
        401: {"description": "Falta el token de sesión o no es válido"},
        422: {"description": "Algún síntoma no está en el vocabulario del modelo"},
        503: {"description": "El modelo no está disponible"},
    },
)
def predecir(entrada: PrediccionEntrada, _: Medico = Depends(get_current_medico)) -> PrediccionSalida:
    """Enfermedades más probables para los síntomas dados, con su probabilidad estimada."""
    try:
        resultado = prediccion_service.predecir(entrada.sintomas, entrada.top_n)
    except ModeloNoDisponible as error:
        raise HTTPException(status_code=503, detail=str(error))
    except SintomaDesconocido as error:
        raise HTTPException(
            status_code=422,
            detail={"mensaje": "Hay síntomas que el modelo no conoce", "sintomas": error.sintomas},
        )
    return PrediccionSalida(
        modelo_version=resultado.modelo_version,
        sugerencias=[SugerenciaSalida.model_validate(s) for s in resultado.sugerencias],
    )


@router.get("/estado", response_model=EstadoModelo)
def estado() -> dict:
    """Si el modelo está cargado y cuál es. Responde 200 aunque no esté: el motivo va en `error`."""
    return prediccion_service.estado_modelo()
