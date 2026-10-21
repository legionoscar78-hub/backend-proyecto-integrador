"""Pruebas del endpoint de predicción. Usan una app mínima: no necesitan base de datos ni .env."""
import pytest

pytest.importorskip("torch")
pytest.importorskip("httpx")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.v1.api import api_router  # noqa: E402
from app.ml import predictor as pred  # noqa: E402
from juguete import HP, preparar_carpetas  # noqa: E402
from ml_pipeline.training.train import cargar_datos, entrenar, guardar  # noqa: E402

app = FastAPI()
app.include_router(api_router, prefix="/api/v1")
cliente = TestClient(app)  # sin "with": no ejecuta el lifespan de main.py

URL = "/api/v1/ml/predecir"


@pytest.fixture(scope="module")
def artefactos(tmp_path_factory):
    processed, artifacts = preparar_carpetas(tmp_path_factory.mktemp("modelo"))
    datos = cargar_datos(processed, artifacts)
    res = entrenar(datos.X_train, datos.y_train, datos.X_val, datos.y_val, 3, HP, seed=42)
    guardar(res, datos, HP, 42, artifacts)
    return artifacts


@pytest.fixture
def con_modelo(artefactos, monkeypatch):
    monkeypatch.setattr(pred, "_predictor", pred.Predictor.cargar(artefactos))
    monkeypatch.setattr(pred, "_error", None)


@pytest.fixture
def sin_modelo(monkeypatch):
    monkeypatch.setattr(pred, "_predictor", None)
    monkeypatch.setattr(pred, "_error", "Faltan o están vacíos: model.pt. Ejecuta el ETL y el entrenamiento.")


def test_predecir_devuelve_sugerencias_y_aviso(con_modelo):
    r = cliente.post(URL, json={"sintomas": ["sintoma 3", "Sintoma 4"], "top_n": 2})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["modelo_version"].startswith("mlp-")
    assert [s["posicion"] for s in cuerpo["sugerencias"]] == [1, 2]
    assert cuerpo["sugerencias"][0]["enfermedad"] == "enfermedad 1"
    assert set(cuerpo["sugerencias"][0]) == {"posicion", "enfermedad", "enfermedad_es", "cie10_codigo", "probabilidad"}
    assert "no es un diagnóstico" in cuerpo["aviso"].lower()


def test_top_n_mayor_que_las_enfermedades_del_modelo_devuelve_todas(con_modelo):
    # top_n por defecto = 5 y el modelo de juguete solo tiene 3 enfermedades
    r = cliente.post(URL, json={"sintomas": ["sintoma 0"]})
    assert r.status_code == 200
    assert len(r.json()["sugerencias"]) == 3


def test_sintomas_repetidos_se_aceptan(con_modelo):
    r = cliente.post(URL, json={"sintomas": ["sintoma 0", "sintoma 0", "sintoma 1"], "top_n": 1})
    assert r.status_code == 200


def test_sintoma_desconocido_da_422_con_la_lista(con_modelo):
    r = cliente.post(URL, json={"sintomas": ["sintoma 0", "inventado"], "top_n": 1})
    assert r.status_code == 422
    assert r.json()["detail"]["sintomas"] == ["inventado"]


@pytest.mark.parametrize("cuerpo", [
    {"sintomas": []},
    {"sintomas": ["   "]},
    {"sintomas": ["a"] * 41},
    {"sintomas": ["sintoma 0"], "top_n": 0},
    {"sintomas": ["sintoma 0"], "top_n": 11},
    {},
])
def test_entradas_invalidas_dan_422(con_modelo, cuerpo):
    assert cliente.post(URL, json=cuerpo).status_code == 422


def test_sin_modelo_responde_503_con_el_motivo(sin_modelo):
    r = cliente.post(URL, json={"sintomas": ["sintoma 0"]})
    assert r.status_code == 503
    assert "model.pt" in r.json()["detail"]


def test_estado_con_y_sin_modelo(con_modelo, monkeypatch):
    ok = cliente.get("/api/v1/ml/estado").json()
    assert ok["disponible"] is True and ok["n_enfermedades"] == 3 and ok["error"] is None
    monkeypatch.setattr(pred, "_predictor", None)
    monkeypatch.setattr(pred, "_error", "no hay")
    r = cliente.get("/api/v1/ml/estado")
    assert r.status_code == 200 and r.json()["disponible"] is False and r.json()["error"] == "no hay"
