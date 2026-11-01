from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_medico, get_db
from app.ml.predictor import ModeloNoDisponible
from app.schemas.catalogo import EnfermedadDetalleSalida, EnfermedadSalida, SintomaSalida
from app.schemas.comunes import LIMITE_MAXIMO, LIMITE_POR_DEFECTO, Pagina
from app.services import catalogo_service as servicio
from app.services.consulta_service import EnfermedadNoEncontrada

# Todos los endpoints exigen sesión de médico
router = APIRouter(dependencies=[Depends(get_current_medico)])


@router.get("/enfermedades", response_model=Pagina[EnfermedadSalida])
def listar_enfermedades(
    buscar: str | None = Query(None, max_length=100, description="Palabras a buscar en el nombre"),
    limit: int = Query(LIMITE_POR_DEFECTO, ge=1, le=LIMITE_MAXIMO),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Pagina[EnfermedadSalida]:
    """Enfermedades del catálogo, ordenadas por nombre. Su `id` es el que se envía como `enfermedad_id` en una consulta."""
    items, total = servicio.listar_enfermedades(db, buscar, limit, offset)
    return Pagina[EnfermedadSalida](
        items=[EnfermedadSalida.model_validate(e) for e in items], total=total, limit=limit, offset=offset
    )


@router.get("/enfermedades/{enfermedad_id}", response_model=EnfermedadDetalleSalida,
            responses={404: {"description": "No existe"}})
def obtener_enfermedad(enfermedad_id: int, db: Session = Depends(get_db)) -> EnfermedadDetalleSalida:
    """Una enfermedad con los síntomas que el catálogo le asocia."""
    try:
        enfermedad, del_modelo = servicio.obtener_enfermedad(db, enfermedad_id)
    except EnfermedadNoEncontrada:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enfermedad no encontrada")
    return EnfermedadDetalleSalida(
        id=enfermedad.id, nombre=enfermedad.nombre, descripcion=enfermedad.descripcion,
        sintomas=[
            SintomaSalida(id=s.id, nombre=s.nombre, usado_por_el_modelo=s.nombre in (del_modelo or ()))
            for s in enfermedad.sintomas
        ],
    )


@router.get(
    "/sintomas",
    response_model=Pagina[SintomaSalida],
    responses={503: {"description": "Se pidió solo_modelo y el modelo no está disponible"}},
)
def listar_sintomas(
    buscar: str | None = Query(None, max_length=100, description="Palabras a buscar en el nombre"),
    solo_modelo: bool = Query(False, description="Solo los síntomas que el modelo de predicción entiende"),
    limit: int = Query(LIMITE_POR_DEFECTO, ge=1, le=LIMITE_MAXIMO),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Pagina[SintomaSalida]:
    """Síntomas del catálogo, ordenados por nombre. Sus nombres son los que acepta /ml/predecir."""
    try:
        items, total, del_modelo = servicio.listar_sintomas(db, buscar, solo_modelo, limit, offset)
    except ModeloNoDisponible as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))
    return Pagina[SintomaSalida](
        items=[SintomaSalida(id=s.id, nombre=s.nombre, usado_por_el_modelo=s.nombre in (del_modelo or ())) for s in items],
        total=total, limit=limit, offset=offset,
    )
