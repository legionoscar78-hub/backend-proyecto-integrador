"""App completa sobre SQLite en memoria (todas las tablas, con claves foráneas activas) y ayudantes
para crear médicos con sesión. Así las pruebas recorren el mismo camino que una petición real."""
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  registra todas las tablas
from app.api.deps import get_db
from app.api.v1.api import api_router
from app.core.database import Base
from datos import dias, paciente_json


class Api:
    def __init__(self, cliente: TestClient, sesion):
        self.cliente, self.Sesion = cliente, sesion

    def medico(self, usuario: str = "dra.ana") -> dict:
        """Registra al médico (si no existe), inicia sesión y devuelve la cabecera Authorization."""
        datos = {"nombre": "Ana", "apellidos": "López", "ciudad": "Morelia", "efirma": "firma",
                 "nombre_de_usuario": usuario, "password": "Clave-segura-123"}
        self.cliente.post("/api/v1/auth/registro", json=datos)
        r = self.cliente.post("/api/v1/auth/login", json={"nombre_de_usuario": usuario, "password": datos["password"]})
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def paciente(self, headers: dict, n: int = 0, **cambios) -> dict:
        r = self.cliente.post("/api/v1/pacientes", json=paciente_json(n, **cambios), headers=headers)
        assert r.status_code == 201, r.text
        return r.json()

    def cita(self, headers: dict, paciente_id: int, fecha: str | None = None, hora: str = "10:00") -> dict:
        r = self.cliente.post("/api/v1/citas", headers=headers,
                              json={"paciente_id": paciente_id, "fecha_cita": fecha or dias(1), "hora_cita": hora})
        assert r.status_code == 201, r.text
        return r.json()


def _motor():
    """SQLite en memoria por defecto. Con TEST_DATABASE_URL las mismas pruebas corren contra PostgreSQL
    (la base debe llamarse con 'test': se vacían todas sus tablas en cada prueba)."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        motor = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

        @event.listens_for(motor, "connect")
        def _claves_foraneas(conexion, _):  # SQLite no las exige salvo que se pida
            conexion.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(motor)
        return motor

    motor = create_engine(url)
    if "test" not in (motor.url.database or "").lower():
        pytest.exit(f"TEST_DATABASE_URL apunta a '{motor.url.database}': por seguridad el nombre debe contener 'test'")
    Base.metadata.create_all(motor)
    tablas = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with motor.begin() as conexion:
        conexion.execute(text(f"TRUNCATE {tablas} RESTART IDENTITY CASCADE"))
    return motor


@pytest.fixture
def api():
    motor = _motor()
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
    yield Api(TestClient(app), Sesion)
    motor.dispose()
