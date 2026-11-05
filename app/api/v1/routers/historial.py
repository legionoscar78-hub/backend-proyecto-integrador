from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_medico, get_db
from app.models.medico import Medico
from app.schemas.comunes import LIMITE_MAXIMO, LIMITE_POR_DEFECTO, Pagina
from app.schemas.consulta import ConsultaSalida
from app.schemas.historial import HistorialSalida
from app.schemas.paciente import PacienteSalida
from app.services import historial_service as servicio
from app.services.paciente_service import PacienteNoEncontrado

# Exige sesión de médico. Cualquier médico puede abrir el historial de cualquier paciente, pero solo ve en él
# las consultas que hizo él mismo; las de otros médicos se abren con su llave (POST /consultas/acceso).
router = APIRouter()


@router.get(
    "/{paciente_id}",
    response_model=HistorialSalida,
    responses={404: {"description": "El paciente no existe"}},
)
def historial_del_paciente(
    paciente_id: int,
    desde: date | None = Query(None, description="Desde esta fecha (incluida)"),
    hasta: date | None = Query(None, description="Hasta esta fecha (incluida, todo el día)"),
    limit: int = Query(LIMITE_POR_DEFECTO, ge=1, le=LIMITE_MAXIMO),
    offset: int = Query(0, ge=0),
    medico: Medico = Depends(get_current_medico),
    db: Session = Depends(get_db),
) -> HistorialSalida:
    """Datos del paciente y las consultas que el médico de la sesión le ha hecho, de la más reciente a la más antigua."""
    if desde and hasta and desde > hasta:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="`desde` no puede ser posterior a `hasta`")
    try:
        paciente, consultas, total = servicio.obtener(db, medico, paciente_id, desde, hasta, limit, offset)
    except PacienteNoEncontrado:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente no encontrado")
    return HistorialSalida(
        paciente=PacienteSalida.model_validate(paciente),
        consultas=Pagina[ConsultaSalida](
            items=[ConsultaSalida.model_validate(c) for c in consultas], total=total, limit=limit, offset=offset
        ),
    )
