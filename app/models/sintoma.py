from sqlalchemy import Identity, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Sintoma(Base):
    """Catálogo de síntomas. Los nombres de tabla y columna son los del diseño SQL."""

    __tablename__ = "sintomas"

    id: Mapped[int] = mapped_column("sintomaid", Identity(), primary_key=True)
    # Nombre en inglés: clave estable, igual a las columnas del dataset y a symptoms.json
    nombre: Mapped[str] = mapped_column("nombresintoma", String(100), unique=True)
    # Nombre para mostrar en la interfaz
    nombre_es: Mapped[str | None] = mapped_column(String(150))
