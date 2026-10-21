"""Arquitectura del MLP. La usan el entrenamiento y el predictor, así que vive aquí
y no en ml_pipeline/: los dos tienen que construir exactamente la misma red."""
from torch import nn


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
