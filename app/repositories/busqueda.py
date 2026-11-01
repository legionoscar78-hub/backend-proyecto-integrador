"""Búsqueda por palabras, compartida por los repositories."""
from sqlalchemy import or_

MAX_PALABRAS_BUSQUEDA = 5


def patron_like(palabra: str) -> str:
    """LIKE '%palabra%' con los comodines que escriba el usuario (% y _) tratados como texto."""
    escapada = palabra.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escapada}%"


def filtro_por_palabras(buscar: str | None, columnas: list) -> list:
    """Una condición por palabra: debe aparecer en alguna de las columnas (sin distinguir
    mayúsculas; los acentos sí cuentan). Sin texto, no hay condiciones."""
    return [
        or_(*(columna.ilike(patron_like(palabra), escape="\\") for columna in columnas))
        for palabra in (buscar or "").split()[:MAX_PALABRAS_BUSQUEDA]
    ]
