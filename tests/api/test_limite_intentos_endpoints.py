"""Límite de intentos en el login y en el acceso con llave (POST /consultas/acceso)."""
import pytest

from app.core.config import settings
from app.core.limites import intentos_login

LOGIN = "/api/v1/auth/login"
ACCESO = "/api/v1/consultas/acceso"
MAXIMO = settings.intentos_max_por_cuenta  # 5 por defecto


def _login(api, usuario, password):
    return api.cliente.post(LOGIN, json={"nombre_de_usuario": usuario, "password": password})


@pytest.fixture
def ana(api):
    api.medico("dra.ana")  # registra la cuenta (contraseña: Clave-segura-123)
    return api


def test_los_primeros_intentos_fallidos_dan_401(ana):
    for _ in range(MAXIMO):
        assert _login(ana, "dra.ana", "mala-clave").status_code == 401


def test_al_llegar_al_maximo_responde_429_con_retry_after(ana):
    for _ in range(MAXIMO):
        _login(ana, "dra.ana", "mala-clave")
    r = _login(ana, "dra.ana", "mala-clave")
    assert r.status_code == 429
    assert "Demasiados intentos" in r.json()["detail"]
    assert 0 < int(r.headers["Retry-After"]) <= settings.intentos_ventana_minutos * 60


def test_bloqueada_la_cuenta_ni_la_contrasena_correcta_entra(ana):
    for _ in range(MAXIMO):
        _login(ana, "dra.ana", "mala-clave")
    assert _login(ana, "dra.ana", "Clave-segura-123").status_code == 429


def test_el_bloqueo_no_revela_si_el_usuario_existe(ana):
    """Un usuario que no existe se bloquea igual que uno real: la respuesta no sirve para descubrir cuentas."""
    for _ in range(MAXIMO):
        assert _login(ana, "no.existe", "x").status_code == 401
    assert _login(ana, "no.existe", "x").status_code == 429


def test_otro_usuario_no_se_ve_afectado_por_el_bloqueo(ana):
    ana.medico("dr.luis")
    for _ in range(MAXIMO):
        _login(ana, "dra.ana", "mala-clave")
    assert _login(ana, "dra.ana", "x").status_code == 429
    assert _login(ana, "dr.luis", "Clave-segura-123").status_code == 200


def test_el_usuario_se_cuenta_sin_importar_las_mayusculas(ana):
    for usuario in ["dra.ana", "DRA.ANA", "Dra.Ana", "dra.ANA", "DRA.ana"]:
        assert _login(ana, usuario, "mala-clave").status_code == 401
    assert _login(ana, "dra.ana", "Clave-segura-123").status_code == 429


def test_un_acierto_antes_del_maximo_reinicia_el_contador(ana):
    for _ in range(MAXIMO - 1):
        _login(ana, "dra.ana", "mala-clave")
    assert _login(ana, "dra.ana", "Clave-segura-123").status_code == 200
    for _ in range(MAXIMO):  # vuelve a tener todos sus intentos
        assert _login(ana, "dra.ana", "mala-clave").status_code == 401
    assert _login(ana, "dra.ana", "mala-clave").status_code == 429


def test_pasada_la_ventana_se_puede_volver_a_intentar(ana, monkeypatch):
    for _ in range(MAXIMO):
        _login(ana, "dra.ana", "mala-clave")
    assert _login(ana, "dra.ana", "Clave-segura-123").status_code == 429
    ahora = intentos_login._reloj()
    monkeypatch.setattr(intentos_login, "_reloj", lambda: ahora + settings.intentos_ventana_minutos * 60 + 1)
    assert _login(ana, "dra.ana", "Clave-segura-123").status_code == 200


def test_una_ip_que_prueba_muchos_usuarios_tambien_se_bloquea(api):
    for i in range(settings.intentos_max_por_ip):
        assert _login(api, f"usuario{i}", "x").status_code == 401  # cada usuario con un solo fallo
    assert _login(api, "otro.mas", "x").status_code == 429


def test_un_login_correcto_no_reinicia_el_contador_de_la_ip(api):
    """Si lo hiciera, bastaría intercalar un login con una cuenta propia para no llegar nunca al límite."""
    api.medico("dra.ana")
    for i in range(settings.intentos_max_por_ip - 1):
        _login(api, f"usuario{i}", "x")
    assert _login(api, "dra.ana", "Clave-segura-123").status_code == 200
    _login(api, "otro", "x")
    assert _login(api, "dra.ana", "Clave-segura-123").status_code == 429


def test_el_bloqueo_del_login_no_afecta_a_la_sesion_ya_iniciada_ni_al_registro(ana):
    sesion = ana.medico("dra.ana")
    for _ in range(MAXIMO + 1):
        _login(ana, "dra.ana", "mala-clave")
    assert _login(ana, "dra.ana", "Clave-segura-123").status_code == 429
    assert ana.cliente.get("/api/v1/auth/me", headers=sesion).status_code == 200
    assert ana.cliente.post("/api/v1/auth/registro", json={
        "nombre": "Luis", "apellidos": "Pérez", "ciudad": "Toluca", "efirma": "f",
        "nombre_de_usuario": "dr.luis", "password": "Clave-segura-123"}).status_code == 201


# ---------------------------------------------------------------- acceso con llave

@pytest.fixture
def con_consulta(api):
    ana = api.medico("dra.ana")
    paciente, enfermedad = api.paciente(ana, 0), api.enfermedad("gripe")
    consulta = api.consulta(ana, paciente["id"], enfermedad)
    return api, api.medico("dr.luis"), consulta


def _acceso(api, headers, llave):
    return api.cliente.post(ACCESO, headers=headers, json={"llave": llave})


def test_las_llaves_incorrectas_se_limitan_por_medico(con_consulta):
    api, luis, consulta = con_consulta
    for _ in range(MAXIMO):
        assert _acceso(api, luis, "AAAA-BBBB").status_code == 404
    r = _acceso(api, luis, "AAAA-BBBB")
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    # bloqueado: ni la llave buena abre
    assert _acceso(api, luis, consulta["llave"]).status_code == 429


def test_los_fallos_de_un_medico_no_bloquean_a_otro(con_consulta):
    api, luis, consulta = con_consulta
    for _ in range(MAXIMO):
        _acceso(api, luis, "AAAA-BBBB")
    assert _acceso(api, luis, "AAAA-BBBB").status_code == 429
    assert _acceso(api, api.medico("dra.ana"), consulta["llave"]).status_code == 200


def test_una_llave_correcta_reinicia_el_contador_del_medico(con_consulta):
    api, luis, consulta = con_consulta
    for _ in range(MAXIMO - 1):
        _acceso(api, luis, "AAAA-BBBB")
    assert _acceso(api, luis, consulta["llave"]).status_code == 200
    for _ in range(MAXIMO):
        assert _acceso(api, luis, "AAAA-BBBB").status_code == 404


def test_crear_cuentas_nuevas_no_evita_el_limite_porque_la_ip_tambien_cuenta(api):
    ana = api.medico("dra.ana")
    api.consulta(ana, api.paciente(ana, 0)["id"], api.enfermedad("gripe"))
    for i in range(settings.intentos_max_por_ip):
        assert _acceso(api, api.medico(f"atacante{i}"), "AAAA-BBBB").status_code == 404
    assert _acceso(api, api.medico("atacante-nuevo"), "AAAA-BBBB").status_code == 429


def test_el_login_y_la_llave_llevan_contadores_separados(con_consulta):
    api, luis, _ = con_consulta
    for _ in range(MAXIMO):
        _login(api, "dr.luis", "mala-clave")
    assert _login(api, "dr.luis", "Clave-segura-123").status_code == 429
    assert _acceso(api, luis, "AAAA-BBBB").status_code == 404  # la llave sigue con sus 5 intentos
