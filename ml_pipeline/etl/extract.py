"""Extracción: lee el dataset crudo y los catálogos. No transforma nada."""
from pathlib import Path

import pandas as pd

COL_ENFERMEDAD = "diseases"


def leer_dataset(ruta: Path) -> pd.DataFrame:
    """DiseaseAndSymptoms.csv: una columna `diseases` y una columna 0/1 por síntoma."""
    cabecera = pd.read_csv(ruta, nrows=0).columns
    if COL_ENFERMEDAD not in cabecera:
        raise ValueError(f"{ruta.name} no tiene la columna '{COL_ENFERMEDAD}'")
    # int8: el CSV pesa ~190 MB y con int64 ocuparía más de 700 MB en memoria
    tipos = {c: "int8" for c in cabecera if c != COL_ENFERMEDAD}
    return pd.read_csv(ruta, dtype=tipos)


def leer_label_map(ruta: Path) -> pd.DataFrame:
    return pd.read_csv(ruta)


def leer_sintomas(ruta: Path) -> pd.DataFrame:
    return pd.read_csv(ruta)
