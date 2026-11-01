from datetime import date


def calcular_edad(nacimiento: date, hoy: date | None = None) -> int:
    """Años cumplidos a la fecha `hoy` (por defecto, hoy)."""
    hoy = hoy or date.today()
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))
