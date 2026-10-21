from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Prediccion(Base):
    """Una ejecución del modelo sobre una consulta."""

    __tablename__ = "prediccion"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    consulta_id: Mapped[int] = mapped_column(
        ForeignKey("consulta.id", ondelete="CASCADE"), index=True
    )
    modelo_version: Mapped[str] = mapped_column(String(50))
    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    consulta: Mapped["Consulta"] = relationship(back_populates="predicciones")
    detalles: Mapped[list["PrediccionDetalle"]] = relationship(
        back_populates="prediccion",
        order_by="PrediccionDetalle.posicion",
        cascade="all, delete-orphan",
    )


class PrediccionDetalle(Base):
    """Una enfermedad sugerida por el modelo, con su probabilidad."""

    __tablename__ = "prediccion_detalle"

    prediccion_id: Mapped[int] = mapped_column(
        ForeignKey("prediccion.id", ondelete="CASCADE"), primary_key=True
    )
    enfermedad_id: Mapped[int] = mapped_column(
        ForeignKey("enfermedades.enfermedadid", ondelete="RESTRICT"), primary_key=True
    )
    probabilidad: Mapped[float]
    posicion: Mapped[int]  # 1 = la más probable

    prediccion: Mapped["Prediccion"] = relationship(back_populates="detalles")
