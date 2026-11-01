from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Identity, Index, Numeric, SmallInteger, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Consulta(Base):
    """Tabla consultas del diseño SQL (docs/ScriptDb.sql).

    Guarda el diagnóstico que el médico confirmó (enfermedad_id), no lo que sugirió el modelo.
    """

    __tablename__ = "consultas"
    __table_args__ = (
        UniqueConstraint("llave", name="uq_consultas_llave"),
        CheckConstraint("edad BETWEEN 0 AND 150", name="ck_consultas_edad"),
        CheckConstraint("peso IS NULL OR peso > 0", name="ck_consultas_peso"),
        CheckConstraint("altura IS NULL OR altura > 0", name="ck_consultas_altura"),
        Index("ix_consultas_medico", "medicoid"),
        Index("ix_consultas_paciente", "pacienteid"),
        Index("ix_consultas_enfermedad", "enfermedadid"),
    )

    id: Mapped[int] = mapped_column("consultaid", Identity(always=True), primary_key=True)
    medico_id: Mapped[int] = mapped_column(
        "medicoid",
        ForeignKey("medicos.medicoid", name="fk_consultas_medico", onupdate="CASCADE", ondelete="RESTRICT"),
    )
    paciente_id: Mapped[int] = mapped_column(
        "pacienteid",
        ForeignKey("pacientes.pacienteid", name="fk_consultas_paciente", onupdate="CASCADE", ondelete="RESTRICT"),
    )
    enfermedad_id: Mapped[int] = mapped_column(
        "enfermedadid",
        ForeignKey("enfermedades.enfermedadid", name="fk_consultas_enfermedad", onupdate="CASCADE", ondelete="RESTRICT"),
    )
    edad: Mapped[int] = mapped_column(SmallInteger)  # edad del paciente el día de la consulta
    peso: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))  # kg
    altura: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))  # metros
    fecha_consulta: Mapped[datetime] = mapped_column(
        "fechaconsulta", DateTime(), server_default=func.current_timestamp()
    )
    llave: Mapped[str] = mapped_column(String(100))
    notas: Mapped[str | None] = mapped_column(Text)

    medico: Mapped["Medico"] = relationship(back_populates="consultas")
    paciente: Mapped["Paciente"] = relationship(back_populates="consultas")
    enfermedad: Mapped["Enfermedad"] = relationship()
