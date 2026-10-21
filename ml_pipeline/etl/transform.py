"""Transformación: del dataset crudo a la matriz lista para entrenar.

Son funciones puras (no leen ni escriben archivos); las decisiones que toman están
justificadas en notebooks/02_eda_sintomas.ipynb.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from app.ml.features import normalizar_texto
from ml_pipeline.etl.extract import COL_ENFERMEDAD

COL_ENFERMEDAD_EN = "enfermedad_en"  # columna de salida con el nombre de la enfermedad
COL_CLASE = "clase"
COL_SPLIT = "split"


class ErrorDeDatos(ValueError):
    """Los datos o los catálogos no cumplen lo que el ETL necesita."""


@dataclass
class Resultado:
    datos: pd.DataFrame      # síntomas (uint8, en orden del vocabulario) + enfermedad_en + clase + split
    vocabulario: list[str]   # -> symptoms.json
    clases: list[dict]       # índice de clase -> enfermedad y código CIE-10
    reporte: dict


def _lista(valores, maximo=8) -> str:
    valores = sorted(valores)
    extra = f" (+{len(valores) - maximo} más)" if len(valores) > maximo else ""
    return ", ".join(valores[:maximo]) + extra


def normalizar_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza los nombres de síntomas (columnas) y de enfermedades, igual que la BD."""
    columnas = [c if c == COL_ENFERMEDAD else normalizar_texto(c) for c in df.columns]
    if len(set(columnas)) != len(columnas):
        raise ErrorDeDatos("Hay columnas repetidas tras normalizar los nombres")
    df = df.copy()
    df.columns = columnas
    df[COL_ENFERMEDAD] = df[COL_ENFERMEDAD].map(normalizar_texto)
    return df


def dividir(clases: pd.Series, val_size: float, test_size: float, seed: int) -> np.ndarray:
    """Etiqueta cada fila como train/val/test, estratificando por clase."""
    posiciones = np.arange(len(clases))
    pos_trainval, pos_test = train_test_split(
        posiciones, test_size=test_size, stratify=clases, random_state=seed
    )
    pos_train, pos_val = train_test_split(
        pos_trainval,
        test_size=val_size / (1 - test_size),
        stratify=clases.iloc[pos_trainval],
        random_state=seed,
    )
    etiquetas = np.empty(len(clases), dtype=object)
    etiquetas[pos_train], etiquetas[pos_val], etiquetas[pos_test] = "train", "val", "test"
    return etiquetas


def transformar(
    df: pd.DataFrame,
    label_map: pd.DataFrame,
    sintomas: pd.DataFrame,
    *,
    min_casos: int,
    val_size: float,
    test_size: float,
    seed: int,
) -> Resultado:
    df = normalizar_dataset(df)
    filas_originales = len(df)

    lm = label_map.copy()
    lm["enfermedad_en"] = lm["enfermedad_en"].map(normalizar_texto)
    if not lm["enfermedad_en"].is_unique or not lm["cie10_codigo"].is_unique:
        raise ErrorDeDatos("label_map.csv tiene enfermedades o códigos CIE-10 repetidos")
    lm = lm.sort_values("cie10_codigo").reset_index(drop=True)

    sv = sintomas.copy()
    sv["nombre_en"] = sv["nombre_en"].map(normalizar_texto)

    # --- los síntomas del dataset deben ser exactamente los de sintomas.csv
    columnas = [c for c in df.columns if c != COL_ENFERMEDAD]
    if set(columnas) != set(sv["nombre_en"]):
        raise ErrorDeDatos(
            "sintomas.csv no coincide con las columnas del dataset. "
            f"Faltan en el CSV: {_lista(set(columnas) - set(sv['nombre_en']))}. "
            f"Sobran: {_lista(set(sv['nombre_en']) - set(columnas))}"
        )

    # --- subconjunto de enfermedades
    faltan = set(lm["enfermedad_en"]) - set(df[COL_ENFERMEDAD])
    if faltan:
        raise ErrorDeDatos(f"Enfermedades de label_map.csv que no están en el dataset: {_lista(faltan)}")
    df = df[df[COL_ENFERMEDAD].isin(lm["enfermedad_en"])]
    filas_subconjunto = len(df)

    # --- duplicados exactos: se quitan antes de dividir para no filtrar filas entre train y test.
    # Las filas con los mismos síntomas pero distinta enfermedad NO se tocan (ver EDA, sección 6).
    df = df.drop_duplicates().reset_index(drop=True)

    por_clase = df[COL_ENFERMEDAD].value_counts()
    pocas = por_clase[por_clase < min_casos]
    if len(pocas):
        raise ErrorDeDatos(
            f"Enfermedades con menos de {min_casos} casos únicos: "
            + ", ".join(f"{e} ({n})" for e, n in pocas.items())
        )

    # --- vocabulario: los síntomas marcados en sintomas.csv, en su orden
    vocabulario = sv.loc[sv["usado_en_modelo"] == 1].sort_values("orden")["nombre_en"].tolist()
    con_casos = {c for c in columnas if df[c].any()}
    perdidos = con_casos - set(vocabulario)
    if perdidos:
        raise ErrorDeDatos(
            "Hay síntomas con casos que no están marcados como usado_en_modelo en sintomas.csv "
            f"(se perderían del modelo): {_lista(perdidos)}"
        )
    sin_casos = sorted(set(vocabulario) - con_casos)

    # --- clases, en orden de código CIE-10
    indice_clase = {e: i for i, e in enumerate(lm["enfermedad_en"])}
    clases = [
        {"indice": i, "enfermedad_en": r.enfermedad_en, "enfermedad_es": r.enfermedad_es,
         "cie10_codigo": r.cie10_codigo}
        for i, r in enumerate(lm.itertuples())
    ]

    datos = df[vocabulario].astype("uint8")
    datos[COL_ENFERMEDAD_EN] = df[COL_ENFERMEDAD]
    datos[COL_CLASE] = df[COL_ENFERMEDAD].map(indice_clase).astype("int16")
    datos[COL_SPLIT] = dividir(datos[COL_CLASE], val_size, test_size, seed)

    reporte = {
        "semilla": seed,
        "filas_originales": filas_originales,
        "filas_subconjunto": filas_subconjunto,
        "duplicados_eliminados": filas_subconjunto - len(datos),
        "filas_finales": len(datos),
        "enfermedades": len(clases),
        "sintomas_en_vocabulario": len(vocabulario),
        "sintomas_del_vocabulario_sin_casos": sin_casos,
        "casos_por_enfermedad": {"min": int(por_clase.min()), "max": int(por_clase.max())},
        "filas_por_split": {k: int(v) for k, v in datos[COL_SPLIT].value_counts().items()},
    }
    return Resultado(datos=datos, vocabulario=vocabulario, clases=clases, reporte=reporte)
