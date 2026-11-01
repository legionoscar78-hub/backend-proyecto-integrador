from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

LIMITE_POR_DEFECTO = 20
LIMITE_MAXIMO = 100


class Pagina(BaseModel, Generic[T]):
    """Una página de resultados. `total` cuenta todos los que cumplen el filtro, no solo los de esta página."""

    items: list[T]
    total: int = Field(ge=0)
    limit: int
    offset: int
