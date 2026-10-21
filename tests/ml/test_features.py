import json

import pytest

from app.ml.features import (
    SintomaDesconocido,
    cargar_vocabulario,
    normalizar_texto,
    vectorizar_sintomas,
)

VOCAB = ["fever", "cough", "sore throat", "headache"]


class TestNormalizarTexto:
    def test_minusculas_y_espacios(self):
        assert normalizar_texto("  Sore   THROAT ") == "sore throat"

    def test_quita_acentos(self):
        assert normalizar_texto("Náuseas") == "nauseas"

    def test_es_idempotente(self):
        una_vez = normalizar_texto("  Dolor  de CABEZA ")
        assert normalizar_texto(una_vez) == una_vez

    def test_conserva_el_sufijo_de_columnas_duplicadas(self):
        assert normalizar_texto("regurgitation.1") == "regurgitation.1"


class TestVectorizarSintomas:
    def test_marca_los_presentes_en_el_orden_del_vocabulario(self):
        assert vectorizar_sintomas(["headache", "fever"], VOCAB) == [1, 0, 0, 1]

    def test_el_orden_de_entrada_no_importa(self):
        assert vectorizar_sintomas(["cough", "fever"], VOCAB) == vectorizar_sintomas(["fever", "cough"], VOCAB)

    def test_repetidos_no_suman(self):
        assert vectorizar_sintomas(["fever", "fever"], VOCAB) == [1, 0, 0, 0]

    def test_normaliza_la_entrada(self):
        assert vectorizar_sintomas(["  SORE   Throat"], VOCAB) == [0, 0, 1, 0]

    def test_sin_sintomas_da_ceros(self):
        assert vectorizar_sintomas([], VOCAB) == [0, 0, 0, 0]

    def test_longitud_igual_al_vocabulario(self):
        assert len(vectorizar_sintomas(["fever"], VOCAB)) == len(VOCAB)

    def test_sintoma_desconocido_falla_por_defecto(self):
        with pytest.raises(SintomaDesconocido) as error:
            vectorizar_sintomas(["fever", "dolor raro"], VOCAB)
        assert error.value.sintomas == ["dolor raro"]

    def test_modo_no_estricto_ignora_los_desconocidos(self):
        assert vectorizar_sintomas(["fever", "dolor raro"], VOCAB, estricto=False) == [1, 0, 0, 0]


class TestCargarVocabulario:
    def test_lee_la_lista(self, tmp_path):
        archivo = tmp_path / "symptoms.json"
        archivo.write_text(json.dumps(VOCAB), encoding="utf-8")
        assert cargar_vocabulario(archivo) == VOCAB

    def test_rechaza_algo_que_no_es_una_lista_de_textos(self, tmp_path):
        archivo = tmp_path / "symptoms.json"
        archivo.write_text(json.dumps({"fever": 0}), encoding="utf-8")
        with pytest.raises(ValueError):
            cargar_vocabulario(archivo)

    def test_rechaza_repetidos(self, tmp_path):
        archivo = tmp_path / "symptoms.json"
        archivo.write_text(json.dumps(["fever", "fever"]), encoding="utf-8")
        with pytest.raises(ValueError, match="repetidos"):
            cargar_vocabulario(archivo)

    def test_un_archivo_vacio_falla_en_vez_de_dar_un_vocabulario_vacio(self, tmp_path):
        archivo = tmp_path / "symptoms.json"
        archivo.write_text("", encoding="utf-8")
        with pytest.raises(ValueError):
            cargar_vocabulario(archivo)
