import numpy as np
import pandas as pd
import pytest

from ml_pipeline.etl.transform import COL_CLASE, COL_SPLIT, ErrorDeDatos, transformar

# Nombres "sucios" a propósito: el ETL debe normalizarlos
COLUMNAS = ["Fever ", "cough", "Sore  Throat", "rash", "headache", "nausea"]
LIMPIOS = ["fever", "cough", "sore throat", "rash", "headache", "nausea"]
PARAMS = dict(min_casos=20, val_size=0.15, test_size=0.15, seed=7)


def _dataset(nausea_con_casos=False):
    rng = np.random.default_rng(0)
    bloques = []
    for enfermedad, probs in {
        "FLU ": [0.8, 0.7, 0.3, 0.1, 0.5, 0.0],
        "common cold": [0.3, 0.8, 0.8, 0.1, 0.2, 0.0],
        "migraine": [0.2, 0.3, 0.3, 0.3, 0.7, 0.0],
        "otra enfermedad": [0.5, 0.5, 0.5, 0.5, 0.5, 0.0],  # fuera de label_map
    }.items():
        datos = (rng.random((400, 6)) < probs).astype("int8")
        bloque = pd.DataFrame(datos, columns=COLUMNAS)
        bloque.insert(0, "diseases", enfermedad)
        bloques.append(bloque)
    df = pd.concat(bloques, ignore_index=True)
    df = df[df[COLUMNAS].sum(axis=1) > 0]
    if nausea_con_casos:
        df.loc[df.index[:50], "nausea"] = 1
    return pd.concat([df, df.iloc[[0, 1]]], ignore_index=True)  # 2 duplicados exactos extra


@pytest.fixture
def label_map():
    return pd.DataFrame({
        "enfermedad_en": ["flu", "common cold", "migraine"],
        "enfermedad_es": ["gripe", "resfriado", "migraña"],
        "cie10_codigo": ["J11", "J00", "G43"],
    })


@pytest.fixture
def sintomas():
    # nausea queda fuera del modelo (usado_en_modelo = 0)
    return pd.DataFrame({
        "orden": range(6),
        "nombre_en": COLUMNAS,
        "usado_en_modelo": [1, 1, 1, 1, 1, 0],
    })


@pytest.fixture
def resultado(label_map, sintomas):
    return transformar(_dataset(), label_map, sintomas, **PARAMS)


def test_normaliza_nombres_y_respeta_el_orden_de_sintomas_csv(resultado):
    assert resultado.vocabulario == LIMPIOS[:5]
    assert list(resultado.datos.columns[:5]) == LIMPIOS[:5]


def test_deja_solo_las_enfermedades_del_label_map(resultado):
    assert set(resultado.datos["enfermedad_en"]) == {"flu", "common cold", "migraine"}


def test_elimina_duplicados_exactos(resultado):
    columnas = resultado.vocabulario + ["enfermedad_en"]
    assert not resultado.datos.duplicated(subset=columnas).any()
    assert resultado.reporte["duplicados_eliminados"] > 0
    assert resultado.reporte["filas_finales"] == len(resultado.datos)


def test_las_clases_siguen_el_orden_del_codigo_cie10(resultado):
    assert [c["cie10_codigo"] for c in resultado.clases] == ["G43", "J00", "J11"]
    assert [c["indice"] for c in resultado.clases] == [0, 1, 2]
    esperado = {c["enfermedad_en"]: c["indice"] for c in resultado.clases}
    assert (resultado.datos["enfermedad_en"].map(esperado) == resultado.datos[COL_CLASE]).all()


def test_los_sintomas_son_uint8_0_o_1(resultado):
    sintomas = resultado.datos[resultado.vocabulario]
    assert (sintomas.dtypes == "uint8").all()
    assert set(np.unique(sintomas.values)) <= {0, 1}


def test_split_reparte_70_15_15_por_clase(resultado):
    datos = resultado.datos
    assert set(datos[COL_SPLIT]) == {"train", "val", "test"}
    proporciones = datos[COL_SPLIT].value_counts(normalize=True)
    assert proporciones["train"] == pytest.approx(0.70, abs=0.02)
    assert proporciones["val"] == pytest.approx(0.15, abs=0.02)
    assert proporciones["test"] == pytest.approx(0.15, abs=0.02)
    por_clase = datos.groupby(COL_CLASE)[COL_SPLIT].value_counts(normalize=True).unstack()
    assert por_clase["test"].between(0.12, 0.18).all()


def test_ninguna_fila_esta_en_train_y_en_test(resultado):
    datos = resultado.datos
    sintomas = datos[resultado.vocabulario].to_numpy(dtype="uint8")
    split = datos[COL_SPLIT].to_numpy()
    llaves = [(fila.tobytes(), clase) for fila, clase in zip(sintomas, datos[COL_CLASE].to_numpy())]
    train = {k for k, s in zip(llaves, split) if s == "train"}
    test = {k for k, s in zip(llaves, split) if s == "test"}
    assert not train & test


def test_el_split_es_reproducible_y_depende_de_la_semilla(label_map, sintomas):
    a = transformar(_dataset(), label_map, sintomas, **PARAMS)
    b = transformar(_dataset(), label_map, sintomas, **PARAMS)
    c = transformar(_dataset(), label_map, sintomas, **{**PARAMS, "seed": 8})
    assert a.datos[COL_SPLIT].tolist() == b.datos[COL_SPLIT].tolist()
    assert a.datos[COL_SPLIT].tolist() != c.datos[COL_SPLIT].tolist()


def test_un_sintoma_del_vocabulario_sin_casos_se_reporta(label_map, sintomas):
    sintomas.loc[sintomas["nombre_en"] == "nausea", "usado_en_modelo"] = 1
    res = transformar(_dataset(), label_map, sintomas, **PARAMS)
    assert res.reporte["sintomas_del_vocabulario_sin_casos"] == ["nausea"]


def test_falla_si_un_sintoma_con_casos_no_esta_en_el_vocabulario(label_map, sintomas):
    with pytest.raises(ErrorDeDatos, match="nausea"):
        transformar(_dataset(nausea_con_casos=True), label_map, sintomas, **PARAMS)


def test_falla_si_una_enfermedad_del_label_map_no_esta_en_el_dataset(label_map, sintomas):
    label_map.loc[0, "enfermedad_en"] = "no existe"
    with pytest.raises(ErrorDeDatos, match="no existe"):
        transformar(_dataset(), label_map, sintomas, **PARAMS)


def test_falla_si_una_enfermedad_tiene_pocos_casos(label_map, sintomas):
    with pytest.raises(ErrorDeDatos, match="menos de"):
        transformar(_dataset(), label_map, sintomas, **{**PARAMS, "min_casos": 10_000})


def test_falla_si_sintomas_csv_no_coincide_con_el_dataset(label_map, sintomas):
    sintomas.loc[0, "nombre_en"] = "otro sintoma"
    with pytest.raises(ErrorDeDatos, match="sintomas.csv"):
        transformar(_dataset(), label_map, sintomas, **PARAMS)


def test_falla_con_codigos_cie10_repetidos(label_map, sintomas):
    label_map.loc[1, "cie10_codigo"] = "J11"
    with pytest.raises(ErrorDeDatos, match="repetidos"):
        transformar(_dataset(), label_map, sintomas, **PARAMS)
