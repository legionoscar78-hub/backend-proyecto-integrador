"""Pruebas del predictor con un modelo de juguete entrenado en el momento."""
import json
import shutil

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from app.ml import predictor as pred  # noqa: E402
from app.ml.features import SintomaDesconocido, vectorizar_sintomas  # noqa: E402
from app.ml.model import ErrorDeArtefactos, cargar_modelo  # noqa: E402
from juguete import HP, N_SINTOMAS, preparar_carpetas  # noqa: E402
from ml_pipeline.training.train import cargar_datos, entrenar, guardar  # noqa: E402


@pytest.fixture(scope="module")
def artefactos(tmp_path_factory):
    processed, artifacts = preparar_carpetas(tmp_path_factory.mktemp("modelo"))
    datos = cargar_datos(processed, artifacts)
    res = entrenar(datos.X_train, datos.y_train, datos.X_val, datos.y_val, 3, HP, seed=42)
    guardar(res, datos, HP, 42, artifacts)
    return artifacts


@pytest.fixture
def predictor_juguete(artefactos):
    return pred.Predictor.cargar(artefactos)


@pytest.fixture(autouse=True)
def estado_limpio(monkeypatch):
    """Cada prueba empieza sin modelo cargado en el módulo y lo deja igual."""
    monkeypatch.setattr(pred, "_predictor", None)
    monkeypatch.setattr(pred, "_error", None)


# Síntomas propios de cada clase del juguete (ver tests/utils/juguete.py)
CLASE0 = ["sintoma 0", "sintoma 1", "sintoma 2"]
CLASE1 = ["sintoma 3", "sintoma 4", "sintoma 5"]
CLASE2 = ["sintoma 6", "sintoma 7", "sintoma 8"]


def test_devuelve_top_n_ordenado_y_con_probabilidades_validas(predictor_juguete):
    sugerencias = predictor_juguete.predecir(CLASE1, top_n=3)
    assert [s.posicion for s in sugerencias] == [1, 2, 3]
    probs = [s.probabilidad for s in sugerencias]
    assert probs == sorted(probs, reverse=True)
    assert sum(probs) == pytest.approx(1.0)  # con 3 clases y top_n=3 cubre todo
    assert sugerencias[0].enfermedad == "enfermedad 1" and sugerencias[0].cie10_codigo == "A01"


def test_top_n_menor_devuelve_solo_esas(predictor_juguete):
    assert len(predictor_juguete.predecir(CLASE0, top_n=1)) == 1


def test_acierta_las_tres_clases_del_juguete(predictor_juguete):
    for esperado, sintomas in enumerate([CLASE0, CLASE1, CLASE2]):
        assert predictor_juguete.predecir(sintomas, top_n=1)[0].enfermedad == f"enfermedad {esperado}"


def test_orden_mayusculas_y_repeticiones_no_cambian_el_resultado(predictor_juguete):
    base = predictor_juguete.predecir(CLASE2, top_n=3)
    alterado = predictor_juguete.predecir(["  SINTOMA 8", "sintoma 6", "Sintoma 7", "sintoma 7"], top_n=3)
    assert base == alterado


def test_sintoma_desconocido_los_lista_todos(predictor_juguete):
    with pytest.raises(SintomaDesconocido) as error:
        predictor_juguete.predecir(["sintoma 0", "fiebre inventada", "otra cosa"], top_n=1)
    assert error.value.sintomas == ["fiebre inventada", "otra cosa"]


def test_sin_sintomas(predictor_juguete):
    with pytest.raises(pred.SinSintomas):
        predictor_juguete.predecir([], top_n=1)


@pytest.mark.parametrize("top_n", [0, 4, -1])
def test_top_n_fuera_de_rango(predictor_juguete, top_n):
    with pytest.raises(ValueError, match="top_n"):
        predictor_juguete.predecir(CLASE0, top_n=top_n)


def test_coincide_con_el_modelo_sobre_el_vector_de_entrenamiento(artefactos, predictor_juguete):
    """Mismo vector por los dos caminos: el del predictor (nombres) y el directo (0/1)."""
    modelo, _ = cargar_modelo(artefactos)
    vocabulario = json.loads((artefactos / "symptoms.json").read_text(encoding="utf-8"))
    rng = np.random.default_rng(0)
    for _ in range(50):
        activos = rng.choice(N_SINTOMAS, size=rng.integers(1, 6), replace=False)
        nombres = [vocabulario[i] for i in activos]
        vector = torch.tensor([vectorizar_sintomas(nombres, vocabulario)], dtype=torch.float32)
        with torch.no_grad():
            directo = torch.softmax(modelo(vector), dim=1)[0]
        sugerencia = predictor_juguete.predecir(nombres, top_n=1)[0]
        assert sugerencia.probabilidad == pytest.approx(directo.max().item())
        assert sugerencia.enfermedad == f"enfermedad {directo.argmax().item()}"


# ---------------------------------------------------------------- instancia única

def test_iniciar_con_artefactos_deja_el_modelo_disponible(artefactos):
    pred.iniciar(artefactos)
    estado = pred.estado()
    assert estado["disponible"] and estado["version"].startswith("mlp-")
    assert (estado["n_sintomas"], estado["n_enfermedades"]) == (N_SINTOMAS, 3)
    assert pred.obtener().version == estado["version"]


def test_iniciar_sin_artefactos_no_lanza_y_obtener_si(tmp_path):
    pred.iniciar(tmp_path)  # carpeta vacía: no debe lanzar
    assert pred.estado()["disponible"] is False
    with pytest.raises(pred.ModeloNoDisponible, match="Faltan"):
        pred.obtener()


def test_cargar_falla_si_los_artefactos_no_cuadran(artefactos, tmp_path):
    copia = tmp_path / "copia"
    shutil.copytree(artefactos, copia)
    meta = json.loads((copia / "metadata.json").read_text(encoding="utf-8"))
    meta["clases"] = meta["clases"][:2]  # menos clases que las del modelo
    (copia / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ErrorDeArtefactos, match="clases"):
        pred.Predictor.cargar(copia)


# ---------------------------------------------------------------- nombres en español

@pytest.fixture
def artefactos_con_es(artefactos, tmp_path):
    """Copia de los artefactos de juguete con symptoms_es.json (el síntoma i se llama 'síntoma i' en español)."""
    copia = tmp_path / "con_es"
    shutil.copytree(artefactos, copia)
    vocabulario = json.loads((copia / "symptoms.json").read_text(encoding="utf-8"))
    nombres = {en: en.replace("sintoma", "Dolor número") for en in vocabulario}
    (copia / "symptoms_es.json").write_text(json.dumps(nombres, ensure_ascii=False), encoding="utf-8")
    return copia


def test_acepta_nombres_en_espanol_igual_que_en_ingles(artefactos_con_es):
    p = pred.Predictor.cargar(artefactos_con_es)
    en = p.predecir(CLASE1, top_n=3)
    es = p.predecir(["dolor numero 3", "DOLOR NÚMERO 4", "Dolor número 5"], top_n=3)  # sin acentos, con ellos, en mayúsculas
    assert es == en


def test_acepta_mezclar_idiomas(artefactos_con_es):
    p = pred.Predictor.cargar(artefactos_con_es)
    assert p.predecir(["Dolor número 6", "sintoma 7", "Dolor número 8"], top_n=3) == p.predecir(CLASE2, top_n=3)


def test_nombre_desconocido_se_informa_tal_como_llego(artefactos_con_es):
    p = pred.Predictor.cargar(artefactos_con_es)
    with pytest.raises(SintomaDesconocido) as error:
        p.predecir(["Dolor número 3", "Dolor raro"], top_n=1)
    assert error.value.sintomas == ["Dolor raro"]


def test_sin_symptoms_es_json_solo_se_aceptan_nombres_en_ingles(artefactos):
    with pytest.raises(SintomaDesconocido):
        pred.Predictor.cargar(artefactos).predecir(["Dolor número 3"], top_n=1)


def test_symptoms_es_json_que_no_cuadra_con_el_vocabulario(artefactos_con_es):
    (artefactos_con_es / "symptoms_es.json").write_text(json.dumps({"sintoma 0": "x"}), encoding="utf-8")
    with pytest.raises(ErrorDeArtefactos, match="symptoms_es.json"):
        pred.Predictor.cargar(artefactos_con_es)


def test_symptoms_es_json_corrupto(artefactos_con_es):
    (artefactos_con_es / "symptoms_es.json").write_text("{no es json", encoding="utf-8")
    with pytest.raises(ErrorDeArtefactos, match="symptoms_es.json"):
        pred.Predictor.cargar(artefactos_con_es)
