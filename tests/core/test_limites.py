"""LimiteIntentos con un reloj falso: no hace falta esperar minutos de verdad."""
import pytest

from app.core import limites
from app.core.limites import LimiteIntentos


class Reloj:
    def __init__(self):
        self.ahora = 1000.0

    def __call__(self):
        return self.ahora


@pytest.fixture
def reloj():
    return Reloj()


@pytest.fixture
def limite(reloj):
    return LimiteIntentos(ventana_segundos=900, reloj=reloj)


def test_sin_fallos_no_hay_espera(limite):
    assert limite.espera("a", maximo=3) == 0


def test_bloquea_al_llegar_al_maximo_y_no_antes(limite):
    for _ in range(2):
        limite.fallo("a")
    assert limite.espera("a", maximo=3) == 0
    limite.fallo("a")
    assert limite.espera("a", maximo=3) == 900


def test_la_espera_baja_con_el_tiempo_y_termina_cuando_el_fallo_sale_de_la_ventana(limite, reloj):
    for _ in range(3):
        limite.fallo("a")
    reloj.ahora += 600
    assert limite.espera("a", maximo=3) == 300
    reloj.ahora += 300  # justo al cumplirse la ventana el fallo deja de contar
    assert limite.espera("a", maximo=3) == 0


def test_los_fallos_escalonados_liberan_de_a_uno(limite, reloj):
    limite.fallo("a")            # t=0
    reloj.ahora += 100
    limite.fallo("a")            # t=100
    reloj.ahora += 100
    limite.fallo("a")            # t=200 -> bloqueada hasta que salga el de t=0
    assert limite.espera("a", maximo=3) == 700
    reloj.ahora += 700
    assert limite.espera("a", maximo=3) == 0
    limite.fallo("a")            # vuelve a tener 3 vigentes (t=100, 200, 900)
    assert limite.espera("a", maximo=3) > 0


def test_cada_clave_cuenta_por_separado(limite):
    for _ in range(3):
        limite.fallo("a")
    assert limite.espera("a", maximo=3) > 0
    assert limite.espera("b", maximo=3) == 0


def test_reiniciar_borra_los_fallos_de_esa_clave(limite):
    for _ in range(3):
        limite.fallo("a")
        limite.fallo("b")
    limite.reiniciar("a")
    assert limite.espera("a", maximo=3) == 0
    assert limite.espera("b", maximo=3) > 0


def test_el_maximo_se_decide_al_consultar(limite):
    for _ in range(5):
        limite.fallo("a")
    assert limite.espera("a", maximo=5) > 0
    assert limite.espera("a", maximo=6) == 0


def test_la_memoria_tiene_tope_aunque_se_inventen_claves(limite, monkeypatch):
    monkeypatch.setattr(limites, "MAX_CLAVES", 100)
    for i in range(1000):
        limite.fallo(f"clave-{i}")
    assert len(limite._fallos) <= 100


def test_las_claves_vencidas_se_liberan_al_llenarse(limite, reloj, monkeypatch):
    monkeypatch.setattr(limites, "MAX_CLAVES", 10)
    for i in range(10):
        limite.fallo(f"vieja-{i}")
    reloj.ahora += 901
    limite.fallo("nueva")
    assert set(limite._fallos) == {"nueva"}
