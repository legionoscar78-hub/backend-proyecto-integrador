from collections.abc import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import TokenInvalido, leer_token
from app.models.medico import Medico
from app.repositories import medico_repo

# auto_error=False: así la respuesta sin credenciales es 401 (con WWW-Authenticate) y no el 403 por defecto
esquema_bearer = HTTPBearer(auto_error=False, description="Token que devuelve POST /api/v1/auth/login")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_medico(
    credenciales: HTTPAuthorizationCredentials | None = Depends(esquema_bearer),
    db: Session = Depends(get_db),
) -> Medico:
    """El médico de la sesión. Responde 401 si falta el token, es inválido, expiró o el médico ya no existe."""
    no_autenticado = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No autenticado o sesión expirada",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credenciales is None:
        raise no_autenticado
    try:
        medico_id = leer_token(credenciales.credentials)
    except TokenInvalido:
        raise no_autenticado
    medico = medico_repo.obtener_por_id(db, medico_id)
    if medico is None:
        raise no_autenticado
    return medico
