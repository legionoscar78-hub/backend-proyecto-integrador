"""Preprocesamiento de síntomas, compartido por el ETL, el entrenamiento y el predictor.

Vive en un solo lugar a propósito: si el texto se normaliza o se vectoriza distinto al entrenar
que al predecir, el modelo falla en silencio (no da error, solo predice mal).

Se mantiene sin dependencias pesadas (nada de torch, pandas ni la base de datos) para poder
importarlo desde cualquier parte.
"""
import json
import unicodedata
from collections.abc import Iterable, Sequence
from pathlib import Path


class SintomaDesconocido(ValueError):
    """Se pidió un síntoma que no está en el vocabulario del modelo."""

    def __init__(self, sintomas: list[str]):
        self.sintomas = sintomas
        super().__init__(f"Síntomas fuera del vocabulario del modelo: {', '.join(sintomas)}")


def normalizar_texto(texto: str) -> str:
    """Minúsculas, sin acentos y con un solo espacio entre palabras."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", str(texto)) if not unicodedata.combining(c)
    )
    return " ".join(sin_acentos.lower().split())


def cargar_vocabulario(ruta: Path) -> list[str]:
    """Lee symptoms.json: la lista de síntomas, en el orden de las columnas del modelo."""
    vocabulario = json.loads(Path(ruta).read_text(encoding="utf-8"))
    if not isinstance(vocabulario, list) or not all(isinstance(s, str) for s in vocabulario):
        raise ValueError(f"{ruta} debe contener una lista de nombres de síntomas")
    if len(set(vocabulario)) != len(vocabulario):
        raise ValueError(f"{ruta} tiene síntomas repetidos")
    return vocabulario


def vectorizar_sintomas(
    sintomas: Iterable[str], vocabulario: Sequence[str], *, estricto: bool = True
) -> list[int]:
    """Vector 0/1 con un 1 en la posición de cada síntoma presente.

    El orden del vector es el de `vocabulario`. Con `estricto=True` (por defecto) un síntoma
    desconocido lanza SintomaDesconocido; con False se ignora.
    """
    indice = {nombre: i for i, nombre in enumerate(vocabulario)}
    vector = [0] * len(vocabulario)
    desconocidos = []
    for sintoma in sintomas:
        posicion = indice.get(normalizar_texto(sintoma))
        if posicion is None:
            desconocidos.append(sintoma)
        else:
            vector[posicion] = 1
    if desconocidos and estricto:
        raise SintomaDesconocido(desconocidos)
    return vector
