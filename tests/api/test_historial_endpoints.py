"""Historial de un paciente: cada médico ve solo sus propias consultas; las ajenas, solo con la llave."""
from datetime import datetime

import pytest

URL = "/api/v1/historial"
ACCESO = "/api/v1/consultas/acceso"


@pytest.fixture
def base(api):
    ana, luis = api.medico("dra.ana"), api.medico("dr.luis")
    return api, ana, luis, api.paciente(ana, 0), api.enfermedad("gripe"), api.enfermedad("asma")


def _ver(api, headers, paciente_id, **params):
    return api.cliente.get(f"{URL}/{paciente_id}", headers=headers, params=params)


def test_exige_sesion(api):
    assert api.cliente.get(f"{URL}/1").status_code == 401


def test_devuelve_el_paciente_y_sus_consultas_con_el_formato_de_pagina(base):
    api, ana, _, paciente, gripe, _ = base
    c = api.consulta(ana, paciente["id"], gripe, peso=70, notas="reposo")
    r = _ver(api, ana, paciente["id"])
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["paciente"] == paciente
    assert cuerpo["consultas"] == {"items": [c], "total": 1, "limit": 20, "offset": 0}


def test_paciente_sin_consultas_da_historial_vacio(base):
    api, ana, _, paciente, *_ = base
    r = _ver(api, ana, paciente["id"])
    assert r.status_code == 200 and r.json()["consultas"]["items"] == [] and r.json()["consultas"]["total"] == 0


def test_paciente_inexistente_da_404(base):
    api, ana, *_ = base
    assert _ver(api, ana, 999).status_code == 404


def test_cualquier_medico_puede_abrir_el_historial_de_cualquier_paciente(base):
    api, ana, luis, paciente, *_ = base
    r = _ver(api, luis, paciente["id"])  # el paciente lo registró Ana, pero Luis también lo ve
    assert r.status_code == 200 and r.json()["paciente"]["id"] == paciente["id"]


def test_el_medico_solo_ve_las_consultas_que_hizo_el_mismo(base):
    api, ana, luis, paciente, gripe, asma = base
    de_ana = api.consulta(ana, paciente["id"], gripe)
    de_luis = api.consulta(luis, paciente["id"], asma)

    assert [c["id"] for c in _ver(api, ana, paciente["id"]).json()["consultas"]["items"]] == [de_ana["id"]]
    assert [c["id"] for c in _ver(api, luis, paciente["id"]).json()["consultas"]["items"]] == [de_luis["id"]]


def test_las_consultas_de_otros_medicos_ni_se_listan_ni_se_cuentan(base):
    api, ana, luis, paciente, gripe, _ = base
    for _ in range(3):
        api.consulta(ana, paciente["id"], gripe)
    cuerpo = _ver(api, luis, paciente["id"]).json()
    assert cuerpo["consultas"]["total"] == 0 and cuerpo["consultas"]["items"] == []
    for dato in ["llave", "gripe"]:
        assert dato not in str(cuerpo["consultas"]).lower()


def test_la_consulta_de_otro_medico_se_abre_con_la_llave_y_no_aparece_en_el_historial(base):
    """El flujo del frontend: el historial muestra lo propio y un cuadro de texto abre la ajena con su llave."""
    api, ana, luis, paciente, gripe, _ = base
    ajena = api.consulta(ana, paciente["id"], gripe, notas="seguimiento en 15 días")

    assert _ver(api, luis, paciente["id"]).json()["consultas"]["total"] == 0
    abierta = api.cliente.post(ACCESO, headers=luis, json={"llave": ajena["llave"]})
    assert abierta.status_code == 200 and abierta.json()["id"] == ajena["id"]
    assert abierta.json()["paciente"]["id"] == paciente["id"]
    # abrirla con la llave no la agrega a su historial
    assert _ver(api, luis, paciente["id"]).json()["consultas"]["total"] == 0


def test_solo_cuenta_los_de_ese_paciente(base):
    api, ana, _, paciente, gripe, _ = base
    otro = api.paciente(ana, 1)
    api.consulta(ana, paciente["id"], gripe)
    api.consulta(ana, otro["id"], gripe)
    assert _ver(api, ana, paciente["id"]).json()["consultas"]["total"] == 1
    assert _ver(api, ana, otro["id"]).json()["consultas"]["total"] == 1


def test_orden_de_la_mas_reciente_a_la_mas_antigua_y_paginacion(base):
    api, ana, _, paciente, gripe, _ = base
    ids = []
    for mes in (1, 2, 3):
        c = api.consulta(ana, paciente["id"], gripe)
        api.fechar(c["id"], datetime(2025, mes, 10, 8, 0))
        ids.append(c["id"])
    pagina1 = _ver(api, ana, paciente["id"], limit=2).json()["consultas"]
    assert [c["id"] for c in pagina1["items"]] == [ids[2], ids[1]] and pagina1["total"] == 3
    pagina2 = _ver(api, ana, paciente["id"], limit=2, offset=2).json()["consultas"]
    assert [c["id"] for c in pagina2["items"]] == [ids[0]]


def test_filtra_por_fechas_con_los_limites_incluidos(base):
    api, ana, _, paciente, gripe, _ = base
    ids = {}
    for dia in (9, 10, 20, 21):
        c = api.consulta(ana, paciente["id"], gripe)
        api.fechar(c["id"], datetime(2025, 3, dia, 23, 59))
        ids[dia] = c["id"]
    r = _ver(api, ana, paciente["id"], desde="2025-03-10", hasta="2025-03-20").json()["consultas"]
    assert sorted(c["id"] for c in r["items"]) == [ids[10], ids[20]] and r["total"] == 2


@pytest.mark.parametrize("params", [
    {"desde": "2025-03-20", "hasta": "2025-03-10"}, {"limit": 0}, {"limit": 101}, {"offset": -1}, {"desde": "no-es-fecha"},
])
def test_parametros_invalidos_dan_422(base, params):
    api, ana, _, paciente, *_ = base
    assert _ver(api, ana, paciente["id"], **params).status_code == 422


def test_id_que_no_es_numero_da_422(base):
    api, ana, *_ = base
    assert api.cliente.get(f"{URL}/abc", headers=ana).status_code == 422
