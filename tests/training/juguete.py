"""Datos y carpetas de juguete compartidos por las pruebas de entrenamiento y evaluación."""
import json

import numpy as np
import pandas as pd

N_SINTOMAS = 12
HP = {
    "hidden_layers": [16], "dropout": 0.1, "learning_rate": 0.01, "batch_size": 32,
    "epochs": 40, "patience": 5, "class_weights": "balanced",
}


def juguete(n_por_clase=(80, 80, 40), seed=0):
    """3 clases separables: cada una tiene 3 síntomas propios y hay algo de ruido."""
    rng = np.random.default_rng(seed)
    X, y = [], []
    for clase, n in enumerate(n_por_clase):
        base = np.zeros(N_SINTOMAS, dtype=np.float32)
        base[clase * 3:clase * 3 + 3] = 1
        for _ in range(n):
            fila = base.copy()
            ruido = rng.random(N_SINTOMAS) < 0.05
            fila[ruido] = 1 - fila[ruido]
            X.append(fila)
            y.append(clase)
    return np.array(X), np.array(y, dtype=np.int64)


def preparar_carpetas(tmp_path, vocabulario=None, columnas=None):
    processed, artifacts = tmp_path / "processed", tmp_path / "artifacts"
    processed.mkdir()
    artifacts.mkdir()
    vocabulario = vocabulario or [f"sintoma {i}" for i in range(N_SINTOMAS)]
    (artifacts / "symptoms.json").write_text(json.dumps(vocabulario), encoding="utf-8")
    clases = [
        {"indice": i, "enfermedad_en": f"enfermedad {i}", "enfermedad_es": f"enfermedad {i}", "cie10_codigo": f"A0{i}"}
        for i in range(3)
    ]
    (processed / "classes.json").write_text(json.dumps(clases), encoding="utf-8")

    X, y = juguete()
    df = pd.DataFrame(X.astype("uint8"), columns=columnas or vocabulario)
    df["enfermedad_en"] = [f"enfermedad {c}" for c in y]
    df["clase"] = y
    df = df.sample(frac=1, random_state=0).reset_index(drop=True)  # mezcla para que todas las clases estén en train
    df["split"] = ["train"] * 150 + ["val"] * 30 + ["test"] * 20
    df.to_parquet(processed / "dataset.parquet", index=False)
    return processed, artifacts
