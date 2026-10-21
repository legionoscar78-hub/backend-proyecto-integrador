from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_db

app = FastAPI(title="MediApoyo API", version="0.1.0")

# Al crear los routers de app/api/routers/, se registran aquí:
#   app.include_router(pacientes.router, prefix="/pacientes", tags=["pacientes"])


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
