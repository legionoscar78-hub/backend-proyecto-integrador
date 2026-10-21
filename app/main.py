from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.v1.api import api_router
from app.ml import predictor


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Carga el modelo una vez. Si faltan artefactos la API arranca igual y /api/v1/ml/predecir responde 503.
    predictor.iniciar()
    yield


app = FastAPI(title="MediApoyo API", version="0.1.0", lifespan=lifespan)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    """El servidor está arriba."""
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> dict[str, str]:
    """El servidor puede hablar con PostgreSQL."""
    try:
        db.execute(text("select 1"))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="No hay conexión con la base de datos")
    return {"database": "ok"}
