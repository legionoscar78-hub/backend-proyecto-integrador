from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_medico, get_db
from app.models.consulta import Consulta
from app.models.medico import Medico
from app.schemas.comunes import LIMITE_MAXIMO, LIMITE_POR_DEFECTO, Pagina
from app.schemas.consulta import AccesoPorLlave, ConsultaActualizar, ConsultaCrear, ConsultaSalida
from app.services import consulta_service as servicio
from app.services.paciente_service import PacienteNoEncontrado

# Todos los endpoints exigen sesión de médico y solo ven las consultas de ese médico.
# No hay DELETE: las consultas forman parte del expediente del paciente. Las de otros médicos solo se
# abren con su llave (POST /acceso), en solo lectura.
router = APIRouter()

NO_ENCONTRADA = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consulta no encontrada")
PACIENTE_NO_ENCONTRADO = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="El paciente no existe")
ENFERMEDAD_NO_ENCONTRADA = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="La enfermedad del diagnóstico no existe en el catálogo"
)


@router.post(
    "",
    response_model=ConsultaSalida,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"description": "El paciente o la enfermedad no existen"}},
)
def registrar_consulta(
    datos: ConsultaCrear, medico: Medico = Depends(get_current_medico), db: Session = Depends(get_db)
) -> Consulta:
    """Registra una consulta con el diagnóstico que confirma el médico (`enfermedad_id`, del catálogo o de una
    sugerencia de /ml/predecir). La edad se calcula con la fecha de nacimiento del paciente. Se genera una `llave`
    de acceso que el médico le entrega al paciente: con ella, otro médico podrá ver esta consulta."""
    try:
        return servicio.crear(db, medico, datos)
    except PacienteNoEncontrado:
        raise PACIENTE_NO_ENCONTRADO
    except servicio.EnfermedadNoEncontrada:
        raise ENFERMEDAD_NO_ENCONTRADA
    except servicio.NoSePudoGenerarLlave:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No se pudo generar la llave. Intenta de nuevo")


@router.post(
    "/acceso",
    response_model=ConsultaSalida,
    responses={404: {"description": "La llave no corresponde a ninguna consulta"}},
)
def consultar_con_llave(
    datos: AccesoPorLlave, _: Medico = Depends(get_current_medico), db: Session = Depends(get_db)
) -> Consulta:
    """Abre (solo lectura) una consulta de otro médico con la llave que le dio el paciente. La llave va en el cuerpo
    y no en la URL para que no quede en los registros del servidor. Acepta minúsculas, espacios o sin guiones."""
    try:
        return servicio.obtener_por_llave(db, datos.llave)
    except servicio.LlaveInvalida:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La llave no corresponde a ninguna consulta")


@router.get("", response_model=Pagina[ConsultaSalida])
def listar_consultas(
    paciente_id: int | None = Query(None, gt=0, description="Historial de un paciente"),
    enfermedad_id: int | None = Query(None, gt=0),
    desde: date | None = Query(None, description="Desde esta fecha (incluida)"),
    hasta: date | None = Query(None, description="Hasta esta fecha (incluida, todo el día)"),
    limit: int = Query(LIMITE_POR_DEFECTO, ge=1, le=LIMITE_MAXIMO),
    offset: int = Query(0, ge=0),
    medico: Medico = Depends(get_current_medico),
    db: Session = Depends(get_db),
) -> Pagina[ConsultaSalida]:
    """Consultas del médico, de la más reciente a la más antigua."""
    if desde and hasta and desde > hasta:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="`desde` no puede ser posterior a `hasta`")
    items, total = servicio.listar(db, medico, paciente_id, enfermedad_id, desde, hasta, limit, offset)
    return Pagina[ConsultaSalida](
        items=[ConsultaSalida.model_validate(c) for c in items], total=total, limit=limit, offset=offset
    )


@router.get("/{consulta_id}", response_model=ConsultaSalida, responses={404: {"description": "No existe o es de otro médico"}})
def obtener_consulta(
    consulta_id: int, medico: Medico = Depends(get_current_medico), db: Session = Depends(get_db)
) -> Consulta:
    try:
        return servicio.obtener(db, medico, consulta_id)
    except servicio.ConsultaNoEncontrada:
        raise NO_ENCONTRADA


@router.patch(
    "/{consulta_id}",
    response_model=ConsultaSalida,
    responses={404: {"description": "No existe, es de otro médico o la enfermedad no existe"}},
)
def corregir_consulta(
    consulta_id: int, datos: ConsultaActualizar,
    medico: Medico = Depends(get_current_medico), db: Session = Depends(get_db),
) -> Consulta:
    """Corrige el diagnóstico, el peso, la altura o las notas. El paciente, la edad, la fecha y el folio no cambian."""
    try:
        return servicio.actualizar(db, medico, consulta_id, datos)
    except servicio.ConsultaNoEncontrada:
        raise NO_ENCONTRADA
    except servicio.EnfermedadNoEncontrada:
        raise ENFERMEDAD_NO_ENCONTRADA
