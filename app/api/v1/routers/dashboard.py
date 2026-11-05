from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_medico, get_db
from app.schemas.dashboard import DashboardSalida
from app.services import dashboard_service as servicio

# Exige sesión de médico. A diferencia de las consultas, que son de cada médico, el dashboard resume las
# de todos (solo conteos, sin datos de pacientes), porque compara regiones.
router = APIRouter(dependencies=[Depends(get_current_medico)])


@router.get("", response_model=DashboardSalida)
def dashboard(
    anio: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100, description="Año a resumir (por defecto, el actual)"),
    db: Session = Depends(get_db),
) -> DashboardSalida:
    """Tres vistas de las consultas del año:
    1. `top_por_mes`: las 5 enfermedades más diagnosticadas de cada mes.
    2. `total_anual_por_region`: casos del año, por región, de las 5 enfermedades más diagnosticadas del año (`top_anual`).
    3. `casos_mensuales_por_region`: casos de esas mismas 5, mes a mes, por región.

    La región es la ciudad del médico que atendió."""
    return servicio.estadisticas(db, anio)
