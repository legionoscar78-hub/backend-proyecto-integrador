from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_medico, get_db
from app.models.medico import Medico
from app.schemas.auth import LoginEntrada, MedicoSalida, RegistroEntrada, TokenSalida
from app.services import auth_service

router = APIRouter()


@router.post(
    "/registro",
    response_model=MedicoSalida,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "El nombre de usuario ya está en uso"}},
)
def registro(datos: RegistroEntrada, db: Session = Depends(get_db)) -> Medico:
    """Crea la cuenta de un médico. La contraseña se guarda con hash argon2."""
    try:
        return auth_service.registrar(db, datos)
    except auth_service.UsuarioYaExiste:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El nombre de usuario ya está en uso")


@router.post(
    "/login",
    response_model=TokenSalida,
    responses={401: {"description": "Usuario o contraseña incorrectos"}},
)
def login(datos: LoginEntrada, db: Session = Depends(get_db)) -> TokenSalida:
    """Devuelve un token para enviar como `Authorization: Bearer <token>`."""
    try:
        token, segundos = auth_service.iniciar_sesion(db, datos)
    except auth_service.CredencialesInvalidas:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenSalida(access_token=token, expires_in=segundos)


@router.get("/me", response_model=MedicoSalida)
def me(medico: Medico = Depends(get_current_medico)) -> Medico:
    """Perfil del médico que inició sesión."""
    return medico
