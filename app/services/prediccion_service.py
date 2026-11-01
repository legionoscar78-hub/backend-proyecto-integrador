"""Lógica de negocio de la predicción. No conoce HTTP: los errores del dominio
(ModeloNoDisponible, SintomaDesconocido) llegan tal cual al router, que los traduce."""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.ml import predictor
from app.ml.predictor import Sugerencia
from app.repositories import enfermedad_repo


@dataclass(frozen=True)
class Prediccion:
    modelo_version: str
    sugerencias: list[Sugerencia]
    enfermedad_ids: dict[str, int] = field(default_factory=dict)  # nombre en español -> enfermedades.enfermedadid


def predecir(db: Session, sintomas: list[str], top_n: int = predictor.TOP_N_POR_DEFECTO) -> Prediccion:
    """Sugiere las top_n enfermedades más probables para los síntomas dados.

    Quita repeticiones conservando el orden (el modelo no distingue si un síntoma llega dos
    veces) antes de llamar al predictor. Si top_n supera el número de enfermedades del modelo,
    devuelve todas.
    """
    unicos = list(dict.fromkeys(sintomas))
    modelo = predictor.obtener()
    sugerencias = modelo.predecir(unicos, min(top_n, modelo.n_clases))
    # Para que el médico pueda elegir una sugerencia como diagnóstico de la consulta (enfermedad_id)
    ids = enfermedad_repo.ids_por_nombre(db, [s.enfermedad_es for s in sugerencias])
    return Prediccion(modelo_version=modelo.version, sugerencias=sugerencias, enfermedad_ids=ids)


def estado_modelo() -> dict:
    return predictor.estado()
