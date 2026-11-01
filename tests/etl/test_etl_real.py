"""ETL de punta a punta con el dataset real. Se omite si DiseaseAndSymptoms.csv no está en raw/
(el CSV no se versiona en git). Tarda ~30 s porque lee 190 MB."""
import copy
import json

import numpy as np
import pandas as pd
import pytest

from app.ml.features import cargar_vocabulario, normalizar_texto, vectorizar_sintomas
from ml_pipeline.config import cargar_config, ruta
from ml_pipeline.etl.run_etl import ejecutar
from ml_pipeline.etl.transform import COL_CLASE, COL_SPLIT

CFG = cargar_config()
CSV = ruta(CFG, "raw") / CFG["data"]["symptoms_csv"]

pytestmark = pytest.mark.skipif(not CSV.exists(), reason=f"falta {CSV.name} en raw/")


@pytest.fixture(scope="module")
def corrida(tmp_path_factory):
    """Corre el ETL escribiendo en una carpeta temporal, sin tocar processed/ ni artifacts/."""
    base = tmp_path_factory.mktemp("etl")
    cfg = copy.deepcopy(CFG)
    cfg["paths"]["processed"] = str(base / "processed")
    cfg["paths"]["artifacts"] = str(base / "artifacts")
    return ejecutar(cfg), base


def test_hay_una_clase_por_enfermedad_del_label_map(corrida):
    resultado, _ = corrida
    label_map = pd.read_csv(ruta(CFG, "mappings") / "label_map.csv")
    assert len(resultado.clases) == len(label_map)
    assert set(resultado.datos[COL_CLASE]) == set(range(len(label_map)))


def test_el_vocabulario_es_el_de_sintomas_csv_en_su_orden(corrida):
    resultado, _ = corrida
    sv = pd.read_csv(ruta(CFG, "mappings") / "sintomas.csv")
    esperado = sv.loc[sv["usado_en_modelo"] == 1].sort_values("orden")["nombre_en"].tolist()
    assert resultado.vocabulario == esperado
    assert list(resultado.datos.columns[: len(esperado)]) == esperado


def test_symptoms_json_se_escribe_y_se_puede_cargar(corrida):
    resultado, base = corrida
    assert cargar_vocabulario(base / "artifacts" / "symptoms.json") == resultado.vocabulario


def test_symptoms_es_json_tiene_un_nombre_por_sintoma_del_vocabulario(corrida):
    resultado, base = corrida
    es = json.loads((base / "artifacts" / "symptoms_es.json").read_text(encoding="utf-8"))
    assert list(es) == resultado.vocabulario
    assert len(set(map(normalizar_texto, es.values()))) == len(es)


def test_el_parquet_conserva_los_datos(corrida):
    resultado, base = corrida
    leido = pd.read_parquet(base / "processed" / "dataset.parquet")
    assert leido.shape == resultado.datos.shape
    assert leido[COL_SPLIT].tolist() == resultado.datos[COL_SPLIT].tolist()


def test_cada_clase_esta_en_train_val_y_test(corrida):
    resultado, _ = corrida
    cuenta = resultado.datos.groupby(COL_CLASE)[COL_SPLIT].nunique()
    assert (cuenta == 3).all()


def test_no_hay_filas_repetidas_entre_train_y_test(corrida):
    resultado, _ = corrida
    datos = resultado.datos
    sintomas = datos[resultado.vocabulario].to_numpy(dtype="uint8")
    split = datos[COL_SPLIT].to_numpy()
    llaves = [(fila.tobytes(), clase) for fila, clase in zip(sintomas, datos[COL_CLASE].to_numpy())]
    train = {k for k, s in zip(llaves, split) if s == "train"}
    test = {k for k, s in zip(llaves, split) if s == "test"}
    assert not train & test


def test_el_vector_de_entrenamiento_es_identico_al_que_produce_features(corrida):
    """EL punto crítico: lo que ve el modelo al entrenar == lo que vectoriza features.py al predecir."""
    resultado, _ = corrida
    vocab = resultado.vocabulario
    muestra = resultado.datos.sample(500, random_state=1)
    for _, fila in muestra.iterrows():
        presentes = [vocab[i] for i, v in enumerate(fila[vocab].values) if v == 1]
        np.random.default_rng(0).shuffle(presentes)
        assert vectorizar_sintomas(presentes, vocab) == fila[vocab].astype(int).tolist()
