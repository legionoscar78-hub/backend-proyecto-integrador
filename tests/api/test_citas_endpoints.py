import pytest

from datos import dias

URL = "/api/v1/citas"


def _crear(api, headers, paciente_id, fecha=None, hora="10:00"):
    return api.cliente.post(URL, headers=headers, json={
        "paciente_id": paciente_id, "fecha_cita": fecha or dias(1), "hora_cita": hora})


@pytest.mark.parametrize("metodo, ruta", [
    ("post", URL), ("get", URL), ("get", f"{URL}/1"), ("patch", f"{URL}/1"), ("delete", f"{URL}/1"),
])
def test_todos_los_endpoints_exigen_sesion(api, metodo, ruta):
    cuerpo = {"json": {"paciente_id": 1, "fecha_cita": dias(1), "hora_cita": "10:00"}} if metodo in ("post", "patch") else {}
    assert getattr(api.cliente, metodo)(ruta, **cuerpo).status_code == 401


# ---------------------------------------------------------------- agendar

def test_agendar_devuelve_la_cita_con_el_paciente_y_el_medico_de_la_sesion(api):
    h = api.medico()
    p = api.paciente(h, 0)
    r = _crear(api, h, p["id"], fecha=dias(3), hora="09:30")
    assert r.status_code == 201
    assert r.json() == {"id": 1, "medico_id": 1, "fecha_cita": dias(3), "hora_cita": "09:30:00",
                        "paciente": {"id": p["id"], "nombre": p["nombre"], "apellidos": p["apellidos"]}}


def test_la_hora_se_guarda_sin_segundos(api):
    h = api.medico()
    p = api.paciente(h, 0)
    assert _crear(api, h, p["id"], hora="10:00:45").json()["hora_cita"] == "10:00:00"
    assert _crear(api, h, p["id"], hora="10:00:10").status_code == 409  # es el mismo horario


def test_se_puede_agendar_hoy_pero_no_en_el_pasado(api):
    h = api.medico()
    p = api.paciente(h, 0)
    assert _crear(api, h, p["id"], fecha=dias(0)).status_code == 201
    r = _crear(api, h, p["id"], fecha=dias(-1), hora="11:00")
    assert r.status_code == 422 and "pasada" in r.json()["detail"]


def test_paciente_inexistente_da_404(api):
    h = api.medico()
    r = _crear(api, h, 999)
    assert r.status_code == 404 and "paciente" in r.json()["detail"].lower()


def test_horario_ocupado_da_409_pero_otro_medico_puede_usarlo(api):
    ana, luis = api.medico("dra.ana"), api.medico("dr.luis")
    p = api.paciente(ana, 0)
    assert _crear(api, ana, p["id"]).status_code == 201
    r = _crear(api, ana, p["id"])
    assert r.status_code == 409 and "fecha y hora" in r.json()["detail"]
    assert _crear(api, luis, p["id"]).status_code == 201           # otro médico, mismo horario
    assert _crear(api, ana, p["id"], hora="10:01").status_code == 201  # mismo médico, otro minuto


@pytest.mark.parametrize("cuerpo", [
    {"paciente_id": 0, "fecha_cita": "2099-01-01", "hora_cita": "10:00"},
    {"paciente_id": "x", "fecha_cita": "2099-01-01", "hora_cita": "10:00"},
    {"paciente_id": 1, "fecha_cita": "mañana", "hora_cita": "10:00"},
    {"paciente_id": 1, "fecha_cita": "2099-01-01", "hora_cita": "25:00"},
    {"paciente_id": 1, "fecha_cita": "2099-01-01"},
    {"paciente_id": 1, "hora_cita": "10:00"},
    {},
])
def test_cuerpo_invalido_da_422(api, cuerpo):
    h = api.medico()
    assert api.cliente.post(URL, headers=h, json=cuerpo).status_code == 422


def test_dos_citas_simultaneas_al_mismo_horario_dan_409_y_la_sesion_sigue_sirviendo(api, monkeypatch):
    from app.repositories import cita_repo
    h = api.medico()
    p = api.paciente(h, 0)
    _crear(api, h, p["id"])
    monkeypatch.setattr(cita_repo, "horario_ocupado", lambda *a, **k: False)  # la comprobación no lo vio
    assert _crear(api, h, p["id"]).status_code == 409  # lo detiene la restricción UNIQUE de la BD
    monkeypatch.undo()
    assert _crear(api, h, p["id"], hora="12:00").status_code == 201


# ---------------------------------------------------------------- consultar

def test_listar_solo_muestra_las_citas_propias_ordenadas_por_fecha_y_hora(api):
    ana, luis = api.medico("dra.ana"), api.medico("dr.luis")
    p = api.paciente(ana, 0)
    api.cita(ana, p["id"], dias(2), "09:00")
    api.cita(ana, p["id"], dias(1), "16:00")
    api.cita(ana, p["id"], dias(1), "08:00")
    api.cita(luis, p["id"], dias(1), "08:00")

    citas = api.cliente.get(URL, headers=ana).json()
    assert citas["total"] == 3
    assert [(c["fecha_cita"], c["hora_cita"]) for c in citas["items"]] == [
        (dias(1), "08:00:00"), (dias(1), "16:00:00"), (dias(2), "09:00:00")]
    assert api.cliente.get(URL, headers=luis).json()["total"] == 1


def test_filtros_por_fecha_y_por_paciente(api):
    h = api.medico()
    a, b = api.paciente(h, 0), api.paciente(h, 1)
    api.cita(h, a["id"], dias(1), "08:00")
    api.cita(h, a["id"], dias(5), "08:00")
    api.cita(h, b["id"], dias(5), "09:00")

    def listar(**params):
        return api.cliente.get(URL, params=params, headers=h).json()

    assert listar(desde=dias(2))["total"] == 2
    assert listar(hasta=dias(2))["total"] == 1
    assert listar(desde=dias(5), hasta=dias(5))["total"] == 2            # un solo día
    assert listar(desde=dias(2), hasta=dias(4))["total"] == 0
    assert listar(paciente_id=b["id"])["total"] == 1
    assert listar(paciente_id=a["id"], desde=dias(2))["total"] == 1
    assert api.cliente.get(URL, params={"desde": dias(3), "hasta": dias(1)}, headers=h).status_code == 422


def test_paginacion(api):
    h = api.medico()
    p = api.paciente(h, 0)
    for hora in ("08:00", "09:00", "10:00", "11:00", "12:00"):
        api.cita(h, p["id"], hora=hora)
    pagina = api.cliente.get(URL, params={"limit": 2, "offset": 1}, headers=h).json()
    assert [c["hora_cita"] for c in pagina["items"]] == ["09:00:00", "10:00:00"]
    assert (pagina["total"], pagina["limit"], pagina["offset"]) == (5, 2, 1)
    assert api.cliente.get(URL, params={"limit": 101}, headers=h).status_code == 422


def test_una_cita_de_otro_medico_no_existe_para_mi(api):
    ana, luis = api.medico("dra.ana"), api.medico("dr.luis")
    p = api.paciente(ana, 0)
    cita = api.cita(ana, p["id"])
    assert api.cliente.get(f"{URL}/{cita['id']}", headers=ana).status_code == 200
    assert api.cliente.get(f"{URL}/{cita['id']}", headers=luis).status_code == 404
    assert api.cliente.patch(f"{URL}/{cita['id']}", headers=luis, json={"hora_cita": "11:00"}).status_code == 404
    assert api.cliente.delete(f"{URL}/{cita['id']}", headers=luis).status_code == 404
    assert api.cliente.get(f"{URL}/{cita['id']}", headers=ana).json()["hora_cita"] == "10:00:00"  # sin cambios


# ---------------------------------------------------------------- reprogramar

def test_reprogramar(api):
    h = api.medico()
    p = api.paciente(h, 0)
    cita = api.cita(h, p["id"])
    r = api.cliente.patch(f"{URL}/{cita['id']}", headers=h, json={"fecha_cita": dias(4), "hora_cita": "15:30:59"})
    assert r.status_code == 200
    assert (r.json()["fecha_cita"], r.json()["hora_cita"]) == (dias(4), "15:30:00")


def test_reprogramar_a_un_horario_ocupado_da_409_pero_no_choca_consigo_misma(api):
    h = api.medico()
    p = api.paciente(h, 0)
    api.cita(h, p["id"], dias(1), "10:00")
    otra = api.cita(h, p["id"], dias(1), "11:00")
    r = api.cliente.patch(f"{URL}/{otra['id']}", headers=h, json={"hora_cita": "10:00"})
    assert r.status_code == 409
    assert api.cliente.patch(f"{URL}/{otra['id']}", headers=h, json={"hora_cita": "11:00"}).status_code == 200
    assert api.cliente.patch(f"{URL}/{otra['id']}", headers=h, json={"fecha_cita": dias(1)}).status_code == 200


def test_cambiar_el_paciente_de_la_cita(api):
    h = api.medico()
    a, b = api.paciente(h, 0), api.paciente(h, 1)
    cita = api.cita(h, a["id"])
    r = api.cliente.patch(f"{URL}/{cita['id']}", headers=h, json={"paciente_id": b["id"]})
    assert r.status_code == 200 and r.json()["paciente"]["id"] == b["id"]
    assert api.cliente.patch(f"{URL}/{cita['id']}", headers=h, json={"paciente_id": 999}).status_code == 404


def test_reprogramar_al_pasado_o_con_datos_invalidos(api):
    h = api.medico()
    p = api.paciente(h, 0)
    cita = api.cita(h, p["id"])
    ruta = f"{URL}/{cita['id']}"
    assert api.cliente.patch(ruta, headers=h, json={"fecha_cita": dias(-2)}).status_code == 422
    for cuerpo in ({}, {"fecha_cita": None}, {"hora_cita": None}, {"paciente_id": None}, {"hora_cita": "99:99"}):
        assert api.cliente.patch(ruta, headers=h, json=cuerpo).status_code == 422, cuerpo
    assert api.cliente.patch(f"{URL}/999", headers=h, json={"hora_cita": "11:00"}).status_code == 404


# ---------------------------------------------------------------- cancelar

def test_cancelar_libera_el_horario(api):
    h = api.medico()
    p = api.paciente(h, 0)
    cita = api.cita(h, p["id"])
    assert api.cliente.delete(f"{URL}/{cita['id']}", headers=h).status_code == 204
    assert api.cliente.get(f"{URL}/{cita['id']}", headers=h).status_code == 404
    assert api.cliente.delete(f"{URL}/{cita['id']}", headers=h).status_code == 404
    assert _crear(api, h, p["id"]).status_code == 201  # el horario quedó libre


def test_tras_cancelar_todas_las_citas_el_paciente_se_puede_borrar(api):
    h = api.medico()
    p = api.paciente(h, 0)
    cita = api.cita(h, p["id"])
    assert api.cliente.delete(f"/api/v1/pacientes/{p['id']}", headers=h).status_code == 409
    api.cliente.delete(f"{URL}/{cita['id']}", headers=h)
    assert api.cliente.delete(f"/api/v1/pacientes/{p['id']}", headers=h).status_code == 204
