from sqlalchemy import Identity, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Enfermedad(Base):
    """Tabla enfermedades del diseño SQL (docs/ScriptDb.sql)."""

    __tablename__ = "enfermedades"
    __table_args__ = (UniqueConstraint("nombreenfermedad", name="uq_enfermedades_nombre"),)

    id: Mapped[int] = mapped_column("enfermedadid", Identity(always=True), primary_key=True)
    nombre: Mapped[str] = mapped_column("nombreenfermedad", String(150))
    descripcion: Mapped[str | None] = mapped_column(Text)

    sintomas: Mapped[list["Sintoma"]] = relationship(
        secondary="enfermedadesdetalle", viewonly=True
    )
