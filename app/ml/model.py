"""Arquitectura del MLP y carga de los artefactos entrenados.

La usan el entrenamiento, la evaluación y el predictor, así que vive aquí y no en
ml_pipeline/: todos tienen que construir exactamente la misma red.
"""
import hashlib
import json
from pathlib import Path

import torch
from torch import nn


class ErrorDeArtefactos(RuntimeError):
    """Faltan los artefactos del modelo o no son coherentes entre sí."""


def crear_mlp(n_entrada: int, n_clases: int, capas: list[int], dropout: float) -> nn.Sequential:
    """MLP que devuelve logits (sin softmax): Linear -> ReLU -> Dropout por cada capa oculta."""
    if n_entrada < 1 or n_clases < 2:
        raise ValueError("Se necesita al menos 1 entrada y 2 clases")
    if not capas or any(n < 1 for n in capas):
        raise ValueError("hidden_layers debe tener al menos una capa de tamaño >= 1")
    if not 0 <= dropout < 1:
        raise ValueError("dropout debe estar en [0, 1)")

    bloques: list[nn.Module] = []
    previo = n_entrada
    for n in capas:
        bloques += [nn.Linear(previo, n), nn.ReLU(), nn.Dropout(dropout)]
        previo = n
    bloques.append(nn.Linear(previo, n_clases))
    return nn.Sequential(*bloques)


def cargar_modelo(artifacts: Path) -> tuple[nn.Sequential, dict]:
    """Reconstruye el modelo en modo evaluación a partir de model.pt y metadata.json.

    Comprueba que symptoms.json sea el vocabulario con el que se entrenó: si no, el vector
    de entrada tendría otro orden y las predicciones saldrían mal sin dar ningún error.
    Devuelve (modelo, metadata).
    """
    archivos = {n: artifacts / n for n in ("model.pt", "metadata.json", "symptoms.json")}
    faltan = [n for n, ruta in archivos.items() if not ruta.is_file() or ruta.stat().st_size == 0]
    if faltan:
        raise ErrorDeArtefactos(
            f"Faltan o están vacíos: {', '.join(faltan)}. Ejecuta el ETL y el entrenamiento."
        )

    try:
        metadata = json.loads(archivos["metadata.json"].read_text(encoding="utf-8"))
        arq = metadata["arquitectura"]
        esperado = metadata["datos"]["vocabulario_sha256"]
    except (json.JSONDecodeError, KeyError) as error:
        raise ErrorDeArtefactos(f"metadata.json no es válido: {error!r}") from error

    if hashlib.sha256(archivos["symptoms.json"].read_bytes()).hexdigest() != esperado:
        raise ErrorDeArtefactos(
            "symptoms.json no es el vocabulario con el que se entrenó el modelo. "
            "Vuelve a ejecutar el entrenamiento."
        )

    modelo = crear_mlp(arq["n_entrada"], arq["n_clases"], arq["hidden_layers"], arq["dropout"])
    try:
        # weights_only: model.pt solo contiene tensores; no se ejecuta código al cargarlo
        modelo.load_state_dict(torch.load(archivos["model.pt"], map_location="cpu", weights_only=True))
    except Exception as error:  # torch.load lanza tipos distintos según cómo esté dañado el archivo
        raise ErrorDeArtefactos(f"model.pt no coincide con metadata.json: {error}") from error
    modelo.eval()
    return modelo, metadata
