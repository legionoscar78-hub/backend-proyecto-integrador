"""Pruebas de la evaluación con datos de juguete."""
import json

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from app.ml.model import ErrorDeArtefactos, cargar_modelo  # noqa: E402
from juguete import HP, preparar_carpetas  # noqa: E402
from ml_pipeline.training import evaluate as ev  # noqa: E402
from ml_pipeline.training.train import ErrorDeEntrenamiento, cargar_datos, entrenar, guardar  # noqa: E402

CLASES = [{"indice": i, "enfermedad_en": f"d{i}", "enfermedad_es": f"e{i}"} for i in range(4)]


# ---------------------------------------------------------------- métricas

def _casos():
    """8 casos, 4 clases, con aciertos, errores y una confusión repetida 1 -> 2."""
    y = np.array([0, 0, 1, 1, 1, 2, 3, 3])
    pred = np.array([0, 0, 1, 2, 2, 2, 3, 0])
    probs = np.full((8, 4), 0.05)
    probs[np.arange(8), pred] = 0.85
    return probs / probs.sum(axis=1, keepdims=True), y, pred


def test_metricas_globales_coinciden_con_scikit_learn():
    metrics = pytest.importorskip("sklearn.metrics")
    probs, y, pred = _casos()
    g = ev.metricas_globales(probs, y, ev.matriz_confusion(y, pred, 4))
    assert g["top1"] == pytest.approx(metrics.accuracy_score(y, pred))
    assert g["macro_f1"] == pytest.approx(metrics.f1_score(y, pred, average="macro", zero_division=0))
    assert g["macro_recall"] == pytest.approx(metrics.balanced_accuracy_score(y, pred))
    assert g["macro_precision"] == pytest.approx(metrics.precision_score(y, pred, average="macro", zero_division=0))
    assert g["log_loss"] == pytest.approx(metrics.log_loss(y, probs, labels=[0, 1, 2, 3]))


def test_top_k_cuenta_la_segunda_y_tercera_opcion():
    probs = np.array([[0.5, 0.3, 0.2, 0.0],    # real 1: segunda opción
                      [0.5, 0.3, 0.2, 0.0]])   # real 2: tercera opción
    y = np.array([1, 2])
    g = ev.metricas_globales(probs, y, ev.matriz_confusion(y, probs.argmax(axis=1), 4))
    assert (g["top1"], g["top3"]) == (0.0, 1.0)


def test_metricas_por_clase_y_clase_nunca_predicha():
    probs, y, pred = _casos()
    por_clase = ev.metricas_por_clase(ev.matriz_confusion(y, pred, 4), CLASES)
    clase1 = por_clase[1]
    assert (clase1["casos"], clase1["recall"]) == (3, pytest.approx(1 / 3))
    # nadie se predice como clase 3 con precisión indefinida: debe dar 0 y no NaN
    sin_predicciones = ev.metricas_por_clase(ev.matriz_confusion(np.array([3, 3]), np.array([0, 0]), 4), CLASES)[3]
    assert sin_predicciones["precision"] == 0 and sin_predicciones["f1"] == 0


def test_confusiones_ordenadas_y_sin_aciertos():
    probs, y, pred = _casos()
    top = ev.confusiones_principales(ev.matriz_confusion(y, pred, 4), CLASES, n=10)
    assert top[0] == {"real_en": "d1", "real_es": "e1", "predicho_en": "d2", "predicho_es": "e2",
                      "casos": 2, "porcentaje_de_la_real": pytest.approx(2 / 3)}
    assert len(top) == 2  # solo hay dos parejas con errores; los aciertos no aparecen
    assert all(c["real_en"] != c["predicho_en"] for c in top)


def test_calibracion_perfecta_y_sobreconfiada():
    y = np.array([0, 1, 0, 1])
    perfecta = np.array([[1.0, 0], [0, 1.0], [1.0, 0], [0, 1.0]])
    assert ev.calibracion(perfecta, y)["ece"] == pytest.approx(0)
    # siempre 99 % de confianza pero acierta la mitad: ECE ~ 0.49
    sobreconfiada = np.array([[0.99, 0.01]] * 4)
    assert ev.calibracion(sobreconfiada, y)["ece"] == pytest.approx(0.49)


def test_ambiguedad_detecta_vectores_vistos_en_train():
    X_train = np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32)
    X_test = np.array([[1, 0, 0], [0, 0, 1], [0, 1, 0]], dtype=np.float32)
    acierta = np.array([False, True, True])
    r = ev.ambiguedad(X_train, X_test, acierta)
    assert r["casos_ambiguos"] == 2
    assert (r["top1_en_ambiguos"], r["top1_en_no_ambiguos"]) == (0.5, 1.0)


# ---------------------------------------------------------------- flujo completo

def _entrenado(tmp_path):
    processed, artifacts = preparar_carpetas(tmp_path)
    datos = cargar_datos(processed, artifacts)
    res = entrenar(datos.X_train, datos.y_train, datos.X_val, datos.y_val, 3, HP, seed=42)
    guardar(res, datos, HP, 42, artifacts)
    cfg = {"paths": {"processed": str(processed), "artifacts": str(artifacts)}}
    return cfg, processed, artifacts


@pytest.fixture
def cfg_juguete(tmp_path):
    return _entrenado(tmp_path)  # rutas absolutas: ruta() las respeta aunque antepone backend/


def test_evaluar_escribe_informe_y_resumen_en_metadata(cfg_juguete):
    cfg, processed, artifacts = cfg_juguete
    informe = ev.ejecutar(cfg)

    assert informe["globales"]["casos"] == 20  # el split test del juguete
    assert informe["globales"]["top1"] > 0.8
    escrito = json.loads((processed / "evaluacion_test.json").read_text(encoding="utf-8"))
    assert escrito["modelo"] == informe["modelo"]
    assert len(escrito["por_clase"]) == 3

    meta = json.loads((artifacts / "metadata.json").read_text(encoding="utf-8"))
    assert meta["metricas_test"]["top1"] == informe["globales"]["top1"]
    assert meta["metricas_val"]  # lo de validación sigue ahí


def test_no_se_evalua_dos_veces_sin_forzar(cfg_juguete):
    cfg, _, _ = cfg_juguete
    ev.ejecutar(cfg)
    with pytest.raises(ErrorDeEntrenamiento, match="ya se evaluó"):
        ev.ejecutar(cfg)
    ev.ejecutar(cfg, forzar=True)  # con --forzar sí se permite


# ---------------------------------------------------------------- cargar_modelo

def test_cargar_modelo_falla_si_cambia_el_vocabulario(tmp_path):
    _, _, artifacts = _entrenado(tmp_path)
    vocab = json.loads((artifacts / "symptoms.json").read_text(encoding="utf-8"))
    (artifacts / "symptoms.json").write_text(json.dumps(vocab[::-1]), encoding="utf-8")
    with pytest.raises(ErrorDeArtefactos, match="vocabulario"):
        cargar_modelo(artifacts)


def test_cargar_modelo_falla_si_faltan_artefactos(tmp_path):
    _, _, artifacts = _entrenado(tmp_path)
    (artifacts / "model.pt").write_bytes(b"")
    with pytest.raises(ErrorDeArtefactos, match="model.pt"):
        cargar_modelo(artifacts)


def test_cargar_modelo_falla_si_model_pt_esta_corrupto(tmp_path):
    _, _, artifacts = _entrenado(tmp_path)
    (artifacts / "model.pt").write_bytes(b"esto no es un modelo")
    with pytest.raises(ErrorDeArtefactos):
        cargar_modelo(artifacts)
