"""Coherencia de los catálogos versionados en ml_pipeline/mappings (no necesita el dataset crudo)."""
import re

import pandas as pd
import pytest

from app.ml.features import normalizar_texto
from ml_pipeline.config import cargar_config, ruta

CFG = cargar_config()
MAPPINGS = ruta(CFG, "mappings")


@pytest.fixture(scope="module")
def sintomas():
    return pd.read_csv(MAPPINGS / "sintomas.csv")


@pytest.fixture(scope="module")
def label_map():
    return pd.read_csv(MAPPINGS / "label_map.csv")


class TestSintomasCsv:
    def test_son_377_con_orden_contiguo(self, sintomas):
        assert len(sintomas) == 377
        assert sintomas["orden"].tolist() == list(range(377))

    def test_las_claves_en_ingles_son_unicas_y_estan_normalizadas(self, sintomas):
        assert sintomas["nombre_en"].is_unique
        assert (sintomas["nombre_en"] == sintomas["nombre_en"].map(normalizar_texto)).all()

    def test_todos_tienen_traduccion_unica(self, sintomas):
        assert sintomas["nombre_es"].notna().all()
        assert sintomas["nombre_es"].is_unique

    def test_usado_en_modelo_coincide_con_los_casos_del_subconjunto(self, sintomas):
        assert set(sintomas["usado_en_modelo"]) <= {0, 1}
        assert ((sintomas["casos_subconjunto"] > 0) == (sintomas["usado_en_modelo"] == 1)).all()

    def test_la_columna_duplicada_del_csv_original_esta_presente(self, sintomas):
        assert {"regurgitation", "regurgitation.1"} <= set(sintomas["nombre_en"])


class TestLabelMap:
    def test_enfermedades_y_codigos_unicos(self, label_map):
        assert label_map["enfermedad_en"].is_unique
        assert label_map["cie10_codigo"].is_unique

    def test_codigos_cie10_de_tres_caracteres(self, label_map):
        assert label_map["cie10_codigo"].map(lambda c: bool(re.fullmatch(r"[A-Z]\d{2}", c))).all()

    def test_nombres_normalizados(self, label_map):
        assert (label_map["enfermedad_en"] == label_map["enfermedad_en"].map(normalizar_texto)).all()

    def test_tipo_de_mapeo_valido(self, label_map):
        assert set(label_map["tipo_mapeo"]) <= {"exacto", "amplio"}

    def test_todas_cumplen_el_minimo_de_casos(self, label_map):
        assert (label_map["casos_unicos"] >= CFG["data"]["min_unique_cases"]).all()

    def test_no_hay_campos_vacios(self, label_map):
        assert not label_map[["enfermedad_es", "cie10_codigo", "cie10_descripcion"]].isna().any().any()
