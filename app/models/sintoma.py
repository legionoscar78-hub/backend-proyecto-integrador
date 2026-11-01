from sqlalchemy import Identity, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Sintoma(Base):
    """Tabla sintomas del diseño SQL (docs/ScriptDb.sql)."""

    __tablename__ = "sintomas"
    __table_args__ = (UniqueConstraint("nombresintoma", name="uq_sintomas_nombre"),)

    id: Mapped[int] = mapped_column("sintomaid", Identity(always=True), primary_key=True)
    nombre: Mapped[str] = mapped_column("nombresintoma", String(150))
