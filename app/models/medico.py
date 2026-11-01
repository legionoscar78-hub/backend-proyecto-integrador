from sqlalchemy import Identity, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Medico(Base):
    """Tabla medicos del diseño SQL (docs/ScriptDb.sql)."""

    __tablename__ = "medicos"
    __table_args__ = (UniqueConstraint("nombredeusuario", name="uq_medicos_usuario"),)

    id: Mapped[int] = mapped_column("medicoid", Identity(always=True), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    apellidos: Mapped[str] = mapped_column(String(150))
    ciudad: Mapped[str] = mapped_column(String(100))
    efirma: Mapped[str] = mapped_column(Text)
    nombre_de_usuario: Mapped[str] = mapped_column("nombredeusuario", String(50))
    # Hash (argon2), nunca la contraseña en claro
    password: Mapped[str] = mapped_column(String(255))

    citas: Mapped[list["Cita"]] = relationship(back_populates="medico")
    consultas: Mapped[list["Consulta"]] = relationship(back_populates="medico")
