"""El predictor con el modelo real. Se omite si falta model.pt (está en .gitignore) o el dataset."""
import numpy as np
import pytest

torch = pytest.importorskip("torch")
pd = pytest.importorskip("pandas")

from app.ml.predictor import ARTIFACTS, Predictor  # noqa: E402
from ml_pipeline.config import cargar_config, ruta  # noqa: E402

CFG = cargar_config()
PARQUET = ruta(CFG, "processed") / "dataset.parquet"

pytestmark = pytest.mark.skipif(
    not ((ARTIFACTS / "model.pt").is_file() and (ARTIFACTS / "model.pt").stat().st_size > 0 and PARQUET.is_file()),
    reason="Falta el modelo entrenado o dataset.parquet: ejecuta el ETL y el entrenamiento",
)


@pytest.fixture(scope="module")
def predictor():
    return Predictor.cargar()


@pytest.fixture(scope="module")
def muestra_test(predictor):
    df = pd.read_parquet(PARQUET)
    return df[df["split"] == "test"].sample(300, random_state=0).reset_index(drop=True)


def test_el_predictor_da_lo_mismo_que_el_modelo_sobre_el_vector_del_dataset(predictor, muestra_test):
    """Punto crítico: nombres -> vector (predictor) debe dar el mismo vector que el del entrenamiento.

    Los nombres se pasan en orden aleatorio para comprobar que el orden de entrada no importa.
    """
    vocabulario = predictor.vocabulario
    modelo = predictor._modelo
    rng = np.random.default_rng(0)
    for _, fila in muestra_test.iterrows():
        activos = [s for s in vocabulario if fila[s] == 1]
        rng.shuffle(activos)
        vector = torch.tensor([[float(fila[s]) for s in vocabulario]])
        with torch.no_grad():
            directo = torch.softmax(modelo(vector), dim=1)[0]
        mejor = predictor.predecir(activos, top_n=1)[0]
        assert mejor.enfermedad == predictor._clases[directo.argmax().item()]["enfermedad_en"]
        assert mejor.probabilidad == pytest.approx(directo.max().item(), abs=1e-6)


def test_acierto_top1_en_la_muestra_es_coherente_con_la_evaluacion(predictor, muestra_test):
    """La evaluación completa dio ~0.93 en test; en 300 casos debe estar cerca (no cae a ~0)."""
    vocabulario = predictor.vocabulario
    aciertos = sum(
        predictor.predecir([s for s in vocabulario if fila[s] == 1], top_n=1)[0].enfermedad == fila["enfermedad_en"]
        for _, fila in muestra_test.iterrows()
    )
    assert aciertos / len(muestra_test) > 0.85


def test_probabilidades_validas(predictor):
    sugerencias = predictor.predecir([predictor.vocabulario[0]], top_n=10)
    probs = [s.probabilidad for s in sugerencias]
    assert probs == sorted(probs, reverse=True) and 0 < sum(probs) <= 1.0 + 1e-9
