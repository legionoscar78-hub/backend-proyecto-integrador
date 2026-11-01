"""Los modelos SQLAlchemy deben tener la estructura de docs/ScriptDb.sql: mismas tablas, columnas
(en orden), nulabilidad, restricciones e índices con sus nombres. No necesita base de datos."""
import re
from pathlib import Path

import pytest

import app.models  # noqa: F401  registra los modelos
from app.core.database import Base

SCRIPT = Path(__file__).resolve().parents[2] / "docs" / "ScriptDb.sql"


def _tablas_del_script() -> dict[str, dict]:
    sql = SCRIPT.read_text(encoding="utf-8")
    sql = re.sub(r"--[^\n]*", "", sql)  # comentarios
    tablas = {}
    for m in re.finditer(r"CREATE TABLE (\w+) \((.*?)\n\);", sql, flags=re.S | re.I):
        nombre, cuerpo = m.group(1).lower(), m.group(2)
        columnas, restricciones = [], set()
        # una definición por línea; las restricciones pueden ocupar varias, pero siempre empiezan con CONSTRAINT
        for linea in cuerpo.split("\n"):
            linea = linea.strip().rstrip(",")
            if not linea:
                continue
            c = re.match(r"CONSTRAINT (\w+)", linea, flags=re.I)
            if c:
                restricciones.add(c.group(1).lower())
            elif re.match(r"\w+\s+(INTEGER|VARCHAR|CHAR|TEXT|DATE|TIME|SMALLINT|NUMERIC|TIMESTAMP)", linea, flags=re.I):
                col = linea.split()[0].lower()
                obligatoria = "NOT NULL" in linea.upper() or "GENERATED ALWAYS" in linea.upper()
                columnas.append((col, obligatoria))
        tablas[nombre] = {"columnas": columnas, "restricciones": restricciones}
    indices = {m.group(1).lower(): m.group(2).lower()
               for m in re.finditer(r"CREATE INDEX (\w+)\s+ON (\w+)", sql, flags=re.I)}
    return {"tablas": tablas, "indices": indices}


SCRIPT_DB = _tablas_del_script()
MODELOS = Base.metadata.tables


def test_el_script_se_leyo_bien():
    assert set(SCRIPT_DB["tablas"]) == {
        "medicos", "pacientes", "enfermedades", "sintomas", "citas", "consultas", "enfermedadesdetalle"}
    assert len(SCRIPT_DB["indices"]) == 6


def test_mismas_tablas():
    assert set(MODELOS) == set(SCRIPT_DB["tablas"])


@pytest.mark.parametrize("tabla", sorted(SCRIPT_DB["tablas"]))
def test_mismas_columnas_en_el_mismo_orden_y_con_la_misma_nulabilidad(tabla):
    esperado = SCRIPT_DB["tablas"][tabla]["columnas"]
    real = [(c.name, not c.nullable) for c in MODELOS[tabla].columns]
    assert real == esperado


@pytest.mark.parametrize("tabla", sorted(SCRIPT_DB["tablas"]))
def test_mismas_restricciones_con_el_mismo_nombre(tabla):
    real = {str(c.name).lower() for c in MODELOS[tabla].constraints}
    assert real == SCRIPT_DB["tablas"][tabla]["restricciones"]


def test_mismos_indices_con_el_mismo_nombre():
    real = {i.name: t.name for t in MODELOS.values() for i in t.indexes}
    assert real == SCRIPT_DB["indices"]


def test_los_identificadores_son_identity_always():
    for tabla in MODELOS.values():
        pk = list(tabla.primary_key.columns)
        assert len(pk) == 1 and pk[0].identity is not None and pk[0].identity.always, tabla.name
