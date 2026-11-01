from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_medico, get_db
from app.models.cita import Cita
from app.models.medico import Medico
from app.schemas.cita import CitaActualizar, CitaCrear, CitaSalida
from app.schemas.comunes import LIMITE_MAXIMO, LIMITE_POR_DEFECTO, Pagina
from app.services import cita_service as servicio
from app.services.paciente_service import PacienteNoEncontrado

# Todos los endpoints exigen sesión de médico y solo ven las citas de ese médico
router = APIRouter()

CITA_NO_ENCONTRADA = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cita no encontrada")
PACIENTE_NO_ENCONTRADO = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="El paciente no existe")
HORARIO_OCUPADO = HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya tienes una cita a esa fecha y hora")
FECHA_PASADA = HTTPException(
    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="No se puede agendar una cita en una fecha pasada"
)


@router.post(
    "",
    response_model=CitaSalida,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"description": "El paciente no existe"}, 409: {"description": "Horario ocupado"}},
)
def agendar_cita(
    datos: CitaCrear, medico: Medico = Depends(get_current_medico), db: Session = Depends(get_db)
) -> Cita:
    """Agenda una cita del médico con sesión. La hora se guarda sin segundos."""
    try:
        return servicio.agendar(db, medico, datos)
    except PacienteNoEncontrado:
        raise PACIENTE_NO_ENCONTRADO
    except servicio.HorarioOcupado:
        raise HORARIO_OCUPADO
    except servicio.FechaEnElPasado:
        raise FECHA_PASADA


@router.get("", response_model=Pagina[CitaSalida])
def listar_citas(
    desde: date | None = Query(None, description="Desde esta fecha (incluida)"),
    hasta: date | None = Query(None, description="Hasta esta fecha (incluida)"),
    paciente_id: int | None = Query(None, gt=0),
    limit: int = Query(LIMITE_POR_DEFECTO, ge=1, le=LIMITE_MAXIMO),
    offset: int = Query(0, ge=0),
    medico: Medico = Depends(get_current_medico),
    db: Session = Depends(get_db),
) -> Pagina[CitaSalida]:
    """Citas del médico, de la más próxima a la más lejana. Para un solo día, usa el mismo valor en desde y hasta."""
    if desde and hasta and desde > hasta:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="`desde` no puede ser posterior a `hasta`")
    items, total = servicio.listar(db, medico, desde, hasta, paciente_id, limit, offset)
    return Pagina[CitaSalida](
        items=[CitaSalida.model_validate(c) for c in items], total=total, limit=limit, offset=offset
    )


@router.get("/{cita_id}", response_model=CitaSalida, responses={404: {"description": "No existe o es de otro médico"}})
def obtener_cita(cita_id: int, medico: Medico = Depends(get_current_medico), db: Session = Depends(get_db)) -> Cita:
    try:
        return servicio.obtener(db, medico, cita_id)
    except servicio.CitaNoEncontrada:
        raise CITA_NO_ENCONTRADA


@router.patch(
    "/{cita_id}",
    response_model=CitaSalida,
    responses={404: {"description": "No existe o el paciente no existe"}, 409: {"description": "Horario ocupado"}},
)
def actualizar_cita(
    cita_id: int, datos: CitaActualizar, medico: Medico = Depends(get_current_medico), db: Session = Depends(get_db)
) -> Cita:
    """Reprograma la cita o le cambia el paciente. Solo cambia lo que se envía."""
    try:
        return servicio.actualizar(db, medico, cita_id, datos)
    except servicio.CitaNoEncontrada:
        raise CITA_NO_ENCONTRADA
    except PacienteNoEncontrado:
        raise PACIENTE_NO_ENCONTRADO
    except servicio.HorarioOcupado:
        raise HORARIO_OCUPADO
    except servicio.FechaEnElPasado:
        raise FECHA_PASADA


@router.delete("/{cita_id}", status_code=status.HTTP_204_NO_CONTENT, responses={404: {"description": "No existe"}})
def cancelar_cita(cita_id: int, medico: Medico = Depends(get_current_medico), db: Session = Depends(get_db)) -> Response:
    """Cancela (borra) la cita."""
    try:
        servicio.cancelar(db, medico, cita_id)
    except servicio.CitaNoEncontrada:
        raise CITA_NO_ENCONTRADA
    return Response(status_code=status.HTTP_204_NO_CONTENT)
