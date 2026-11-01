from sqlalchemy import ForeignKey, Identity, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EnfermedadDetalle(Base):
    """Tabla enfermedadesdetalle del diseño SQL: qué síntomas tiene cada enfermedad."""

    __tablename__ = "enfermedadesdetalle"
    __table_args__ = (
        UniqueConstraint("enfermedadid", "sintomaid", name="uq_enfdet_enfermedad_sintoma"),
        Index("ix_enfdet_sintoma", "sintomaid"),
    )

    id: Mapped[int] = mapped_column("enfermedaddetalleid", Identity(always=True), primary_key=True)
    enfermedad_id: Mapped[int] = mapped_column(
        "enfermedadid",
        ForeignKey("enfermedades.enfermedadid", name="fk_enfdet_enfermedad", onupdate="CASCADE", ondelete="CASCADE"),
    )
    sintoma_id: Mapped[int] = mapped_column(
        "sintomaid",
        ForeignKey("sintomas.sintomaid", name="fk_enfdet_sintoma", onupdate="CASCADE", ondelete="CASCADE"),
    )
