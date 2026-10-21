"""Lógica de negocio de la predicción. No conoce HTTP: los errores del dominio
(ModeloNoDisponible, SintomaDesconocido) llegan tal cual al router, que los traduce."""
from dataclasses import dataclass

from app.ml import predictor
from app.ml.predictor import Sugerencia


@dataclass(frozen=True)
class Prediccion:
    modelo_version: str
    sugerencias: list[Sugerencia]


def predecir(sintomas: list[str], top_n: int = predictor.TOP_N_POR_DEFECTO) -> Prediccion:
    """Sugiere las top_n enfermedades más probables para los síntomas dados.

    Quita repeticiones conservando el orden (el modelo no distingue si un síntoma llega dos
    veces) antes de llamar al predictor. Si top_n supera el número de enfermedades del modelo,
    devuelve todas.
    """
    unicos = list(dict.fromkeys(sintomas))
    modelo = predictor.obtener()
    return Prediccion(modelo_version=modelo.version, sugerencias=modelo.predecir(unicos, min(top_n, modelo.n_clases)))


def estado_modelo() -> dict:
    return predictor.estado()
