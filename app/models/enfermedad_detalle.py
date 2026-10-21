from sqlalchemy import ForeignKey, Identity, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EnfermedadDetalle(Base):
    """Qué síntomas tiene cada enfermedad (tabla enfermedadesdetalle del diseño SQL)."""

    __tablename__ = "enfermedadesdetalle"
    __table_args__ = (
        UniqueConstraint("enfermedadid", "sintomaid", name="uq_enfermedad_sintoma"),
        Index("ix_detalle_sintoma", "sintomaid"),  # "qué enfermedades tienen este síntoma"
    )

    id: Mapped[int] = mapped_column("detalleid", Identity(), primary_key=True)
    enfermedad_id: Mapped[int] = mapped_column(
        "enfermedadid",
        ForeignKey("enfermedades.enfermedadid", name="fk_detalle_enfermedad", ondelete="RESTRICT"),
    )
    sintoma_id: Mapped[int] = mapped_column(
        "sintomaid",
        ForeignKey("sintomas.sintomaid", name="fk_detalle_sintoma", ondelete="RESTRICT"),
    )
