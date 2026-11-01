from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_medico, get_db
from app.models.medico import Medico
from app.models.paciente import Paciente
from app.schemas.comunes import LIMITE_MAXIMO, LIMITE_POR_DEFECTO, Pagina
from app.schemas.paciente import PacienteActualizar, PacienteCrear, PacienteSalida
from app.services import paciente_service as servicio

# Todos los endpoints exigen sesión de médico
router = APIRouter(dependencies=[Depends(get_current_medico)])

NO_ENCONTRADO = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente no encontrado")
CURP_REPETIDA = HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe un paciente con esa CURP")


@router.post(
    "",
    response_model=PacienteSalida,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "La CURP ya está registrada"}},
)
def crear_paciente(datos: PacienteCrear, db: Session = Depends(get_db)) -> Paciente:
    try:
        return servicio.crear(db, datos)
    except servicio.CurpYaRegistrada:
        raise CURP_REPETIDA


@router.get("", response_model=Pagina[PacienteSalida])
def listar_pacientes(
    buscar: str | None = Query(None, max_length=100, description="Palabras a buscar en nombre, apellidos o CURP"),
    limit: int = Query(LIMITE_POR_DEFECTO, ge=1, le=LIMITE_MAXIMO),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Pagina[PacienteSalida]:
    """Pacientes ordenados por apellidos. Cada palabra de `buscar` debe aparecer en el nombre, los apellidos o la CURP."""
    items, total = servicio.listar(db, buscar, limit, offset)
    return Pagina[PacienteSalida](
        items=[PacienteSalida.model_validate(p) for p in items], total=total, limit=limit, offset=offset
    )


@router.get("/{paciente_id}", response_model=PacienteSalida, responses={404: {"description": "No existe"}})
def obtener_paciente(paciente_id: int, db: Session = Depends(get_db)) -> Paciente:
    try:
        return servicio.obtener(db, paciente_id)
    except servicio.PacienteNoEncontrado:
        raise NO_ENCONTRADO


@router.patch(
    "/{paciente_id}",
    response_model=PacienteSalida,
    responses={404: {"description": "No existe"}, 409: {"description": "La CURP ya está registrada"}},
)
def actualizar_paciente(paciente_id: int, datos: PacienteActualizar, db: Session = Depends(get_db)) -> Paciente:
    """Cambia solo los campos enviados. Teléfono, tipo de sangre y notas se borran enviándolos como null."""
    try:
        return servicio.actualizar(db, paciente_id, datos)
    except servicio.PacienteNoEncontrado:
        raise NO_ENCONTRADO
    except servicio.CurpYaRegistrada:
        raise CURP_REPETIDA


@router.delete(
    "/{paciente_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "No existe"}, 409: {"description": "Tiene citas o consultas"}},
)
def eliminar_paciente(paciente_id: int, db: Session = Depends(get_db)) -> Response:
    """Solo se puede borrar un paciente que no tenga citas ni consultas."""
    try:
        servicio.eliminar(db, paciente_id)
    except servicio.PacienteNoEncontrado:
        raise NO_ENCONTRADO
    except servicio.PacienteConRegistros:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El paciente tiene citas o consultas registradas y no se puede borrar",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
