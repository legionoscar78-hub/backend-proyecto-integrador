"""Pruebas de auth contra SQLite en memoria (solo se crea la tabla medicos). La integración con
PostgreSQL se verificó aparte con el esquema real de Alembic."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.api.v1.api import api_router
from app.core import security
from app.core.config import settings
from app.models.medico import Medico
from app.repositories import medico_repo

REGISTRO = "/api/v1/auth/registro"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"

MEDICO = {
    "nombre": "Ana", "apellidos": "López Ruiz", "ciudad": "Morelia", "efirma": "firma-demo-abc123",
    "nombre_de_usuario": "Dra.Ana", "password": "Clave-segura-123",
}


@pytest.fixture
def entorno():
    motor = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Medico.__table__.create(motor)
    Sesion = sessionmaker(bind=motor, autoflush=False)

    def get_db_prueba():
        db = Sesion()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = get_db_prueba
    return TestClient(app), Sesion


@pytest.fixture
def cliente(entorno):
    return entorno[0]


def _registrar(cliente, **cambios):
    return cliente.post(REGISTRO, json={**MEDICO, **cambios})


def _token(cliente, usuario="dra.ana", password=MEDICO["password"]):
    r = cliente.post(LOGIN, json={"nombre_de_usuario": usuario, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- registro

def test_registro_crea_el_medico_sin_exponer_datos_sensibles(entorno):
    cliente, Sesion = entorno
    r = _registrar(cliente)
    assert r.status_code == 201
    cuerpo = r.json()
    assert cuerpo == {"id": 1, "nombre": "Ana", "apellidos": "López Ruiz", "ciudad": "Morelia",
                      "nombre_de_usuario": "dra.ana"}  # usuario en minúsculas; sin password ni efirma
    with Sesion() as db:
        guardado = db.scalar(select(Medico))
        assert guardado.password.startswith("$argon2id$") and MEDICO["password"] not in guardado.password
        assert guardado.efirma == MEDICO["efirma"]


def test_usuario_repetido_da_409_aunque_cambien_las_mayusculas(cliente):
    assert _registrar(cliente).status_code == 201
    r = _registrar(cliente, nombre_de_usuario="DRA.ANA")
    assert r.status_code == 409
    assert "ya está en uso" in r.json()["detail"]


def test_carrera_entre_dos_registros_tambien_da_409_y_la_sesion_sigue_sirviendo(entorno, monkeypatch):
    cliente, _ = entorno
    assert _registrar(cliente).status_code == 201
    # Simula que la comprobación previa no vio al otro usuario: lo detiene la restricción UNIQUE
    monkeypatch.setattr(medico_repo, "obtener_por_usuario", lambda db, usuario: None)
    assert _registrar(cliente).status_code == 409
    monkeypatch.undo()
    assert _registrar(cliente, nombre_de_usuario="otra.persona").status_code == 201


@pytest.mark.parametrize("cambios", [
    {"password": "corta"},
    {"password": "x" * 129},
    {"nombre_de_usuario": "ab"},
    {"nombre_de_usuario": "con espacio"},
    {"nombre_de_usuario": "raro;drop"},
    {"nombre_de_usuario": "ñandú"},
    {"nombre": ""},
    {"nombre": "   "},
    {"nombre": "x" * 101},
    {"efirma": ""},
    {"efirma": "x" * 10_001},
])
def test_registro_con_datos_invalidos_da_422(cliente, cambios):
    assert _registrar(cliente, **cambios).status_code == 422


def test_registro_sin_campos_obligatorios(cliente):
    for campo in MEDICO:
        datos = {k: v for k, v in MEDICO.items() if k != campo}
        assert cliente.post(REGISTRO, json=datos).status_code == 422, campo


# ---------------------------------------------------------------- login

def test_login_devuelve_un_token_que_sirve_en_me(cliente):
    _registrar(cliente)
    r = cliente.post(LOGIN, json={"nombre_de_usuario": "dra.ana", "password": MEDICO["password"]})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["token_type"] == "bearer" and cuerpo["expires_in"] == settings.access_token_minutes * 60

    yo = cliente.get(ME, headers=_auth(cuerpo["access_token"]))
    assert yo.status_code == 200 and yo.json()["nombre_de_usuario"] == "dra.ana"
    assert "password" not in yo.json() and "efirma" not in yo.json()


def test_login_no_distingue_mayusculas_en_el_usuario(cliente):
    _registrar(cliente)
    assert _token(cliente, usuario="DRA.ANA")


def test_contrasena_incorrecta_y_usuario_inexistente_responden_igual(cliente):
    _registrar(cliente)
    mala = cliente.post(LOGIN, json={"nombre_de_usuario": "dra.ana", "password": "incorrecta"})
    fantasma = cliente.post(LOGIN, json={"nombre_de_usuario": "nadie", "password": "incorrecta"})
    assert mala.status_code == fantasma.status_code == 401
    assert mala.json() == fantasma.json()
    assert mala.headers["www-authenticate"] == fantasma.headers["www-authenticate"] == "Bearer"


def test_la_contrasena_distingue_mayusculas(cliente):
    _registrar(cliente)
    assert cliente.post(LOGIN, json={"nombre_de_usuario": "dra.ana", "password": MEDICO["password"].upper()}
                        ).status_code == 401


def test_login_actualiza_el_hash_si_se_creo_con_parametros_mas_debiles(entorno):
    cliente, Sesion = entorno
    _registrar(cliente)
    debil = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(MEDICO["password"])
    with Sesion() as db:
        db.scalar(select(Medico)).password = debil
        db.commit()

    _token(cliente)  # inicia sesión con el hash débil
    with Sesion() as db:
        nuevo = db.scalar(select(Medico)).password
    assert nuevo != debil and not security.necesita_rehash(nuevo)
    assert _token(cliente)  # y la contraseña sigue valiendo


def test_login_con_cuerpo_incompleto(cliente):
    assert cliente.post(LOGIN, json={"nombre_de_usuario": "x"}).status_code == 422
    assert cliente.post(LOGIN, json={"password": "x"}).status_code == 422


# ---------------------------------------------------------------- sesión (get_current_medico)

def _firmar(sub, **cambios):
    ahora = datetime.now(timezone.utc)
    claims = {"sub": str(sub), "iss": security.EMISOR, "iat": ahora, "exp": ahora + timedelta(minutes=5), **cambios}
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def test_me_sin_token_da_401_con_www_authenticate(cliente):
    r = cliente.get(ME)
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("cabecera", ["Bearer", "Bearer basura", "Basic dXNlcjpwYXNz", "Token abc", "abc"])
def test_me_con_credenciales_mal_formadas_da_401(cliente, cabecera):
    assert cliente.get(ME, headers={"Authorization": cabecera}).status_code == 401


def test_me_con_token_expirado_da_401(cliente):
    _registrar(cliente)
    expirado = _firmar(1, exp=datetime.now(timezone.utc) - timedelta(minutes=1))
    assert cliente.get(ME, headers=_auth(expirado)).status_code == 401


def test_me_con_token_de_un_medico_que_ya_no_existe_da_401(cliente):
    _registrar(cliente)
    assert cliente.get(ME, headers=_auth(_firmar(999))).status_code == 401


def test_me_con_token_firmado_por_otro_da_401(cliente):
    _registrar(cliente)
    ajeno = jwt.encode({"sub": "1", "iss": security.EMISOR, "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
                        "iat": datetime.now(timezone.utc)}, "otra-clave-de-mas-de-32-caracteres-xxxxx", algorithm="HS256")
    assert cliente.get(ME, headers=_auth(ajeno)).status_code == 401


def test_cada_token_identifica_a_su_medico(cliente):
    _registrar(cliente)
    _registrar(cliente, nombre_de_usuario="dr.luis", nombre="Luis")
    t_ana, t_luis = _token(cliente), _token(cliente, usuario="dr.luis")
    assert cliente.get(ME, headers=_auth(t_ana)).json()["nombre"] == "Ana"
    assert cliente.get(ME, headers=_auth(t_luis)).json()["nombre"] == "Luis"


# ---------------------------------------------------------------- actualizar el propio perfil (PATCH /auth/me)

def _sesion(cliente, usuario="dra.ana", **cambios):
    _registrar(cliente, nombre_de_usuario=usuario, **cambios)
    return _auth(_token(cliente, usuario))


def test_actualizar_perfil_cambia_solo_lo_enviado(entorno):
    cliente, Sesion = entorno
    h = _sesion(cliente)
    r = cliente.patch(ME, json={"ciudad": "Puebla", "apellidos": "  Pérez  "}, headers=h)
    assert r.status_code == 200
    assert r.json() == {"id": 1, "nombre": "Ana", "apellidos": "Pérez", "ciudad": "Puebla",
                        "nombre_de_usuario": "dra.ana"}
    assert cliente.get(ME, headers=h).json()["ciudad"] == "Puebla"
    with Sesion() as db:
        assert db.scalar(select(Medico)).efirma == "firma-demo-abc123"  # lo no enviado no se toca


def test_actualizar_efirma_no_se_devuelve_pero_se_guarda(entorno):
    cliente, Sesion = entorno
    h = _sesion(cliente)
    r = cliente.patch(ME, json={"efirma": "firma-nueva"}, headers=h)
    assert r.status_code == 200 and "efirma" not in r.json()
    with Sesion() as db:
        assert db.scalar(select(Medico)).efirma == "firma-nueva"


def test_cambiar_el_nombre_de_usuario_mantiene_la_sesion_y_el_login_nuevo(cliente):
    h = _sesion(cliente)
    r = cliente.patch(ME, json={"nombre_de_usuario": "Doctora.Ana"}, headers=h)
    assert r.status_code == 200 and r.json()["nombre_de_usuario"] == "doctora.ana"  # en minúsculas
    assert cliente.get(ME, headers=h).status_code == 200  # el token identifica por id
    assert cliente.post(LOGIN, json={"nombre_de_usuario": "dra.ana", "password": MEDICO["password"]}).status_code == 401
    assert _token(cliente, "doctora.ana")


def test_nombre_de_usuario_ocupado_da_409_y_no_cambia_nada(cliente):
    _registrar(cliente, nombre_de_usuario="luis")
    h = _sesion(cliente)
    r = cliente.patch(ME, json={"nombre": "Otra", "nombre_de_usuario": "LUIS"}, headers=h)
    assert r.status_code == 409
    perfil = cliente.get(ME, headers=h).json()
    assert perfil["nombre"] == "Ana" and perfil["nombre_de_usuario"] == "dra.ana"


def test_conservar_el_mismo_nombre_de_usuario_no_es_conflicto(cliente):
    h = _sesion(cliente)
    assert cliente.patch(ME, json={"nombre_de_usuario": "Dra.Ana", "ciudad": "León"}, headers=h).status_code == 200


def test_actualizar_perfil_exige_sesion(cliente):
    _sesion(cliente)
    assert cliente.patch(ME, json={"ciudad": "Puebla"}).status_code == 401
    assert cliente.patch(ME, json={"ciudad": "Puebla"}, headers=_auth("token-falso")).status_code == 401


def test_un_medico_solo_edita_su_propio_perfil(cliente):
    h_ana = _sesion(cliente)
    h_luis = _sesion(cliente, "luis", nombre="Luis")
    cliente.patch(ME, json={"ciudad": "Puebla"}, headers=h_luis)
    assert cliente.get(ME, headers=h_ana).json()["ciudad"] == "Morelia"  # Ana no cambió
    assert cliente.get(ME, headers=h_luis).json()["ciudad"] == "Puebla"


def test_el_id_no_se_puede_enviar_para_editar_a_otro(cliente):
    _registrar(cliente, nombre_de_usuario="luis")
    h = _sesion(cliente)
    r = cliente.patch(ME, json={"id": 1, "ciudad": "Puebla"}, headers=h)  # campo desconocido: se ignora
    assert r.status_code == 200 and r.json()["id"] == 2
    assert cliente.get(ME, headers=_auth(_token(cliente, "luis"))).json()["ciudad"] == "Morelia"


@pytest.mark.parametrize("cuerpo", [
    {}, {"nombre": None}, {"ciudad": ""}, {"nombre": "   "}, {"nombre_de_usuario": "ab"},
    {"nombre_de_usuario": "con espacio"}, {"apellidos": "x" * 151}, {"efirma": None},
])
def test_actualizar_perfil_rechaza_datos_invalidos(cliente, cuerpo):
    h = _sesion(cliente)
    assert cliente.patch(ME, json=cuerpo, headers=h).status_code == 422


# ---------------------------------------------------------------- cambiar la contraseña (PUT /auth/me/password)

PASSWORD = f"{ME}/password"
NUEVA = "Otra-clave-456"


def test_cambiar_password_con_la_actual(entorno):
    cliente, Sesion = entorno
    h = _sesion(cliente)
    r = cliente.put(PASSWORD, json={"password_actual": MEDICO["password"], "password_nueva": NUEVA}, headers=h)
    assert r.status_code == 204 and r.content == b""
    assert cliente.post(LOGIN, json={"nombre_de_usuario": "dra.ana", "password": MEDICO["password"]}).status_code == 401
    assert _token(cliente, "dra.ana", NUEVA)
    with Sesion() as db:
        guardado = db.scalar(select(Medico)).password
        assert guardado.startswith("$argon2id$") and NUEVA not in guardado


def test_password_actual_incorrecta_da_400_y_no_cambia_nada(cliente):
    h = _sesion(cliente)
    r = cliente.put(PASSWORD, json={"password_actual": "no-es-esta-123", "password_nueva": NUEVA}, headers=h)
    assert r.status_code == 400  # no 401: el frontend lo tomaría por sesión vencida
    assert cliente.get(ME, headers=h).status_code == 200
    assert _token(cliente, "dra.ana", MEDICO["password"])


def test_cambiar_password_exige_sesion(cliente):
    _sesion(cliente)
    r = cliente.put(PASSWORD, json={"password_actual": MEDICO["password"], "password_nueva": NUEVA})
    assert r.status_code == 401


@pytest.mark.parametrize("cuerpo", [
    {"password_actual": MEDICO["password"], "password_nueva": "corta"},
    {"password_actual": MEDICO["password"], "password_nueva": MEDICO["password"]},
    {"password_actual": "", "password_nueva": NUEVA},
    {"password_nueva": NUEVA},
])
def test_cambiar_password_rechaza_datos_invalidos(cliente, cuerpo):
    h = _sesion(cliente)
    assert cliente.put(PASSWORD, json=cuerpo, headers=h).status_code == 422


def test_adivinar_la_password_actual_se_limita_con_429(cliente):
    h = _sesion(cliente)
    malo = {"password_actual": "no-es-esta-123", "password_nueva": NUEVA}
    for _ in range(settings.intentos_max_por_cuenta):
        assert cliente.put(PASSWORD, json=malo, headers=h).status_code == 400
    r = cliente.put(PASSWORD, json=malo, headers=h)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    # bloqueado también con la contraseña correcta, igual que el login
    bueno = {"password_actual": MEDICO["password"], "password_nueva": NUEVA}
    assert cliente.put(PASSWORD, json=bueno, headers=h).status_code == 429
