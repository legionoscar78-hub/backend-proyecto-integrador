from fastapi import APIRouter

from app.api.v1.routers import auth, catalogo, citas, consultas, ml, pacientes

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(pacientes.router, prefix="/pacientes", tags=["pacientes"])
api_router.include_router(citas.router, prefix="/citas", tags=["citas"])
api_router.include_router(consultas.router, prefix="/consultas", tags=["consultas"])
api_router.include_router(catalogo.router, prefix="/catalogo", tags=["catálogo"])
api_router.include_router(ml.router, prefix="/ml", tags=["ml"])

# A medida que se implementen, se registran aquí (historial, dashboard).
