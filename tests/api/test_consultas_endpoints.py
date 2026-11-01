import re
from datetime import date, datetime

import pytest

from app.services import consulta_service
from app.services.consulta_service import ALFABETO_LLAVE, normalizar_llave, nueva_llave
from datos import dias

URL = "/api/v1/consultas"
ACCESO = f"{URL}/acceso"
PATRON_LLAVE = re.compile(rf"^[{ALFABETO_LLAVE}]{{4}}(-[{ALFABETO_LLAVE}]{{4}}){{3}}$")


def _edad(nacimiento: date) -> int:
    hoy = date.today()
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))


@pytest.fixture
def base(api):
    """Un médico con sesión, un paciente (nacido el 1990-05-17) y una enfermedad del catálogo."""
    h = api.medico("dra.ana")
    return api, h, api.paciente(h, 0), api.enfermedad("gripe")


# ---------------------------------------------------------------- la llave

def test_la_llave_tiene_formato_legible_y_no_usa_caracteres_ambiguos():
    for _ in range(200):
        llave = nueva_llave()
        assert PATRON_LLAVE.fullmatch(llave), llave
        assert not set("01ILO") & set(llave)


def test_las_llaves_no_se_repiten():
    assert len({nueva_llave() for _ in range(5000)}) == 5000


@pytest.mark.parametrize("escrita", [
    "K7QM-2XW9-HP4T-R8ZD", "k7qm-2xw9-hp4t-r8zd", "K7QM 2XW9 HP4T R8ZD", "k7qm2xw9hp4tr8zd", "  K7QM-2XW9-HP4T-R8ZD\n",
])
def test_normalizar_llave_acepta_las_formas_en_que_se_escribe(escrita):
    assert normalizar_llave(escrita) == "K7QM-2XW9-HP4T-R8ZD"


@pytest.mark.parametrize("mala", ["", "abc", "K7QM-2XW9-HP4T", "K7QM-2XW9-HP4T-R8ZD-XXXX"])
def test_normalizar_llave_deja_pasar_lo_que_no_puede_coincidir(mala):
    assert not PATRON_LLAVE.fullmatch(normalizar_llave(mala))


# ---------------------------------------------------------------- sesión

@pytest.mark.parametrize("metodo, ruta", [
    ("post", URL), ("get", URL), ("get", f"{URL}/1"), ("patch", f"{URL}/1"), ("post", ACCESO),
])
def test_todos_los_endpoints_exigen_sesion(api, metodo, ruta):
    cuerpo = {"json": {"paciente_id": 1, "enfermedad_id": 1, "llave": "K7QM-2XW9-HP4T-R8ZD"}} if metodo in ("post", "patch") else {}
    assert getattr(api.cliente, metodo)(ruta, **cuerpo).status_code == 401


# ---------------------------------------------------------------- registrar

def test_registrar_calcula_la_edad_genera_la_llave_y_devuelve_el_detalle(base):
    api, h, paciente, enf = base
    r = api.cliente.post(URL, headers=h, json={
        "paciente_id": paciente["id"], "enfermedad_id": enf, "peso": 70.5, "altura": 1.72, "notas": "  reposo  "})
    assert r.status_code == 201
    c = r.json()
    assert PATRON_LLAVE.fullmatch(c["llave"])
    assert (c["id"], c["medico_id"], c["edad"]) == (1, 1, _edad(date(1990, 5, 17)))
    assert (c["peso"], c["altura"], c["notas"]) == (70.5, 1.72, "reposo")
    assert c["paciente"] == {"id": paciente["id"], "nombre": paciente["nombre"], "apellidos": paciente["apellidos"]}
    assert c["enfermedad"] == {"id": enf, "nombre": "gripe"}
    assert datetime.fromisoformat(c["fecha_consulta"]).date() == date.today()


def test_peso_altura_y_notas_son_opcionales(base):
    api, h, paciente, enf = base
    c = api.consulta(h, paciente["id"], enf)
    assert (c["peso"], c["altura"], c["notas"]) == (None, None, None)


def test_la_edad_que_envie_el_cliente_se_ignora(base):
    api, h, paciente, enf = base
    c = api.consulta(h, paciente["id"], enf, edad=5)
    assert c["edad"] == _edad(date(1990, 5, 17))


def test_cada_consulta_tiene_su_propia_llave(base):
    api, h, paciente, enf = base
    assert api.consulta(h, paciente["id"], enf)["llave"] != api.consulta(h, paciente["id"], enf)["llave"]


def test_paciente_o_enfermedad_inexistente_dan_404(base):
    api, h, paciente, enf = base
    r = api.cliente.post(URL, headers=h, json={"paciente_id": 999, "enfermedad_id": enf})
    assert r.status_code == 404 and "paciente" in r.json()["detail"]
    r = api.cliente.post(URL, headers=h, json={"paciente_id": paciente["id"], "enfermedad_id": 999})
    assert r.status_code == 404 and "enfermedad" in r.json()["detail"]


@pytest.mark.parametrize("cambios", [
    {"paciente_id": 0}, {"enfermedad_id": 0}, {"paciente_id": "x"},
    {"peso": 0}, {"peso": -3}, {"peso": 500.01}, {"peso": 70.123}, {"peso": "pesado"},
    {"altura": 0}, {"altura": 2.51}, {"altura": 172}, {"altura": 1.723},
    {"notas": "x" * 5001},
])
def test_datos_invalidos_dan_422(base, cambios):
    api, h, paciente, enf = base
    cuerpo = {"paciente_id": paciente["id"], "enfermedad_id": enf, **cambios}
    assert api.cliente.post(URL, headers=h, json=cuerpo).status_code == 422


def test_faltan_campos_obligatorios(base):
    api, h, paciente, enf = base
    assert api.cliente.post(URL, headers=h, json={"enfermedad_id": enf}).status_code == 422
    assert api.cliente.post(URL, headers=h, json={"paciente_id": paciente["id"]}).status_code == 422


def test_si_la_llave_choca_se_reintenta_con_otra(base, monkeypatch):
    api, h, paciente, enf = base
    primera = api.consulta(h, paciente["id"], enf)["llave"]
    secuencia = iter([primera, primera, "AAAA-BBBB-CCCC-DDDD"])  # dos choques y luego una libre
    monkeypatch.setattr(consulta_service, "nueva_llave", lambda: next(secuencia))
    r = api.cliente.post(URL, headers=h, json={"paciente_id": paciente["id"], "enfermedad_id": enf})
    assert r.status_code == 201 and r.json()["llave"] == "AAAA-BBBB-CCCC-DDDD"


def test_si_no_se_logra_una_llave_unica_da_503_y_la_sesion_sigue_sirviendo(base, monkeypatch):
    api, h, paciente, enf = base
    existente = api.consulta(h, paciente["id"], enf)["llave"]
    monkeypatch.setattr(consulta_service, "nueva_llave", lambda: existente)
    assert api.cliente.post(URL, headers=h, json={"paciente_id": paciente["id"], "enfermedad_id": enf}).status_code == 503
    monkeypatch.undo()
    assert api.consulta(h, paciente["id"], enf)


# ---------------------------------------------------------------- consultar (solo las propias)

def test_listar_solo_muestra_las_propias_de_la_mas_reciente_a_la_mas_antigua(base):
    api, ana, paciente, enf = base
    luis = api.medico("dr.luis")
    primera = api.consulta(ana, paciente["id"], enf, notas="primera")
    segunda = api.consulta(ana, paciente["id"], enf, notas="segunda")
    api.consulta(luis, paciente["id"], enf, notas="de luis")

    propias = api.cliente.get(URL, headers=ana).json()
    assert propias["total"] == 2
    assert [c["id"] for c in propias["items"]] == [segunda["id"], primera["id"]]
    assert api.cliente.get(URL, headers=luis).json()["total"] == 1


def test_filtros_por_paciente_diagnostico_y_fecha(base):
    api, h, p1, gripe = base
    p2, covid = api.paciente(h, 1), api.enfermedad("covid")
    api.consulta(h, p1["id"], gripe)
    api.consulta(h, p2["id"], gripe)
    api.consulta(h, p2["id"], covid)

    def total(**params):
        return api.cliente.get(URL, params=params, headers=h).json()["total"]

    assert total(paciente_id=p2["id"]) == 2
    assert total(enfermedad_id=covid) == 1
    assert total(paciente_id=p2["id"], enfermedad_id=gripe) == 1
    hoy, ayer, manana = dias(0), dias(-1), dias(1)
    assert total(desde=hoy, hasta=hoy) == 3        # el día completo, incluido hoy
    assert total(hasta=ayer) == 0
    assert total(desde=manana) == 0
    assert total(desde=ayer, hasta=manana) == 3
    assert api.cliente.get(URL, params={"desde": manana, "hasta": ayer}, headers=h).status_code == 422


def test_paginacion(base):
    api, h, paciente, enf = base
    for i in range(5):
        api.consulta(h, paciente["id"], enf, notas=str(i))
    pagina = api.cliente.get(URL, params={"limit": 2, "offset": 1}, headers=h).json()
    assert [c["notas"] for c in pagina["items"]] == ["3", "2"]
    assert (pagina["total"], pagina["limit"], pagina["offset"]) == (5, 2, 1)
    assert api.cliente.get(URL, params={"limit": 101}, headers=h).status_code == 422


def test_una_consulta_ajena_no_existe_por_id(base):
    api, ana, paciente, enf = base
    luis = api.medico("dr.luis")
    c = api.consulta(ana, paciente["id"], enf)
    assert api.cliente.get(f"{URL}/{c['id']}", headers=ana).json() == c
    assert api.cliente.get(f"{URL}/{c['id']}", headers=luis).status_code == 404
    assert api.cliente.get(f"{URL}/999", headers=ana).status_code == 404


# ---------------------------------------------------------------- acceso con la llave

def test_otro_medico_abre_la_consulta_con_la_llave_que_le_da_el_paciente(base):
    api, ana, paciente, enf = base
    luis = api.medico("dr.luis")
    c = api.consulta(ana, paciente["id"], enf, peso=80, notas="control en 15 días")

    r = api.cliente.post(ACCESO, headers=luis, json={"llave": c["llave"]})
    assert r.status_code == 200
    assert r.json() == c and r.json()["medico_id"] != 2  # es la consulta de Ana, vista por Luis


@pytest.mark.parametrize("forma", [str.lower, lambda k: k.replace("-", " "), lambda k: k.replace("-", "").lower(), lambda k: f"  {k} "])
def test_la_llave_se_acepta_escrita_de_varias_formas(base, forma):
    api, ana, paciente, enf = base
    luis = api.medico("dr.luis")
    c = api.consulta(ana, paciente["id"], enf)
    assert api.cliente.post(ACCESO, headers=luis, json={"llave": forma(c["llave"])}).json()["id"] == c["id"]


def test_con_la_llave_solo_se_lee_no_se_da_acceso_a_nada_mas(base):
    api, ana, paciente, enf = base
    luis = api.medico("dr.luis")
    c = api.consulta(ana, paciente["id"], enf)
    assert api.cliente.post(ACCESO, headers=luis, json={"llave": c["llave"]}).status_code == 200
    # sigue sin verla por id, ni en su lista, ni puede modificarla
    assert api.cliente.get(f"{URL}/{c['id']}", headers=luis).status_code == 404
    assert api.cliente.get(URL, headers=luis).json()["total"] == 0
    assert api.cliente.patch(f"{URL}/{c['id']}", headers=luis, json={"notas": "alterada"}).status_code == 404
    assert api.cliente.get(f"{URL}/{c['id']}", headers=ana).json()["notas"] is None


@pytest.mark.parametrize("llave", ["AAAA-BBBB-CCCC-DDDD", "abc", "K7QM-2XW9-HP4T", "' OR 1=1 --", "%", "_" * 19])
def test_una_llave_incorrecta_da_404_siempre_con_el_mismo_mensaje(base, llave):
    api, ana, paciente, enf = base
    api.consulta(ana, paciente["id"], enf)
    r = api.cliente.post(ACCESO, headers=ana, json={"llave": llave})
    assert r.status_code == 404 and r.json()["detail"] == "La llave no corresponde a ninguna consulta"


def test_llave_vacia_o_ausente_da_422(base):
    api, ana, *_ = base
    assert api.cliente.post(ACCESO, headers=ana, json={"llave": "   "}).status_code == 422
    assert api.cliente.post(ACCESO, headers=ana, json={}).status_code == 422


def test_la_llave_no_se_puede_pasar_en_la_url(base):
    api, ana, paciente, enf = base
    c = api.consulta(ana, paciente["id"], enf)
    assert api.cliente.get(f"{URL}/{c['llave']}", headers=ana).status_code == 422


# ---------------------------------------------------------------- corregir

def test_corregir_cambia_solo_lo_enviado_y_no_toca_llave_edad_fecha_ni_paciente(base):
    api, h, paciente, enf = base
    covid = api.enfermedad("covid")
    antes = api.consulta(h, paciente["id"], enf, peso=70, altura=1.7, notas="inicial")
    r = api.cliente.patch(f"{URL}/{antes['id']}", headers=h, json={"enfermedad_id": covid, "notas": "corregida"})
    assert r.status_code == 200
    assert r.json() == {**antes, "enfermedad": {"id": covid, "nombre": "covid"}, "notas": "corregida"}


def test_corregir_con_null_borra_peso_altura_y_notas(base):
    api, h, paciente, enf = base
    c = api.consulta(h, paciente["id"], enf, peso=70, altura=1.7, notas="x")
    r = api.cliente.patch(f"{URL}/{c['id']}", headers=h, json={"peso": None, "altura": None, "notas": None})
    assert (r.json()["peso"], r.json()["altura"], r.json()["notas"]) == (None, None, None)


@pytest.mark.parametrize("cuerpo", [{}, {"enfermedad_id": None}, {"enfermedad_id": 0}, {"peso": 0}, {"altura": 9}, {"notas": "x" * 5001}])
def test_corregir_con_datos_invalidos_da_422(base, cuerpo):
    api, h, paciente, enf = base
    c = api.consulta(h, paciente["id"], enf)
    assert api.cliente.patch(f"{URL}/{c['id']}", headers=h, json=cuerpo).status_code == 422


def test_corregir_con_enfermedad_inexistente_o_consulta_inexistente_da_404(base):
    api, h, paciente, enf = base
    c = api.consulta(h, paciente["id"], enf)
    assert api.cliente.patch(f"{URL}/{c['id']}", headers=h, json={"enfermedad_id": 999}).status_code == 404
    assert api.cliente.patch(f"{URL}/999", headers=h, json={"notas": "x"}).status_code == 404


def test_las_consultas_no_se_pueden_borrar(base):
    api, h, paciente, enf = base
    c = api.consulta(h, paciente["id"], enf)
    assert api.cliente.delete(f"{URL}/{c['id']}", headers=h).status_code == 405


def test_un_paciente_con_consultas_no_se_puede_borrar(base):
    api, h, paciente, enf = base
    api.consulta(h, paciente["id"], enf)
    assert api.cliente.delete(f"/api/v1/pacientes/{paciente['id']}", headers=h).status_code == 409
