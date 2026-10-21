from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Identity, String, Table, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# Síntomas capturados en cada consulta (reemplaza el texto libre `sintomas`)
consulta_sintoma = Table(
    "consulta_sintoma",
    Base.metadata,
    Column("consulta_id", ForeignKey("consulta.id", ondelete="CASCADE"), primary_key=True),
    Column("sintoma_id", ForeignKey("sintomas.sintomaid", ondelete="RESTRICT"), primary_key=True),
)


class Consulta(Base):
    __tablename__ = "consulta"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    paciente_id: Mapped[int] = mapped_column(
        ForeignKey("paciente.id", ondelete="RESTRICT"), index=True
    )
    medico_id: Mapped[int] = mapped_column(
        ForeignKey("medico.id", ondelete="RESTRICT"), index=True
    )
    # Datos del paciente en el momento de la consulta (la edad y el peso cambian)
    paciente_peso: Mapped[float]
    paciente_altura: Mapped[float]
    paciente_edad: Mapped[int]
    fecha_consulta: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    motivo: Mapped[str] = mapped_column(String(500))
    tratamiento: Mapped[str | None] = mapped_column(Text)
    observaciones: Mapped[str | None] = mapped_column(Text)
    # Diagnóstico confirmado por el médico; queda vacío hasta que lo decida
    diagnostico_id: Mapped[int | None] = mapped_column(
        ForeignKey("enfermedades.enfermedadid", ondelete="RESTRICT"), index=True
    )

    paciente: Mapped["Paciente"] = relationship(back_populates="consultas")
    sintomas: Mapped[list["Sintoma"]] = relationship(secondary=consulta_sintoma)
    diagnostico: Mapped["Enfermedad | None"] = relationship()
    predicciones: Mapped[list["Prediccion"]] = relationship(back_populates="consulta")
