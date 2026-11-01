from fastapi import APIRouter

from app.api.v1.routers import auth, citas, ml, pacientes

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(pacientes.router, prefix="/pacientes", tags=["pacientes"])
api_router.include_router(citas.router, prefix="/citas", tags=["citas"])
api_router.include_router(ml.router, prefix="/ml", tags=["ml"])

# A medida que se implementen, se registran aquí (consultas, historial, dashboard).
