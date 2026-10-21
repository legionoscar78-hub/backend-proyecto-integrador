"""Pruebas del entrenamiento con datos de juguete (no necesitan el dataset real)."""
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

torch = pytest.importorskip("torch")

from app.ml.model import crear_mlp  # noqa: E402
from ml_pipeline.training.train import (  # noqa: E402
    TOLERANCIA_MEJORA, ErrorDeEntrenamiento, cargar_datos, entrenar, guardar, pesos_por_clase,
)

N_SINTOMAS = 12
HP = {
    "hidden_layers": [16], "dropout": 0.1, "learning_rate": 0.01, "batch_size": 32,
    "epochs": 40, "patience": 5, "class_weights": "balanced",
}


def _juguete(n_por_clase=(80, 80, 40), seed=0):
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


def _entrenar(**cambios):
    Xt, yt = _juguete(seed=0)
    Xv, yv = _juguete(n_por_clase=(30, 30, 15), seed=1)
    return entrenar(Xt, yt, Xv, yv, n_clases=3, hp={**HP, **cambios}, seed=42)


def test_pesos_por_clase_balanceados():
    y = np.array([0] * 10 + [1] * 30)
    pesos = pesos_por_clase(y, 2)
    assert pesos.tolist() == pytest.approx([2.0, 40 / 60])


def test_pesos_fallan_si_una_clase_no_tiene_ejemplos():
    with pytest.raises(ErrorDeEntrenamiento):
        pesos_por_clase(np.array([0, 0, 1]), 3)


def test_aprende_un_problema_separable():
    res = _entrenar()
    assert res.metricas_val["top1"] > 0.9
    assert res.metricas_val["top3"] == pytest.approx(1.0)  # con 3 clases, top-3 siempre acierta


def test_misma_semilla_mismos_pesos():
    a, b = _entrenar(), _entrenar()
    assert a.mejor_epoca == b.mejor_epoca
    assert a.estado.keys() == b.estado.keys()
    assert all(torch.equal(a.estado[k], b.estado[k]) for k in a.estado)


def test_se_detiene_si_val_no_mejora():
    res = _entrenar(epochs=500, patience=2, learning_rate=0.05)
    assert len(res.historial) < 500
    # y devuelve la mejor época, no la última. Una mejora menor que la tolerancia no cuenta,
    # así que la guardada puede quedar apenas por encima del mínimo absoluto.
    perdidas = [f["val_loss"] for f in res.historial]
    assert res.metricas_val["loss"] == perdidas[res.mejor_epoca - 1]
    assert res.metricas_val["loss"] <= min(perdidas) + TOLERANCIA_MEJORA


def test_class_weights_invalido():
    with pytest.raises(ErrorDeEntrenamiento):
        _entrenar(class_weights="otro")


# ---------------------------------------------------------------- cargar_datos / guardar

def _preparar_carpetas(tmp_path, vocabulario=None, columnas=None):
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

    X, y = _juguete()
    df = pd.DataFrame(X.astype("uint8"), columns=columnas or vocabulario)
    df["enfermedad_en"] = [f"enfermedad {c}" for c in y]
    df["clase"] = y
    df = df.sample(frac=1, random_state=0).reset_index(drop=True)  # mezcla para que todas las clases estén en train
    df["split"] = ["train"] * 150 + ["val"] * 30 + ["test"] * 20
    df.to_parquet(processed / "dataset.parquet", index=False)
    return processed, artifacts


def test_cargar_datos_no_incluye_test(tmp_path):
    processed, artifacts = _preparar_carpetas(tmp_path)
    datos = cargar_datos(processed, artifacts)
    assert len(datos.y_train) == 150 and len(datos.y_val) == 30
    assert datos.X_train.shape == (150, N_SINTOMAS) and datos.X_train.dtype == np.float32


def test_cargar_datos_detecta_orden_distinto_del_vocabulario(tmp_path):
    vocab = [f"sintoma {i}" for i in range(N_SINTOMAS)]
    processed, artifacts = _preparar_carpetas(tmp_path, vocabulario=vocab, columnas=vocab[::-1])
    with pytest.raises(ErrorDeEntrenamiento, match="symptoms.json"):
        cargar_datos(processed, artifacts)


def test_guardar_escribe_modelo_y_metadata_coherentes(tmp_path):
    processed, artifacts = _preparar_carpetas(tmp_path)
    datos = cargar_datos(processed, artifacts)
    res = entrenar(datos.X_train, datos.y_train, datos.X_val, datos.y_val, 3, HP, seed=42)
    destino = guardar(res, datos, HP, 42, artifacts)

    meta = json.loads(destino["metadata"].read_text(encoding="utf-8"))
    assert meta["arquitectura"] == {"n_entrada": N_SINTOMAS, "n_clases": 3, "hidden_layers": [16], "dropout": 0.1}
    assert meta["datos"]["vocabulario_sha256"] == hashlib.sha256((artifacts / "symptoms.json").read_bytes()).hexdigest()
    assert [c["enfermedad_en"] for c in meta["clases"]] == ["enfermedad 0", "enfermedad 1", "enfermedad 2"]
    assert meta["version"].startswith("mlp-")

    # El predictor reconstruye la red solo con metadata.json y carga los pesos con weights_only
    a = meta["arquitectura"]
    modelo = crear_mlp(a["n_entrada"], a["n_clases"], a["hidden_layers"], a["dropout"])
    modelo.load_state_dict(torch.load(destino["modelo"], weights_only=True))
    modelo.eval()
    with torch.no_grad():
        pred = modelo(torch.from_numpy(datos.X_val)).argmax(dim=1).numpy()
    assert (pred == datos.y_val).mean() == pytest.approx(meta["metricas_val"]["top1"])
