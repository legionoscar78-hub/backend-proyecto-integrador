"""Predictor: carga el modelo entrenado una sola vez y sugiere enfermedades a partir de síntomas.

Uso desde la API:
    iniciar()                # al arrancar el servidor (lifespan); nunca lanza, guarda el error
    obtener().predecir(...)  # en cada petición; lanza ModeloNoDisponible si no se pudo cargar

El vector de entrada se construye con vectorizar_sintomas(), la misma función que usó el
entrenamiento, así que el orden de los síntomas es el de symptoms.json.
"""
import logging
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import torch

from app.ml.features import cargar_vocabulario, vectorizar_sintomas
from app.ml.model import ErrorDeArtefactos, cargar_modelo

log = logging.getLogger(__name__)

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
TOP_N_POR_DEFECTO = 5


class ModeloNoDisponible(RuntimeError):
    """El modelo no se pudo cargar (faltan artefactos o son incoherentes). La API responde 503."""


class SinSintomas(ValueError):
    """Se pidió una predicción sin ningún síntoma."""


@dataclass(frozen=True)
class Sugerencia:
    posicion: int  # 1 = la más probable
    enfermedad: str  # nombre en inglés: es la clave estable que usa el catálogo
    enfermedad_es: str
    cie10_codigo: str
    probabilidad: float


class Predictor:
    def __init__(self, modelo: torch.nn.Module, metadata: dict, vocabulario: list[str]):
        self._modelo = modelo
        self._vocabulario = vocabulario
        self._clases = metadata["clases"]
        self.metadata = metadata

    @classmethod
    def cargar(cls, artifacts: Path = ARTIFACTS) -> "Predictor":
        """Carga y valida los artefactos. Lanza ErrorDeArtefactos si algo no cuadra."""
        modelo, metadata = cargar_modelo(artifacts)  # ya comprueba el hash de symptoms.json
        vocabulario = cargar_vocabulario(artifacts / "symptoms.json")
        if len(vocabulario) != metadata["arquitectura"]["n_entrada"]:
            raise ErrorDeArtefactos("symptoms.json y el modelo tienen distinto número de síntomas")
        if len(metadata["clases"]) != metadata["arquitectura"]["n_clases"]:
            raise ErrorDeArtefactos("metadata.json tiene un número de clases distinto al del modelo")
        return cls(modelo, metadata, vocabulario)

    @property
    def version(self) -> str:
        return self.metadata["version"]

    @property
    def n_clases(self) -> int:
        return len(self._clases)

    @property
    def vocabulario(self) -> list[str]:
        return list(self._vocabulario)

    def predecir(self, sintomas: Sequence[str], top_n: int = TOP_N_POR_DEFECTO) -> list[Sugerencia]:
        """Las top_n enfermedades más probables, de mayor a menor probabilidad.

        Lanza SinSintomas si la lista está vacía y SintomaDesconocido (de features.py) si algún
        síntoma no está en el vocabulario del modelo. El orden y las repeticiones no importan.
        """
        if not 1 <= top_n <= len(self._clases):
            raise ValueError(f"top_n debe estar entre 1 y {len(self._clases)}")
        if not sintomas:
            raise SinSintomas("Se necesita al menos un síntoma")

        vector = torch.tensor([vectorizar_sintomas(sintomas, self._vocabulario)], dtype=torch.float32)
        with torch.inference_mode():
            probabilidades = torch.softmax(self._modelo(vector), dim=1)[0]
            valores, indices = probabilidades.topk(top_n)
        return [
            Sugerencia(
                posicion=posicion,
                enfermedad=self._clases[i]["enfermedad_en"],
                enfermedad_es=self._clases[i]["enfermedad_es"],
                cie10_codigo=self._clases[i]["cie10_codigo"],
                probabilidad=float(p),
            )
            for posicion, (i, p) in enumerate(zip(indices.tolist(), valores.tolist()), start=1)
        ]


# --- Instancia única de la aplicación -------------------------------------------------------

_cerrojo = threading.Lock()
_predictor: Predictor | None = None
_error: str | None = None


def iniciar(artifacts: Path = ARTIFACTS) -> None:
    """Intenta cargar el modelo y guarda el resultado. No lanza: la API debe arrancar aunque
    el modelo todavía no exista, y responder 503 solo en los endpoints que lo necesitan."""
    global _predictor, _error
    with _cerrojo:
        try:
            _predictor, _error = Predictor.cargar(artifacts), None
            log.info("Modelo %s cargado", _predictor.version)
        except (ErrorDeArtefactos, ValueError) as error:
            _predictor, _error = None, str(error)
            log.warning("Modelo no disponible: %s", error)


def obtener() -> Predictor:
    """El predictor cargado, o ModeloNoDisponible con el motivo."""
    if _predictor is None:
        raise ModeloNoDisponible(_error or "El modelo todavía no se ha cargado")
    return _predictor


def estado() -> dict:
    """Resumen para el endpoint de estado: si hay modelo y, si lo hay, qué modelo es."""
    if _predictor is None:
        return {"disponible": False, "error": _error or "El modelo todavía no se ha cargado"}
    m = _predictor.metadata
    return {
        "disponible": True,
        "version": m["version"],
        "fecha_entrenamiento": m["fecha_entrenamiento"],
        "n_sintomas": m["arquitectura"]["n_entrada"],
        "n_enfermedades": m["arquitectura"]["n_clases"],
        "metricas_test": m.get("metricas_test"),
    }
