from datetime import date

import pytest

from datos import curp, dias, paciente_json

URL = "/api/v1/pacientes"


def _edad(nacimiento: date) -> int:
    hoy = date.today()
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))


# ---------------------------------------------------------------- sesión

@pytest.mark.parametrize("metodo, ruta", [
    ("post", URL), ("get", URL), ("get", f"{URL}/1"), ("patch", f"{URL}/1"), ("delete", f"{URL}/1"),
])
def test_todos_los_endpoints_exigen_sesion(api, metodo, ruta):
    r = getattr(api.cliente, metodo)(ruta, **({"json": paciente_json()} if metodo in ("post", "patch") else {}))
    assert r.status_code == 401


# ---------------------------------------------------------------- crear

def test_crear_normaliza_curp_y_telefono_y_calcula_la_edad(api):
    h = api.medico()
    r = api.cliente.post(URL, headers=h, json=paciente_json(
        curp=curp(0).lower(), numero_telefonico=" (443) 123-4567 ", nombre="  Luis  "))
    assert r.status_code == 201
    p = r.json()
    assert p["curp"] == curp(0) and p["numero_telefonico"] == "4431234567" and p["nombre"] == "Luis"
    assert p["edad"] == _edad(date(1990, 5, 17)) and p["id"] == 1
    assert set(p) == {"id", "nombre", "apellidos", "curp", "fecha_nacimiento", "edad", "numero_telefonico",
                      "sexo", "tipo_de_sangre", "notas"}


def test_los_campos_opcionales_pueden_faltar(api):
    h = api.medico()
    minimo = {k: v for k, v in paciente_json().items() if k not in ("numero_telefonico", "tipo_de_sangre", "notas")}
    r = api.cliente.post(URL, headers=h, json=minimo)
    assert r.status_code == 201
    assert r.json()["numero_telefonico"] is None and r.json()["tipo_de_sangre"] is None and r.json()["notas"] is None


def test_curp_repetida_da_409_aunque_cambien_las_mayusculas(api):
    h = api.medico()
    api.paciente(h, 0)
    r = api.cliente.post(URL, headers=h, json=paciente_json(1, curp=curp(0).lower()))
    assert r.status_code == 409 and "CURP" in r.json()["detail"]


@pytest.mark.parametrize("cambios", [
    {"curp": "ABC"},
    {"curp": "A" * 18},
    {"curp": curp(0)[:-1] + "X"},          # el último carácter debe ser dígito
    {"curp": curp(0)[:10] + "X" + curp(0)[11:]},  # el sexo debe ser H o M
    {"fecha_nacimiento": dias(1)},
    {"fecha_nacimiento": "1899-12-31"},
    {"fecha_nacimiento": "no-es-fecha"},
    {"sexo": "X"},
    {"sexo": "h"},
    {"tipo_de_sangre": "C+"},
    {"tipo_de_sangre": "o+"},
    {"numero_telefonico": "123"},
    {"numero_telefonico": "1" * 16},
    {"numero_telefonico": "telefono"},
    {"nombre": "   "},
    {"nombre": "x" * 101},
    {"apellidos": "x" * 151},
    {"notas": "x" * 5001},
])
def test_datos_invalidos_dan_422(api, cambios):
    h = api.medico()
    assert api.cliente.post(URL, headers=h, json=paciente_json(**cambios)).status_code == 422


def test_faltan_campos_obligatorios(api):
    h = api.medico()
    for campo in ("nombre", "apellidos", "curp", "fecha_nacimiento", "sexo"):
        datos = {k: v for k, v in paciente_json().items() if k != campo}
        assert api.cliente.post(URL, headers=h, json=datos).status_code == 422, campo


def test_curp_repetida_en_condicion_de_carrera_tambien_da_409(api, monkeypatch):
    from app.repositories import paciente_repo
    h = api.medico()
    api.paciente(h, 0)
    monkeypatch.setattr(paciente_repo, "obtener_por_curp", lambda db, c: None)  # no ve al duplicado
    assert api.cliente.post(URL, headers=h, json=paciente_json(1, curp=curp(0))).status_code == 409
    monkeypatch.undo()
    assert api.cliente.post(URL, headers=h, json=paciente_json(1)).status_code == 201  # la sesión sigue sirviendo


# ---------------------------------------------------------------- consultar

def test_obtener_y_404(api):
    h = api.medico()
    creado = api.paciente(h, 0)
    assert api.cliente.get(f"{URL}/{creado['id']}", headers=h).json() == creado
    assert api.cliente.get(f"{URL}/999", headers=h).status_code == 404
    assert api.cliente.get(f"{URL}/abc", headers=h).status_code == 422


def test_el_directorio_es_compartido_entre_medicos(api):
    ana, luis = api.medico("dra.ana"), api.medico("dr.luis")
    creado = api.paciente(ana, 0)
    assert api.cliente.get(f"{URL}/{creado['id']}", headers=luis).status_code == 200


def test_listar_pagina_y_ordena_por_apellidos(api):
    h = api.medico()
    for n, apellido in enumerate(["Zamora", "Alvarez", "Mora", "Bravo", "Castro"]):
        api.paciente(h, n, apellidos=apellido)
    todos = api.cliente.get(URL, headers=h).json()
    assert todos["total"] == 5 and [p["apellidos"] for p in todos["items"]] == [
        "Alvarez", "Bravo", "Castro", "Mora", "Zamora"]
    pagina = api.cliente.get(URL, params={"limit": 2, "offset": 2}, headers=h).json()
    assert [p["apellidos"] for p in pagina["items"]] == ["Castro", "Mora"]
    assert (pagina["total"], pagina["limit"], pagina["offset"]) == (5, 2, 2)
    assert api.cliente.get(URL, params={"offset": 10}, headers=h).json()["items"] == []


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"buscar": "x" * 101}])
def test_parametros_de_lista_invalidos(api, params):
    h = api.medico()
    assert api.cliente.get(URL, params=params, headers=h).status_code == 422


def test_buscar_por_nombre_apellido_o_curp_sin_distinguir_mayusculas(api):
    h = api.medico()
    api.paciente(h, 0, nombre="María", apellidos="López Ruiz")
    api.paciente(h, 1, nombre="Luis", apellidos="Mora Pérez")

    def buscar(texto):
        return [p["nombre"] for p in api.cliente.get(URL, params={"buscar": texto}, headers=h).json()["items"]]

    assert buscar("lópez") == ["María"]
    assert buscar("LUIS") == ["Luis"]
    assert buscar(curp(1)[:6].lower()) == ["Luis"]
    assert buscar("mora luis") == ["Luis"]        # todas las palabras deben coincidir
    assert buscar("mora maría") == []
    assert sorted(buscar("   ")) == ["Luis", "María"]  # búsqueda vacía = sin filtro


def test_los_comodines_de_like_se_buscan_como_texto(api):
    h = api.medico()
    api.paciente(h, 0, nombre="Ana")
    assert api.cliente.get(URL, params={"buscar": "%"}, headers=h).json()["total"] == 0
    assert api.cliente.get(URL, params={"buscar": "_"}, headers=h).json()["total"] == 0
    assert api.cliente.get(URL, params={"buscar": "A_a"}, headers=h).json()["total"] == 0


# ---------------------------------------------------------------- actualizar

def test_patch_cambia_solo_lo_enviado(api):
    h = api.medico()
    antes = api.paciente(h, 0)
    r = api.cliente.patch(f"{URL}/{antes['id']}", headers=h, json={"nombre": "Nuevo", "tipo_de_sangre": "AB-"})
    assert r.status_code == 200
    assert r.json() == {**antes, "nombre": "Nuevo", "tipo_de_sangre": "AB-"}


def test_patch_con_null_borra_los_campos_opcionales(api):
    h = api.medico()
    p = api.paciente(h, 0)
    r = api.cliente.patch(f"{URL}/{p['id']}", headers=h,
                          json={"numero_telefonico": None, "tipo_de_sangre": None, "notas": None})
    assert r.status_code == 200
    assert (r.json()["numero_telefonico"], r.json()["tipo_de_sangre"], r.json()["notas"]) == (None, None, None)


@pytest.mark.parametrize("cuerpo", [
    {"nombre": None}, {"curp": None}, {"sexo": None}, {"fecha_nacimiento": None}, {}, {"sexo": "X"}, {"curp": "mala"},
])
def test_patch_invalido_da_422(api, cuerpo):
    h = api.medico()
    p = api.paciente(h, 0)
    assert api.cliente.patch(f"{URL}/{p['id']}", headers=h, json=cuerpo).status_code == 422


def test_patch_de_curp_a_una_que_ya_existe_da_409_pero_la_propia_se_acepta(api):
    h = api.medico()
    a, b = api.paciente(h, 0), api.paciente(h, 1)
    assert api.cliente.patch(f"{URL}/{b['id']}", headers=h, json={"curp": a["curp"]}).status_code == 409
    assert api.cliente.patch(f"{URL}/{b['id']}", headers=h, json={"curp": b["curp"].lower()}).status_code == 200
    assert api.cliente.patch(f"{URL}/{b['id']}", headers=h, json={"curp": curp(50)}).json()["curp"] == curp(50)


def test_patch_de_un_paciente_inexistente(api):
    h = api.medico()
    assert api.cliente.patch(f"{URL}/999", headers=h, json={"nombre": "x"}).status_code == 404


# ---------------------------------------------------------------- eliminar

def test_eliminar_paciente_sin_registros(api):
    h = api.medico()
    p = api.paciente(h, 0)
    assert api.cliente.delete(f"{URL}/{p['id']}", headers=h).status_code == 204
    assert api.cliente.get(f"{URL}/{p['id']}", headers=h).status_code == 404
    assert api.cliente.delete(f"{URL}/{p['id']}", headers=h).status_code == 404


def test_no_se_borra_un_paciente_con_citas(api):
    h = api.medico()
    p = api.paciente(h, 0)
    api.cita(h, p["id"])
    r = api.cliente.delete(f"{URL}/{p['id']}", headers=h)
    assert r.status_code == 409 and "citas o consultas" in r.json()["detail"]
    assert api.cliente.get(f"{URL}/{p['id']}", headers=h).status_code == 200
