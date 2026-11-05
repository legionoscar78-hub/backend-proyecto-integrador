"""Pegamento entre el límite de intentos (app/core/limites.py) y las respuestas HTTP.

Cada intento fallido cuenta contra dos claves: la IP de quien lo hizo y una "cuenta" (el usuario que
se intentó adivinar, o el médico que prueba llaves). Un acierto solo reinicia la clave de cuenta: si
también reiniciara la de la IP, bastaría iniciar sesión con una cuenta propia entre intentos para
saltarse el límite."""
from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.limites import LimiteIntentos


def ip_cliente(request: Request) -> str:
    return request.client.host if request.client else "desconocida"


def _claves(ip: str, cuenta: str) -> tuple[str, str]:
    return f"ip:{ip}", f"cuenta:{cuenta}"


def exigir_sin_bloqueo(limite: LimiteIntentos, ip: str, cuenta: str) -> None:
    """Responde 429 (con Retry-After) si la IP o la cuenta ya agotaron sus intentos."""
    clave_ip, clave_cuenta = _claves(ip, cuenta)
    espera = max(
        limite.espera(clave_ip, settings.intentos_max_por_ip),
        limite.espera(clave_cuenta, settings.intentos_max_por_cuenta),
    )
    if espera:
        minutos = -(-espera // 60)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos fallidos. Intenta de nuevo en {minutos} minuto{'s' if minutos != 1 else ''}",
            headers={"Retry-After": str(espera)},
        )


def registrar_fallo(limite: LimiteIntentos, ip: str, cuenta: str) -> None:
    for clave in _claves(ip, cuenta):
        limite.fallo(clave)


def registrar_acierto(limite: LimiteIntentos, ip: str, cuenta: str) -> None:
    limite.reiniciar(_claves(ip, cuenta)[1])
