"""Dashboard: top 5 por mes, total anual por región y casos mensuales por región."""
from datetime import datetime

import pytest

URL = "/api/v1/dashboard"
ANIO = 2025


class Escenario:
    """Crea consultas en una fecha y ciudad concretas (la API siempre fecha las consultas con 'ahora')."""

    def __init__(self, api):
        self.api = api
        self.medicos: dict[str, dict] = {}
        self.pacientes: dict[str, dict] = {}
        self.enfermedades: dict[str, int] = {}

    def consultar(self, ciudad: str, enfermedad: str, mes: int, n: int = 1, anio: int = ANIO, usuario: str | None = None):
        usuario = usuario or f"dr.{ciudad.lower().replace(' ', '')}"
        if usuario not in self.medicos:
            self.medicos[usuario] = self.api.medico(usuario, ciudad=ciudad)
            self.pacientes[usuario] = self.api.paciente(self.medicos[usuario], len(self.pacientes))
        if enfermedad not in self.enfermedades:
            self.enfermedades[enfermedad] = self.api.enfermedad(enfermedad)
        for _ in range(n):
            c = self.api.consulta(self.medicos[usuario], self.pacientes[usuario]["id"], self.enfermedades[enfermedad])
            self.api.fechar(c["id"], datetime(anio, mes, 15, 9, 30))

    def ver(self, anio: int = ANIO, usuario: str | None = None):
        h = self.medicos[usuario] if usuario else next(iter(self.medicos.values()))
        r = self.api.cliente.get(URL, params={"anio": anio}, headers=h)
        assert r.status_code == 200, r.text
        return r.json()


@pytest.fixture
def esc(api):
    return Escenario(api)


def _nombres(lista):
    return [e["nombre"] for e in lista]


def _casos(lista):
    return {e["nombre"]: e["casos"] for e in lista}


# ---------------------------------------------------------------- acceso y forma

def test_exige_sesion(api):
    assert api.cliente.get(URL).status_code == 401


@pytest.mark.parametrize("anio", ["abc", "1999", "2101", "-1"])
def test_anio_invalido_da_422(esc, anio):
    esc.consultar("Morelia", "gripe", 1)
    h = next(iter(esc.medicos.values()))
    assert esc.api.cliente.get(URL, params={"anio": anio}, headers=h).status_code == 422


def test_sin_consultas_responde_vacio_pero_con_los_12_meses(api):
    h = api.medico("dra.ana")
    r = api.cliente.get(URL, params={"anio": ANIO}, headers=h).json()
    assert r["anio"] == ANIO and r["total_consultas"] == 0
    assert r["top_anual"] == [] and r["total_anual_por_region"] == [] and r["casos_mensuales_por_region"] == []
    assert [m["mes"] for m in r["top_por_mes"]] == list(range(1, 13))
    assert all(m["enfermedades"] == [] for m in r["top_por_mes"])


def test_sin_anio_usa_el_actual(api):
    h = api.medico("dra.ana")
    assert api.cliente.get(URL, headers=h).json()["anio"] == datetime.now().year


# ---------------------------------------------------------------- top 5 por mes

def test_top_por_mes_ordena_de_mas_a_menos_y_corta_en_cinco(esc):
    # enero: 7 enfermedades con 7,6,5,4,3,2,1 casos
    for i, n in enumerate([7, 6, 5, 4, 3, 2, 1]):
        esc.consultar("Morelia", f"enf{i}", mes=1, n=n)
    enero = esc.ver()["top_por_mes"][0]
    assert enero["mes"] == 1
    assert _nombres(enero["enfermedades"]) == ["enf0", "enf1", "enf2", "enf3", "enf4"]
    assert [e["casos"] for e in enero["enfermedades"]] == [7, 6, 5, 4, 3]


def test_cada_mes_tiene_su_propio_top(esc):
    esc.consultar("Morelia", "gripe", mes=1, n=3)
    esc.consultar("Morelia", "asma", mes=1, n=1)
    esc.consultar("Morelia", "asma", mes=2, n=4)
    meses = {m["mes"]: m["enfermedades"] for m in esc.ver()["top_por_mes"]}
    assert _nombres(meses[1]) == ["gripe", "asma"]
    assert _nombres(meses[2]) == ["asma"]
    assert meses[3] == []


def test_los_empates_se_resuelven_por_nombre_para_que_el_resultado_sea_estable(esc):
    for nombre in ["zeta", "alfa", "mu"]:
        esc.consultar("Morelia", nombre, mes=4, n=2)
    abril = esc.ver()["top_por_mes"][3]["enfermedades"]
    assert _nombres(abril) == ["alfa", "mu", "zeta"]


def test_solo_cuenta_el_anio_pedido(esc):
    esc.consultar("Morelia", "gripe", mes=12, n=2, anio=ANIO)
    esc.consultar("Morelia", "gripe", mes=1, n=5, anio=ANIO + 1)
    esc.consultar("Morelia", "gripe", mes=12, n=9, anio=ANIO - 1)
    r = esc.ver()
    assert r["total_consultas"] == 2
    assert _casos(r["top_anual"]) == {"gripe": 2}
    assert esc.ver(anio=ANIO + 1)["total_consultas"] == 5


def test_los_limites_del_anio_son_enero_1_y_diciembre_31(esc):
    esc.consultar("Morelia", "gripe", mes=1, n=1)
    c = esc.api.consulta(esc.medicos["dr.morelia"], esc.pacientes["dr.morelia"]["id"], esc.enfermedades["gripe"])
    esc.api.fechar(c["id"], datetime(ANIO, 12, 31, 23, 59, 59))
    c2 = esc.api.consulta(esc.medicos["dr.morelia"], esc.pacientes["dr.morelia"]["id"], esc.enfermedades["gripe"])
    esc.api.fechar(c2["id"], datetime(ANIO + 1, 1, 1, 0, 0, 0))
    assert esc.ver()["total_consultas"] == 2


# ---------------------------------------------------------------- las 5 del año

def test_top_anual_suma_todos_los_meses_y_todas_las_regiones(esc):
    esc.consultar("Morelia", "gripe", mes=1, n=2)
    esc.consultar("Morelia", "gripe", mes=7, n=1)
    esc.consultar("Toluca", "gripe", mes=3, n=1)
    esc.consultar("Toluca", "asma", mes=3, n=3)
    esc.consultar("Toluca", "otitis", mes=5, n=1)
    r = esc.ver()
    assert [(e["nombre"], e["casos"]) for e in r["top_anual"]] == [("gripe", 4), ("asma", 3), ("otitis", 1)]
    assert r["total_consultas"] == 8


def test_una_enfermedad_que_es_top_del_mes_pero_no_del_anio_no_entra_en_las_vistas_por_region(esc):
    """6 enfermedades con muchos casos todo el año + una que solo destaca en enero."""
    for i in range(5):
        esc.consultar("Morelia", f"comun{i}", mes=6, n=10)
    esc.consultar("Morelia", "brote", mes=1, n=3)  # en enero es la única: top del mes; en el año es la 6.ª
    r = esc.ver()
    assert "brote" in _nombres(r["top_por_mes"][0]["enfermedades"])
    assert "brote" not in _nombres(r["top_anual"])
    assert "brote" not in _nombres(r["total_anual_por_region"][0]["enfermedades"])
    assert r["total_anual_por_region"][0]["total"] == 50
    assert sum(m["casos"] for m in r["casos_mensuales_por_region"][0]["meses"]) == 50


# ---------------------------------------------------------------- total anual por región

def test_total_anual_por_region_con_el_desglose_de_las_5(esc):
    esc.consultar("Morelia", "gripe", mes=1, n=3)
    esc.consultar("Morelia", "asma", mes=2, n=1)
    esc.consultar("Toluca", "gripe", mes=1, n=1)
    esc.consultar("Toluca", "asma", mes=9, n=4)
    r = esc.ver()["total_anual_por_region"]
    assert [x["region"] for x in r] == ["Toluca", "Morelia"]
    por_region = {x["region"]: x for x in r}
    assert por_region["Morelia"]["total"] == 4 and _casos(por_region["Morelia"]["enfermedades"]) == {"gripe": 3, "asma": 1}
    assert por_region["Toluca"]["total"] == 5 and _casos(por_region["Toluca"]["enfermedades"]) == {"gripe": 1, "asma": 4}


def test_las_regiones_van_de_mayor_a_menor_total(esc):
    esc.consultar("Morelia", "gripe", mes=1, n=2)
    esc.consultar("Toluca", "gripe", mes=1, n=5)
    esc.consultar("Puebla", "gripe", mes=1, n=3)
    assert [x["region"] for x in esc.ver()["total_anual_por_region"]] == ["Toluca", "Puebla", "Morelia"]


def test_el_desglose_incluye_las_5_con_cero_donde_no_hubo_casos_y_en_el_orden_de_top_anual(esc):
    esc.consultar("Morelia", "gripe", mes=1, n=3)
    esc.consultar("Toluca", "asma", mes=1, n=1)
    r = esc.ver()
    orden = _nombres(r["top_anual"])
    assert orden == ["gripe", "asma"]
    for region in r["total_anual_por_region"]:
        assert _nombres(region["enfermedades"]) == orden
    assert _casos(next(x for x in r["total_anual_por_region"] if x["region"] == "Toluca")["enfermedades"]) == {"gripe": 0, "asma": 1}


# ---------------------------------------------------------------- casos mensuales por región

def test_casos_mensuales_por_region_siempre_trae_12_meses_con_ceros(esc):
    esc.consultar("Morelia", "gripe", mes=2, n=3)
    esc.consultar("Morelia", "asma", mes=2, n=1)
    esc.consultar("Morelia", "gripe", mes=11, n=2)
    region = esc.ver()["casos_mensuales_por_region"][0]
    assert region["region"] == "Morelia"
    assert [m["mes"] for m in region["meses"]] == list(range(1, 13))
    assert {m["mes"]: m["casos"] for m in region["meses"] if m["casos"]} == {2: 4, 11: 2}


def test_la_suma_mensual_de_una_region_es_igual_a_su_total_anual(esc):
    for mes, n in [(1, 2), (4, 5), (8, 1)]:
        esc.consultar("Morelia", "gripe", mes=mes, n=n)
        esc.consultar("Toluca", "asma", mes=mes, n=n + 1)
    r = esc.ver()
    totales = {x["region"]: x["total"] for x in r["total_anual_por_region"]}
    for region in r["casos_mensuales_por_region"]:
        assert sum(m["casos"] for m in region["meses"]) == totales[region["region"]]


# ---------------------------------------------------------------- región = ciudad del médico

def test_la_ciudad_se_agrupa_sin_importar_mayusculas_ni_espacios(esc):
    esc.consultar("Morelia", "gripe", mes=1, n=2, usuario="dr.a")
    esc.consultar("morelia", "gripe", mes=1, n=1, usuario="dr.b")
    esc.consultar("  MORELIA ", "gripe", mes=1, n=1, usuario="dr.c")
    esc.consultar("Ciudad  de México", "gripe", mes=1, n=1, usuario="dr.d")
    esc.consultar("Ciudad de México", "gripe", mes=1, n=2, usuario="dr.e")
    r = esc.ver()["total_anual_por_region"]
    assert {x["region"]: x["total"] for x in r} == {"Morelia": 4, "Ciudad de México": 3}


def test_varios_medicos_de_la_misma_ciudad_suman_en_una_region(esc):
    esc.consultar("Morelia", "gripe", mes=1, n=1, usuario="dr.a")
    esc.consultar("Morelia", "gripe", mes=1, n=1, usuario="dr.b")
    regiones = esc.ver()["total_anual_por_region"]
    assert len(regiones) == 1 and regiones[0]["total"] == 2


# ---------------------------------------------------------------- privacidad

def test_muestra_las_consultas_de_todos_los_medicos_pero_solo_conteos(esc):
    esc.consultar("Morelia", "gripe", mes=1, n=2, usuario="dr.a")
    esc.consultar("Toluca", "gripe", mes=1, n=3, usuario="dr.b")
    r_a = esc.ver(usuario="dr.a")
    assert r_a["total_consultas"] == 5  # ve también lo de dr.b, agregado
    texto = str(r_a)
    for dato in ["paciente", "llave", "notas", "curp", "dr.a", "dr.b"]:
        assert dato not in texto.lower()
