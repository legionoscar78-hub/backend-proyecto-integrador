from datetime import datetime

from sqlalchemy import DateTime, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Medico(Base):
    __tablename__ = "medico"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    apellidos: Mapped[str] = mapped_column(String(100))
    especialidad: Mapped[str] = mapped_column(String(100))
    direccion_consultorio: Mapped[str] = mapped_column(String(200))
    correo: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))  # nunca la contraseña en claro
    fecha_registro: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
