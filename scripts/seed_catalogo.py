"""Carga el catálogo de enfermedades y síntomas desde DiseaseAndSymptoms.csv.

Llena enfermedades, sintomas y enfermedadesdetalle (tablas de docs/ScriptDb.sql). Los nombres se
guardan en español usando los catálogos de ml_pipeline/mappings/:
  - sintomas.nombresintoma: nombre en español de los 377 síntomas (sintomas.csv).
  - enfermedades.nombreenfermedad: nombre en español de las 99 enfermedades del modelo
    (label_map.csv). Las demás conservan el nombre original en inglés hasta que se traduzcan.
  - enfermedades.descripcion: para las 99 del modelo, el código y la descripción CIE-10.
Es idempotente: se puede ejecutar varias veces sin duplicar filas.

Las tablas las crea Alembic, no este script. Antes de cargar, desde backend/:
    alembic upgrade head

Uso (necesita el .env con las credenciales):
    python scripts/seed_catalogo.py --dry-run   # solo analiza el CSV, no toca la BD
    python scripts/seed_catalogo.py             # carga el catálogo
"""
import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from sqlalchemy import Connection, text

BACKEND = Path(__file__).resolve().parents[1]
# Al ejecutar el archivo directamente, Python solo ve scripts/; se agrega backend/
# para poder importar el paquete `app`.
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.ml.features import normalizar_texto  # noqa: E402  (misma normalización que el ETL y el predictor)

CSV_POR_DEFECTO = BACKEND / "ml_pipeline" / "data" / "raw" / "DiseaseAndSymptoms.csv"
MAPPINGS = BACKEND / "ml_pipeline" / "mappings"
COL_ENFERMEDAD = "diseases"
MAX_NOMBRE = 150  # enfermedades.nombreenfermedad y sintomas.nombresintoma son varchar(150)
TABLAS = ("enfermedades", "sintomas", "enfermedadesdetalle")
COLUMNAS = (
    ("enfermedades", "nombreenfermedad"), ("enfermedades", "descripcion"),
    ("sintomas", "nombresintoma"),
    ("enfermedadesdetalle", "enfermedadid"), ("enfermedadesdetalle", "sintomaid"),
)


@dataclass
class Catalogo:
    enfermedades: list[str]                 # nombres tal como se guardan en la BD
    sintomas: list[str]                     # nombres en español, en el orden de columnas del CSV
    pares: list[tuple[str, str]]            # (enfermedad, síntoma), con los nombres de la BD
    sintomas_sin_enfermedad: list[str]
    descripciones: dict[str, str]           # enfermedad -> "CIE-10 J01: ..." (solo las del modelo)

    @property
    def enfermedades_traducidas(self) -> int:
        return len(self.descripciones)


def leer_catalogo(csv: Path, mappings: Path = MAPPINGS) -> Catalogo:
    cabecera = pd.read_csv(csv, nrows=0).columns
    if COL_ENFERMEDAD not in cabecera:
        raise ValueError(f"El CSV no tiene la columna '{COL_ENFERMEDAD}'")

    originales = [c for c in cabecera if c != COL_ENFERMEDAD]
    # int8: el CSV pesa ~190 MB y con int64 ocuparía más de 700 MB en memoria
    df = pd.read_csv(csv, dtype={c: "int8" for c in originales})

    sintomas_en = [normalizar_texto(c) for c in originales]
    if len(set(sintomas_en)) != len(sintomas_en):
        raise ValueError("Hay nombres de síntomas repetidos tras normalizar")
    df.columns = [COL_ENFERMEDAD] + sintomas_en
    df[COL_ENFERMEDAD] = df[COL_ENFERMEDAD].map(normalizar_texto)

    if df[COL_ENFERMEDAD].isna().any() or (df[COL_ENFERMEDAD] == "").any():
        raise ValueError("Hay filas sin nombre de enfermedad")
    if (df[sintomas_en] > 1).any().any() or (df[sintomas_en] < 0).any().any():
        raise ValueError("Las columnas de síntomas deben contener solo 0 o 1")

    # Un síntoma pertenece a una enfermedad si aparece en al menos un caso suyo.
    presencia = df.groupby(COL_ENFERMEDAD)[sintomas_en].max() > 0

    # --- síntomas: el nombre de la BD es el español; debe cubrir todos y no repetirse
    sv = pd.read_csv(mappings / "sintomas.csv", encoding="utf-8-sig")
    sintoma_es = dict(zip(sv["nombre_en"].map(normalizar_texto), sv["nombre_es"]))
    if set(sintoma_es) != set(sintomas_en):
        raise ValueError("mappings/sintomas.csv no coincide con las columnas del dataset")
    sintomas = [sintoma_es[s] for s in sintomas_en]
    _validar_nombres(sintomas, "síntomas")

    # --- enfermedades: español si está en label_map.csv, si no el nombre original
    lm = pd.read_csv(mappings / "label_map.csv", encoding="utf-8-sig")
    del_modelo = {normalizar_texto(r.enfermedad_en): r for r in lm.itertuples()}
    desconocidas = set(del_modelo) - set(presencia.index)
    if desconocidas:
        raise ValueError(f"label_map.csv tiene enfermedades que no están en el dataset: {sorted(desconocidas)}")

    nombre_bd = {en: (del_modelo[en].enfermedad_es if en in del_modelo else en) for en in presencia.index}
    enfermedades = [nombre_bd[en] for en in presencia.index]
    _validar_nombres(enfermedades, "enfermedades")
    descripciones = {
        nombre_bd[en]: f"CIE-10 {r.cie10_codigo}: {r.cie10_descripcion}" for en, r in del_modelo.items()
    }

    pares = [
        (nombre_bd[enfermedad], sintoma_es[sintoma])
        for enfermedad, fila in presencia.iterrows()
        for sintoma in fila.index[fila]
    ]
    return Catalogo(
        enfermedades=enfermedades,
        sintomas=sintomas,
        pares=pares,
        sintomas_sin_enfermedad=[sintoma_es[s] for s in presencia.columns[~presencia.any()]],
        descripciones=descripciones,
    )


def _validar_nombres(nombres: list[str], que: str) -> None:
    """Los nombres son unique y varchar(150) en la BD: se comprueba antes de tocarla."""
    if len(set(nombres)) != len(nombres):
        raise ValueError(f"Hay nombres de {que} repetidos")
    if max(map(len, nombres)) > MAX_NOMBRE:
        raise ValueError(f"Un nombre de {que} supera {MAX_NOMBRE} caracteres")


def _contar(conn: Connection) -> dict[str, int]:
    return {
        tabla: conn.execute(text(f"select count(*) from {tabla}")).scalar_one()
        for tabla in TABLAS
    }


def _verificar_tablas(conn: Connection) -> None:
    faltan = [
        t for t in TABLAS
        if conn.execute(text("select to_regclass(:t)"), {"t": t}).scalar() is None
    ]
    if faltan:
        raise SystemExit(
            f"Faltan las tablas: {', '.join(faltan)}.\n"
            "Créalas primero con: alembic upgrade head"
        )
    sin_columna = [
        f"{t}.{c}" for t, c in COLUMNAS
        if not conn.execute(
            text("select 1 from information_schema.columns "
                 "where table_schema = current_schema() and table_name = :t and column_name = :c"),
            {"t": t, "c": c},
        ).first()
    ]
    if sin_columna:
        raise SystemExit(
            f"Faltan las columnas: {', '.join(sin_columna)}.\n"
            "El esquema está desactualizado. Actualízalo con: alembic upgrade head"
        )


def cargar(conn: Connection, cat: Catalogo) -> dict[str, tuple[int, int]]:
    """Inserta lo que falte. Devuelve {tabla: (filas_antes, filas_despues)}."""
    _verificar_tablas(conn)
    antes = _contar(conn)

    conn.execute(
        text("insert into enfermedades (nombreenfermedad) values (:n) on conflict (nombreenfermedad) do nothing"),
        [{"n": e} for e in cat.enfermedades],
    )
    # Se insertan en el orden de columnas del CSV para que sintomaid siga ese orden
    conn.execute(
        text("insert into sintomas (nombresintoma) values (:n) on conflict (nombresintoma) do nothing"),
        [{"n": s} for s in cat.sintomas],
    )

    id_enfermedad = {n: i for i, n in conn.execute(
        text("select enfermedadid, nombreenfermedad from enfermedades"))}
    id_sintoma = {n: i for i, n in conn.execute(
        text("select sintomaid, nombresintoma from sintomas"))}

    conn.execute(
        text("insert into enfermedadesdetalle (enfermedadid, sintomaid) "
             "values (:e, :s) on conflict (enfermedadid, sintomaid) do nothing"),
        [{"e": id_enfermedad[e], "s": id_sintoma[s]} for e, s in cat.pares],
    )
    conn.execute(
        text("update enfermedades set descripcion = :d where nombreenfermedad = :n"),
        [{"n": n, "d": d} for n, d in cat.descripciones.items()],
    )

    despues = _contar(conn)
    return {t: (antes[t], despues[t]) for t in antes}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--csv", type=Path, default=CSV_POR_DEFECTO)
    parser.add_argument("--dry-run", action="store_true",
                        help="analiza el CSV sin conectarse a la base de datos")
    args = parser.parse_args()

    cat = leer_catalogo(args.csv)
    print(f"CSV: {args.csv.name}")
    print(f"  enfermedades:                 {len(cat.enfermedades)} "
          f"({cat.enfermedades_traducidas} en español, el resto en inglés)")
    print(f"  síntomas:                     {len(cat.sintomas)} (todos en español)")
    print(f"  relaciones enfermedad-síntoma: {len(cat.pares)}")
    if cat.sintomas_sin_enfermedad:
        print(f"  síntomas sin ninguna enfermedad: {len(cat.sintomas_sin_enfermedad)} "
              "(se cargan igual para conservar el vocabulario completo)")

    if args.dry_run:
        print("Dry-run: no se modificó la base de datos.")
        return

    # Import tardío: así --dry-run funciona sin .env ni Postgres
    from app.core.database import engine

    with engine.begin() as conn:  # una sola transacción: o se carga todo o nada
        resumen = cargar(conn, cat)

    print("Base de datos (filas antes -> después):")
    for tabla, (antes, despues) in resumen.items():
        print(f"  {tabla:<22} {antes} -> {despues}")


if __name__ == "__main__":
    main()
