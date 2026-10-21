from fastapi import APIRouter

from app.api.v1.routers import ml

api_router = APIRouter()
api_router.include_router(ml.router, prefix="/ml", tags=["ml"])

# A medida que se implementen, se registran aquí (pacientes, consultas, historial, dashboard, auth).
