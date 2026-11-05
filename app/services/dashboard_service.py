"""Estadísticas del dashboard: qué enfermedades se diagnostican más, y dónde.

Cuenta consultas (el diagnóstico que confirmó cada médico) de un año, de todos los médicos. Son solo
conteos: no expone pacientes ni consultas individuales. La "región" es la ciudad del médico que atendió,
que es el único dato geográfico del esquema (docs/ScriptDb.sql). Las ciudades se agrupan sin importar
mayúsculas ni espacios de más: "Morelia", "morelia" y " Morelia " son la misma región.

Cómo se arma lo que se muestra:
  - Top 5 por mes: en cada mes, las 5 enfermedades con más consultas.
  - "Esas 5": las 5 con más consultas en todo el año (top anual). Las dos vistas por región se calculan
    solo para ellas: el total del año y los casos mes a mes.
  - Los empates se rompen por nombre, para que el resultado no cambie entre llamadas."""
from collections import Counter, defaultdict
from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.repositories import dashboard_repo
from app.schemas.dashboard import (
    CasosMensualesRegion, CasosMes, DashboardSalida, EnfermedadCasos, TopDelMes, TotalAnualRegion,
)

TOP = 5
MESES = range(1, 13)


def _normalizar_region(ciudad: str) -> str:
    return " ".join(ciudad.split()).casefold()


def _top(enfermedades: Iterable[EnfermedadCasos]) -> list[EnfermedadCasos]:
    return sorted(enfermedades, key=lambda e: (-e.casos, e.nombre))[:TOP]


def estadisticas(db: Session, anio: int) -> DashboardSalida:
    filas = dashboard_repo.casos_por_mes_y_enfermedad(db, anio)

    nombres: dict[int, str] = {}
    por_mes: dict[int, list[EnfermedadCasos]] = defaultdict(list)
    anual: Counter[int] = Counter()
    for mes, enfermedad_id, nombre, casos in filas:
        nombres[enfermedad_id] = nombre
        por_mes[mes].append(EnfermedadCasos(enfermedad_id=enfermedad_id, nombre=nombre, casos=casos))
        anual[enfermedad_id] += casos

    top_anual = _top(EnfermedadCasos(enfermedad_id=i, nombre=nombres[i], casos=n) for i, n in anual.items())
    ids = [e.enfermedad_id for e in top_anual]

    # región (normalizada) -> casos por mes y por enfermedad, más cómo se escribió cada ciudad
    mensual: dict[str, Counter[int]] = defaultdict(Counter)
    por_enfermedad: dict[str, Counter[int]] = defaultdict(Counter)
    escrituras: dict[str, Counter[str]] = defaultdict(Counter)
    for ciudad, mes, enfermedad_id, casos in dashboard_repo.casos_por_region_mes_enfermedad(db, anio, ids):
        clave = _normalizar_region(ciudad)
        mensual[clave][mes] += casos
        por_enfermedad[clave][enfermedad_id] += casos
        escrituras[clave][" ".join(ciudad.split())] += casos

    def etiqueta(clave: str) -> str:  # la forma más usada de escribir esa ciudad (y, a igualdad, la primera por orden)
        return min(escrituras[clave], key=lambda e: (-escrituras[clave][e], e))

    claves = sorted(mensual, key=lambda c: (-sum(mensual[c].values()), etiqueta(c)))
    return DashboardSalida(
        anio=anio,
        total_consultas=sum(anual.values()),
        top_anual=top_anual,
        top_por_mes=[TopDelMes(mes=m, enfermedades=_top(por_mes.get(m, []))) for m in MESES],
        total_anual_por_region=[
            TotalAnualRegion(
                region=etiqueta(c),
                total=sum(mensual[c].values()),
                enfermedades=[
                    EnfermedadCasos(enfermedad_id=e.enfermedad_id, nombre=e.nombre, casos=por_enfermedad[c][e.enfermedad_id])
                    for e in top_anual
                ],
            )
            for c in claves
        ],
        casos_mensuales_por_region=[
            CasosMensualesRegion(region=etiqueta(c), meses=[CasosMes(mes=m, casos=mensual[c][m]) for m in MESES])
            for c in claves
        ],
    )
