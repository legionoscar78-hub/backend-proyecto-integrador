from types import SimpleNamespace

import pytest

from app.ml import predictor as pred

ENFERMEDADES = "/api/v1/catalogo/enfermedades"
SINTOMAS = "/api/v1/catalogo/sintomas"


@pytest.fixture
def con_modelo(monkeypatch):
    """Un modelo falso que solo entiende 'tos' y 'fiebre' (basta con los nombres que expone)."""
    falso = SimpleNamespace(nombres_para_mostrar=["tos", "fiebre"])
    monkeypatch.setattr(pred, "_predictor", falso)
    monkeypatch.setattr(pred, "_error", None)


@pytest.fixture
def sin_modelo(monkeypatch):
    monkeypatch.setattr(pred, "_predictor", None)
    monkeypatch.setattr(pred, "_error", "Faltan o están vacíos: model.pt")


@pytest.mark.parametrize("ruta", [ENFERMEDADES, f"{ENFERMEDADES}/1", SINTOMAS])
def test_exige_sesion(api, ruta):
    assert api.cliente.get(ruta).status_code == 401


# ---------------------------------------------------------------- enfermedades

def test_listar_enfermedades_ordenadas_con_su_id_para_usarlo_en_consultas(api):
    h = api.medico()
    ids = {n: api.enfermedad(n, d) for n, d in [("sinusitis", "CIE-10 J01"), ("asma", None), ("bronquitis", None)]}
    r = api.cliente.get(ENFERMEDADES, headers=h).json()
    assert [e["nombre"] for e in r["items"]] == ["asma", "bronquitis", "sinusitis"]
    assert r["items"][2] == {"id": ids["sinusitis"], "nombre": "sinusitis", "descripcion": "CIE-10 J01"}
    assert (r["total"], r["limit"], r["offset"]) == (3, 20, 0)


def test_buscar_y_paginar_enfermedades(api):
    h = api.medico()
    for n in ["gripe común", "gripe aviar", "asma", "otitis"]:
        api.enfermedad(n)

    def nombres(**params):
        return [e["nombre"] for e in api.cliente.get(ENFERMEDADES, params=params, headers=h).json()["items"]]

    assert nombres(buscar="GRIPE") == ["gripe aviar", "gripe común"]
    assert nombres(buscar="gripe aviar") == ["gripe aviar"]
    assert nombres(buscar="gripe asma") == []
    assert nombres(buscar="%") == []
    assert nombres(limit=2, offset=1) == ["gripe aviar", "gripe común"]
    assert api.cliente.get(ENFERMEDADES, params={"limit": 0}, headers=h).status_code == 422


def test_detalle_de_enfermedad_con_sus_sintomas_y_cuales_entiende_el_modelo(api, con_modelo):
    h = api.medico()
    enf = api.enfermedad("gripe", "CIE-10 J11")
    for nombre in ["tos", "dolor de garganta", "fiebre"]:
        api.asociar(enf, api.sintoma(nombre))
    api.sintoma("sin relacion")  # existe en el catálogo pero no es de esta enfermedad

    r = api.cliente.get(f"{ENFERMEDADES}/{enf}", headers=h)
    assert r.status_code == 200
    cuerpo = r.json()
    assert (cuerpo["id"], cuerpo["nombre"], cuerpo["descripcion"]) == (enf, "gripe", "CIE-10 J11")
    assert [(s["nombre"], s["usado_por_el_modelo"]) for s in cuerpo["sintomas"]] == [
        ("dolor de garganta", False), ("fiebre", True), ("tos", True)]


def test_detalle_sin_modelo_marca_todos_como_no_usados(api, sin_modelo):
    h = api.medico()
    enf = api.enfermedad("gripe")
    api.asociar(enf, api.sintoma("tos"))
    r = api.cliente.get(f"{ENFERMEDADES}/{enf}", headers=h)
    assert r.status_code == 200 and r.json()["sintomas"][0]["usado_por_el_modelo"] is False


def test_detalle_de_enfermedad_inexistente(api):
    h = api.medico()
    assert api.cliente.get(f"{ENFERMEDADES}/999", headers=h).status_code == 404


# ---------------------------------------------------------------- síntomas

def test_listar_sintomas_ordenados_y_marcando_los_del_modelo(api, con_modelo):
    h = api.medico()
    for n in ["tos", "dolor de cabeza", "fiebre"]:
        api.sintoma(n)
    r = api.cliente.get(SINTOMAS, headers=h).json()
    assert [(s["nombre"], s["usado_por_el_modelo"]) for s in r["items"]] == [
        ("dolor de cabeza", False), ("fiebre", True), ("tos", True)]
    assert r["total"] == 3


def test_solo_modelo_filtra_y_cuenta_solo_esos(api, con_modelo):
    h = api.medico()
    for n in ["tos", "dolor de cabeza", "fiebre", "mareo"]:
        api.sintoma(n)
    r = api.cliente.get(SINTOMAS, params={"solo_modelo": True}, headers=h).json()
    assert [s["nombre"] for s in r["items"]] == ["fiebre", "tos"] and r["total"] == 2
    r = api.cliente.get(SINTOMAS, params={"solo_modelo": True, "buscar": "to"}, headers=h).json()
    assert [s["nombre"] for s in r["items"]] == ["tos"]


def test_solo_modelo_sin_modelo_da_503_pero_la_lista_normal_funciona(api, sin_modelo):
    h = api.medico()
    api.sintoma("tos")
    r = api.cliente.get(SINTOMAS, params={"solo_modelo": True}, headers=h)
    assert r.status_code == 503 and "model.pt" in r.json()["detail"]
    ok = api.cliente.get(SINTOMAS, headers=h).json()
    assert ok["total"] == 1 and ok["items"][0]["usado_por_el_modelo"] is False


def test_buscar_y_paginar_sintomas(api, con_modelo):
    h = api.medico()
    for n in ["dolor de cabeza", "dolor de garganta", "dolor de espalda", "tos"]:
        api.sintoma(n)
    r = api.cliente.get(SINTOMAS, params={"buscar": "dolor", "limit": 2, "offset": 1}, headers=h).json()
    assert [s["nombre"] for s in r["items"]] == ["dolor de espalda", "dolor de garganta"] and r["total"] == 3
