from sqlalchemy import Identity, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Enfermedad(Base):
    """Catálogo de enfermedades. Los nombres de tabla y columna son los del diseño SQL."""

    __tablename__ = "enfermedades"

    id: Mapped[int] = mapped_column("enfermedadid", Identity(), primary_key=True)
    # Nombre en inglés: clave estable, igual al dataset y a las clases del modelo
    descripcion: Mapped[str] = mapped_column(String(500))
    # Solo las enfermedades que cubre el modelo (label_map.csv) tienen estos dos campos
    descripcion_es: Mapped[str | None] = mapped_column(String(500))
    cie10_codigo: Mapped[str | None] = mapped_column(String(3))

    sintomas: Mapped[list["Sintoma"]] = relationship(
        secondary="enfermedadesdetalle", viewonly=True
    )
