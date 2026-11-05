"""Variables de entorno para las pruebas, antes de que se importe app.core.config.

Las pruebas no se conectan a ninguna base de datos real: solo necesitan que Settings se pueda crear.
La clave JWT es siempre la de prueba, para que no dependa de la que haya en tu .env.
"""
import os
from pathlib import Path

ENV = Path(__file__).resolve().parents[1] / ".env"
_definidas_en_env = ENV.read_text(encoding="utf-8").lower() if ENV.exists() else ""

os.environ["JWT_SECRET"] = "clave-de-prueba-solo-para-pytest-0123456789"
os.environ.pop("ACCESS_TOKEN_MINUTES", None)
for variable in ("DB_NAME", "DB_USER", "DB_PASSWORD"):
    if variable not in os.environ and f"{variable.lower()}=" not in _definidas_en_env:
        os.environ[variable] = "prueba"


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _contadores_de_intentos_en_cero():
    """El límite de intentos vive en memoria y es global: sin esto, los fallos de una prueba
    contarían en la siguiente."""
    from app.core.limites import intentos_llave, intentos_login

    intentos_login.limpiar()
    intentos_llave.limpiar()
    yield
