from datetime import date, time

from sqlalchemy import ForeignKey, Identity, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Cita(Base):
    """Tabla citas del diseño SQL (docs/ScriptDb.sql). Un médico no puede tener dos citas a la misma hora."""

    __tablename__ = "citas"
    __table_args__ = (
        UniqueConstraint("medicoid", "fechacita", "horacita", name="uq_citas_medico_horario"),
        Index("ix_citas_paciente", "pacienteid"),
        Index("ix_citas_fecha", "fechacita"),
    )

    id: Mapped[int] = mapped_column("citaid", Identity(always=True), primary_key=True)
    medico_id: Mapped[int] = mapped_column(
        "medicoid",
        ForeignKey("medicos.medicoid", name="fk_citas_medico", onupdate="CASCADE", ondelete="RESTRICT"),
    )
    paciente_id: Mapped[int] = mapped_column(
        "pacienteid",
        ForeignKey("pacientes.pacienteid", name="fk_citas_paciente", onupdate="CASCADE", ondelete="RESTRICT"),
    )
    fecha_cita: Mapped[date] = mapped_column("fechacita")
    hora_cita: Mapped[time] = mapped_column("horacita")

    medico: Mapped["Medico"] = relationship(back_populates="citas")
    paciente: Mapped["Paciente"] = relationship(back_populates="citas")
