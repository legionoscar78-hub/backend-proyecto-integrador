"""El catálogo que carga seed_catalogo.py (nombres en español) debe contener todo lo que el modelo
puede devolver o recibir. Si no, una predicción no se podría ligar a una enfermedad de la BD ni un
síntoma elegido en pantalla llegaría al modelo. Se omite si falta el dataset crudo o los artefactos."""
import importlib.util
import json
from pathlib import Path

import pytest

from app.ml.features import normalizar_texto
from app.ml.predictor import ARTIFACTS
from ml_pipeline.config import cargar_config, ruta

CFG = cargar_config()
CSV = ruta(CFG, "raw") / CFG["data"]["symptoms_csv"]
METADATA, SINTOMAS_ES = ARTIFACTS / "metadata.json", ARTIFACTS / "symptoms_es.json"

pytestmark = pytest.mark.skipif(
    not (CSV.exists() and SINTOMAS_ES.exists() and METADATA.exists() and METADATA.stat().st_size > 0),
    reason="Falta el dataset crudo o los artefactos (ETL y entrenamiento)",
)


@pytest.fixture(scope="module")
def catalogo():
    ruta_seed = Path(__file__).resolve().parents[2] / "scripts" / "seed_catalogo.py"
    spec = importlib.util.spec_from_file_location("seed_catalogo", ruta_seed)
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    return seed.leer_catalogo(CSV)


def test_todo_sintoma_del_modelo_esta_en_el_catalogo_con_su_nombre_en_espanol(catalogo):
    nombres_es = json.loads(SINTOMAS_ES.read_text(encoding="utf-8"))
    faltan = [es for es in nombres_es.values() if es not in set(catalogo.sintomas)]
    assert not faltan, f"Síntomas del modelo que no están en la BD: {faltan}"


def test_toda_enfermedad_del_modelo_esta_en_el_catalogo_con_su_cie10(catalogo):
    clases = json.loads(METADATA.read_text(encoding="utf-8"))["clases"]
    for clase in clases:
        assert clase["enfermedad_es"] in catalogo.enfermedades, clase["enfermedad_es"]
        assert catalogo.descripciones[clase["enfermedad_es"]].startswith(f"CIE-10 {clase['cie10_codigo']}:")


def test_los_nombres_del_catalogo_son_unicos_aun_normalizados(catalogo):
    # Dos nombres que solo difieren en acentos o mayúsculas se confundirían al buscar por nombre
    for nombres in (catalogo.sintomas, catalogo.enfermedades):
        assert len({normalizar_texto(n) for n in nombres}) == len(nombres)
