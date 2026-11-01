from datetime import date

from sqlalchemy import CHAR, CheckConstraint, Identity, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Paciente(Base):
    """Tabla pacientes del diseño SQL (docs/ScriptDb.sql)."""

    __tablename__ = "pacientes"
    __table_args__ = (
        UniqueConstraint("curp", name="uq_pacientes_curp"),
        CheckConstraint("sexo IN ('H', 'M')", name="ck_pacientes_sexo"),
        CheckConstraint(
            "tipodesangre IS NULL OR tipodesangre IN ('A+','A-','B+','B-','AB+','AB-','O+','O-')",
            name="ck_pacientes_tiposangre",
        ),
        CheckConstraint("fechanacimiento <= CURRENT_DATE", name="ck_pacientes_fechanac"),
    )

    id: Mapped[int] = mapped_column("pacienteid", Identity(always=True), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    apellidos: Mapped[str] = mapped_column(String(150))
    curp: Mapped[str] = mapped_column(CHAR(18))
    fecha_nacimiento: Mapped[date] = mapped_column("fechanacimiento")
    numero_telefonico: Mapped[str | None] = mapped_column("numerotelefonico", String(15))
    sexo: Mapped[str] = mapped_column(CHAR(1))  # 'H' o 'M'
    tipo_de_sangre: Mapped[str | None] = mapped_column("tipodesangre", String(3))
    notas: Mapped[str | None] = mapped_column(Text)

    citas: Mapped[list["Cita"]] = relationship(back_populates="paciente")
    consultas: Mapped[list["Consulta"]] = relationship(back_populates="paciente")
