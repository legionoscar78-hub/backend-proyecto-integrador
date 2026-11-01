"""Pruebas del endpoint de predicción. Usan una app mínima sobre SQLite en memoria (el catálogo de enfermedades)."""
import pytest

pytest.importorskip("torch")
pytest.importorskip("httpx")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: E402,F401
from app.api.deps import get_current_medico, get_db  # noqa: E402
from app.core.database import Base  # noqa: E402
from app.models import Enfermedad  # noqa: E402
from app.api.v1.api import api_router  # noqa: E402
from app.ml import predictor as pred  # noqa: E402
from juguete import HP, preparar_carpetas  # noqa: E402
from ml_pipeline.training.train import cargar_datos, entrenar, guardar  # noqa: E402

motor = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
Sesion = sessionmaker(bind=motor, autoflush=False)


def _get_db_prueba():
    db = Sesion()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def catalogo_vacio():
    """Cada prueba empieza con tablas vacías."""
    Base.metadata.drop_all(motor)
    Base.metadata.create_all(motor)


app = FastAPI()
app.include_router(api_router, prefix="/api/v1")
app.dependency_overrides[get_current_medico] = lambda: object()  # un médico cualquiera con sesión
app.dependency_overrides[get_db] = _get_db_prueba
cliente = TestClient(app)  # sin "with": no ejecuta el lifespan de main.py

# La misma app, pero sin saltarse la autenticación
app_real = FastAPI()
app_real.include_router(api_router, prefix="/api/v1")
cliente_sin_sesion = TestClient(app_real)

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
    assert set(cuerpo["sugerencias"][0]) == {
        "posicion", "enfermedad", "enfermedad_es", "cie10_codigo", "probabilidad", "enfermedad_id"}
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


def test_predecir_exige_sesion_de_medico(con_modelo):
    r = cliente_sin_sesion.post(URL, json={"sintomas": ["sintoma 0"]})
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
    assert cliente_sin_sesion.post(URL, json={"sintomas": ["sintoma 0"]},
                                   headers={"Authorization": "Bearer basura"}).status_code == 401


def test_estado_sigue_siendo_publico(con_modelo):
    assert cliente_sin_sesion.get("/api/v1/ml/estado").status_code == 200


def test_cada_sugerencia_trae_el_id_de_la_enfermedad_en_el_catalogo(con_modelo):
    # Las clases del modelo de juguete se llaman "enfermedad 0", "enfermedad 1", "enfermedad 2" (en español)
    with Sesion() as db:
        db.add_all([Enfermedad(nombre="enfermedad 1"), Enfermedad(nombre="otra")])
        db.commit()
        id_1 = db.query(Enfermedad).filter_by(nombre="enfermedad 1").one().id
    r = cliente.post(URL, json={"sintomas": ["sintoma 3", "sintoma 4", "sintoma 5"], "top_n": 3})
    ids = {s["enfermedad_es"]: s["enfermedad_id"] for s in r.json()["sugerencias"]}
    assert ids["enfermedad 1"] == id_1
    assert ids["enfermedad 0"] is None and ids["enfermedad 2"] is None  # no están cargadas en la BD
