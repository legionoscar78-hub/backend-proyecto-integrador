from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api import limites_http
from app.api.deps import get_current_medico, get_db
from app.core.limites import intentos_login
from app.models.medico import Medico
from app.schemas.auth import CambioPassword, LoginEntrada, MedicoActualizar, MedicoSalida, RegistroEntrada, TokenSalida
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
    responses={
        401: {"description": "Usuario o contraseña incorrectos"},
        429: {"description": "Demasiados intentos fallidos: hay que esperar (cabecera Retry-After)"},
    },
)
def login(datos: LoginEntrada, request: Request, db: Session = Depends(get_db)) -> TokenSalida:
    """Devuelve un token para enviar como `Authorization: Bearer <token>`.

    Límite de intentos: tras 5 fallos con el mismo usuario desde la misma IP (o 20 desde una misma IP
    con cualquier usuario) responde 429 durante 15 minutos, aunque la contraseña ya sea la correcta.
    Un inicio de sesión correcto reinicia el contador de ese usuario."""
    ip = limites_http.ip_cliente(request)
    cuenta = f"{ip}|{datos.nombre_de_usuario.lower()}"
    limites_http.exigir_sin_bloqueo(intentos_login, ip, cuenta)
    try:
        token, segundos = auth_service.iniciar_sesion(db, datos)
    except auth_service.CredencialesInvalidas:
        limites_http.registrar_fallo(intentos_login, ip, cuenta)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    limites_http.registrar_acierto(intentos_login, ip, cuenta)
    return TokenSalida(access_token=token, expires_in=segundos)


@router.get("/me", response_model=MedicoSalida)
def me(medico: Medico = Depends(get_current_medico)) -> Medico:
    """Perfil del médico que inició sesión."""
    return medico


@router.patch(
    "/me",
    response_model=MedicoSalida,
    responses={409: {"description": "El nombre de usuario ya está en uso"}},
)
def actualizar_me(
    datos: MedicoActualizar, medico: Medico = Depends(get_current_medico), db: Session = Depends(get_db)
) -> Medico:
    """Actualiza (parcialmente) el perfil del médico que inició sesión: nombre, apellidos, ciudad, efirma y
    nombre de usuario. No hay forma de editar a otro médico: el id sale siempre del token.
    El token sigue siendo válido aunque cambie el nombre de usuario (identifica por id)."""
    try:
        return auth_service.actualizar_perfil(db, medico, datos)
    except auth_service.UsuarioYaExiste:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El nombre de usuario ya está en uso")


@router.put(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        400: {"description": "La contraseña actual no es correcta"},
        429: {"description": "Demasiados intentos fallidos con la contraseña actual"},
    },
)
def cambiar_password(
    datos: CambioPassword,
    request: Request,
    medico: Medico = Depends(get_current_medico),
    db: Session = Depends(get_db),
) -> None:
    """Cambia la contraseña del médico de la sesión; hay que enviar la actual. Responde 400 (no 401, que
    significa "sesión vencida") si la actual es incorrecta. Cuenta contra el mismo límite de intentos del
    login (5 fallos -> 429), para que quien use una sesión ajena no pueda adivinar la contraseña."""
    ip = limites_http.ip_cliente(request)
    cuenta = f"cambio-password|{medico.id}"
    limites_http.exigir_sin_bloqueo(intentos_login, ip, cuenta)
    try:
        auth_service.cambiar_password(db, medico, datos)
    except auth_service.CredencialesInvalidas:
        limites_http.registrar_fallo(intentos_login, ip, cuenta)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La contraseña actual no es correcta")
    limites_http.registrar_acierto(intentos_login, ip, cuenta)
