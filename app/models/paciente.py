from datetime import date, datetime

from sqlalchemy import DateTime, ForeignKey, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Paciente(Base):
    __tablename__ = "paciente"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    # Cada paciente pertenece a un médico: los repositories filtran por este campo
    medico_id: Mapped[int] = mapped_column(
        ForeignKey("medico.id", ondelete="RESTRICT"), index=True
    )
    nombre: Mapped[str] = mapped_column(String(100))
    apellidos: Mapped[str] = mapped_column(String(100))
    fecha_nacimiento: Mapped[date]
    telefono: Mapped[str] = mapped_column(String(10))
    fecha_registro: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    consultas: Mapped[list["Consulta"]] = relationship(back_populates="paciente")
