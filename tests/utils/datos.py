"""Datos de prueba para los endpoints (CURP válidas, pacientes y fechas relativas a hoy)."""
from datetime import date, timedelta

LETRAS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def curp(n: int) -> str:
    """CURP con formato válido y distinta para cada n (hasta 676 * 10)."""
    return f"{LETRAS[n % 26]}{LETRAS[(n // 26) % 26]}CD900101HDFBCD{(n // 676) % 10}1"


def paciente_json(n: int = 0, **cambios) -> dict:
    datos = {
        "nombre": f"Paciente{n}", "apellidos": f"Apellido{n}", "curp": curp(n), "fecha_nacimiento": "1990-05-17",
        "numero_telefonico": "4431234567", "sexo": "M", "tipo_de_sangre": "O+", "notas": "sin alergias",
    }
    return {**datos, **cambios}


def dias(n: int) -> str:
    """Fecha ISO de dentro de n días (las citas no pueden estar en el pasado)."""
    return (date.today() + timedelta(days=n)).isoformat()
