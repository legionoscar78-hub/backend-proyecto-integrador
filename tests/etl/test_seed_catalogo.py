"""Lectura del catálogo para scripts/seed_catalogo.py (sin base de datos). La carga a Postgres
se probó contra el esquema real de Alembic; aquí se cubre la lógica de nombres y relaciones."""
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

RUTA = Path(__file__).resolve().parents[2] / "scripts" / "seed_catalogo.py"
spec = importlib.util.spec_from_file_location("seed_catalogo", RUTA)
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


@pytest.fixture
def archivos(tmp_path):
    """Dataset de juguete: 3 enfermedades (2 con traducción) y 4 síntomas (uno sin ninguna enfermedad)."""
    csv = tmp_path / "datos.csv"
    pd.DataFrame({
        "diseases": ["Flu ", "flu", "common cold", "Rare Thing"],
        "Fever ": [1, 0, 0, 0],
        "cough": [0, 1, 1, 0],
        "sore  throat": [0, 0, 1, 1],
        "rash": [0, 0, 0, 0],
    }).to_csv(csv, index=False)
    mappings = tmp_path / "mappings"
    mappings.mkdir()
    pd.DataFrame({
        "orden": range(4),
        "nombre_en": ["fever", "cough", "sore throat", "rash"],
        "nombre_es": ["fiebre", "tos", "dolor de garganta", "sarpullido"],
    }).to_csv(mappings / "sintomas.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame({
        "enfermedad_en": ["flu", "common cold"],
        "enfermedad_es": ["influenza (gripe)", "resfriado común"],
        "cie10_codigo": ["J11", "J00"],
        "cie10_descripcion": ["Influenza, virus not identified", "Acute nasopharyngitis"],
    }).to_csv(mappings / "label_map.csv", index=False, encoding="utf-8-sig")
    return csv, mappings


def test_los_sintomas_se_guardan_en_espanol_en_el_orden_del_csv(archivos):
    cat = seed.leer_catalogo(*archivos)
    assert cat.sintomas == ["fiebre", "tos", "dolor de garganta", "sarpullido"]


def test_enfermedades_en_espanol_si_hay_traduccion_y_en_ingles_si_no(archivos):
    cat = seed.leer_catalogo(*archivos)
    assert set(cat.enfermedades) == {"influenza (gripe)", "resfriado común", "rare thing"}
    assert cat.enfermedades_traducidas == 2


def test_descripcion_con_codigo_cie10_solo_para_las_del_modelo(archivos):
    cat = seed.leer_catalogo(*archivos)
    assert cat.descripciones == {
        "influenza (gripe)": "CIE-10 J11: Influenza, virus not identified",
        "resfriado común": "CIE-10 J00: Acute nasopharyngitis",
    }


def test_relaciones_usan_los_nombres_de_la_bd_y_unen_variantes_del_mismo_nombre(archivos):
    cat = seed.leer_catalogo(*archivos)
    assert sorted(cat.pares) == sorted([
        ("influenza (gripe)", "fiebre"), ("influenza (gripe)", "tos"),  # "Flu " y "flu" son la misma enfermedad
        ("resfriado común", "tos"), ("resfriado común", "dolor de garganta"),
        ("rare thing", "dolor de garganta"),
    ])
    assert cat.sintomas_sin_enfermedad == ["sarpullido"]


def test_falla_si_sintomas_csv_no_coincide_con_el_dataset(archivos):
    csv, mappings = archivos
    sv = pd.read_csv(mappings / "sintomas.csv", encoding="utf-8-sig")
    sv.loc[0, "nombre_en"] = "otro"
    sv.to_csv(mappings / "sintomas.csv", index=False, encoding="utf-8-sig")
    with pytest.raises(ValueError, match="sintomas.csv"):
        seed.leer_catalogo(csv, mappings)


def test_falla_si_dos_nombres_en_espanol_se_repiten(archivos):
    csv, mappings = archivos
    sv = pd.read_csv(mappings / "sintomas.csv", encoding="utf-8-sig")
    sv.loc[1, "nombre_es"] = "fiebre"
    sv.to_csv(mappings / "sintomas.csv", index=False, encoding="utf-8-sig")
    with pytest.raises(ValueError, match="repetidos"):
        seed.leer_catalogo(csv, mappings)


def test_falla_si_el_nombre_supera_el_largo_de_la_columna(archivos):
    csv, mappings = archivos
    sv = pd.read_csv(mappings / "sintomas.csv", encoding="utf-8-sig")
    sv.loc[0, "nombre_es"] = "x" * 151
    sv.to_csv(mappings / "sintomas.csv", index=False, encoding="utf-8-sig")
    with pytest.raises(ValueError, match="150"):
        seed.leer_catalogo(csv, mappings)


def test_falla_si_label_map_tiene_una_enfermedad_que_no_esta_en_el_dataset(archivos):
    csv, mappings = archivos
    lm = pd.read_csv(mappings / "label_map.csv", encoding="utf-8-sig")
    lm.loc[0, "enfermedad_en"] = "no existe"
    lm.to_csv(mappings / "label_map.csv", index=False, encoding="utf-8-sig")
    with pytest.raises(ValueError, match="no existe"):
        seed.leer_catalogo(csv, mappings)


def test_falla_si_una_traduccion_choca_con_el_nombre_ingles_de_otra_enfermedad(archivos):
    csv, mappings = archivos
    lm = pd.read_csv(mappings / "label_map.csv", encoding="utf-8-sig")
    lm.loc[0, "enfermedad_es"] = "rare thing"  # ya es el nombre (en inglés) de otra enfermedad
    lm.to_csv(mappings / "label_map.csv", index=False, encoding="utf-8-sig")
    with pytest.raises(ValueError, match="repetidos"):
        seed.leer_catalogo(csv, mappings)
