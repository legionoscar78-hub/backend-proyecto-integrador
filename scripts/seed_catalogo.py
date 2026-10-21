"""Carga el catálogo de enfermedades y síntomas desde DiseaseAndSymptoms.csv.

Llena enfermedades, sintomas y enfermedadesdetalle, y completa los nombres en español
(sintomas.nombre_es, enfermedades.descripcion_es y cie10_codigo) con los catálogos de
ml_pipeline/mappings/. Es idempotente: se puede ejecutar varias veces sin duplicar filas.

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
MAX_ENFERMEDAD = 500  # enfermedades.descripcion varchar(500)
MAX_SINTOMA = 100     # sintomas.nombresintoma varchar(100)
TABLAS = ("enfermedades", "sintomas", "enfermedadesdetalle")
COLUMNAS_ES = (("sintomas", "nombre_es"), ("enfermedades", "descripcion_es"), ("enfermedades", "cie10_codigo"))


@dataclass
class Catalogo:
    enfermedades: list[str]
    sintomas: list[str]                     # en el orden de columnas del CSV
    pares: list[tuple[str, str]]            # (enfermedad, sintoma)
    sintomas_sin_enfermedad: list[str]
    sintomas_es: dict[str, str]             # nombre_en -> nombre_es
    enfermedades_es: dict[str, tuple[str, str]]  # enfermedad_en -> (enfermedad_es, código CIE-10)


def leer_catalogo(csv: Path, mappings: Path = MAPPINGS) -> Catalogo:
    cabecera = pd.read_csv(csv, nrows=0).columns
    if COL_ENFERMEDAD not in cabecera:
        raise ValueError(f"El CSV no tiene la columna '{COL_ENFERMEDAD}'")

    originales = [c for c in cabecera if c != COL_ENFERMEDAD]
    # int8: el CSV pesa ~190 MB y con int64 ocuparía más de 700 MB en memoria
    df = pd.read_csv(csv, dtype={c: "int8" for c in originales})

    sintomas = [normalizar_texto(c) for c in originales]
    if len(set(sintomas)) != len(sintomas):
        raise ValueError("Hay nombres de síntomas repetidos tras normalizar")
    df.columns = [COL_ENFERMEDAD] + sintomas
    df[COL_ENFERMEDAD] = df[COL_ENFERMEDAD].map(normalizar_texto)

    if df[COL_ENFERMEDAD].isna().any() or (df[COL_ENFERMEDAD] == "").any():
        raise ValueError("Hay filas sin nombre de enfermedad")
    if (df[sintomas] > 1).any().any() or (df[sintomas] < 0).any().any():
        raise ValueError("Las columnas de síntomas deben contener solo 0 o 1")
    if max(map(len, sintomas)) > MAX_SINTOMA:
        raise ValueError(f"Un síntoma supera {MAX_SINTOMA} caracteres")
    if df[COL_ENFERMEDAD].str.len().max() > MAX_ENFERMEDAD:
        raise ValueError(f"Una enfermedad supera {MAX_ENFERMEDAD} caracteres")

    # Un síntoma pertenece a una enfermedad si aparece en al menos un caso suyo.
    presencia = df.groupby(COL_ENFERMEDAD)[sintomas].max() > 0
    pares = [
        (enfermedad, sintoma)
        for enfermedad, fila in presencia.iterrows()
        for sintoma in fila.index[fila]
    ]

    # Nombres en español: deben cubrir todos los síntomas y solo enfermedades que existan
    sv = pd.read_csv(mappings / "sintomas.csv")
    sintomas_es = dict(zip(sv["nombre_en"].map(normalizar_texto), sv["nombre_es"]))
    if set(sintomas_es) != set(sintomas):
        raise ValueError("mappings/sintomas.csv no coincide con las columnas del dataset")
    lm = pd.read_csv(mappings / "label_map.csv")
    enfermedades_es = {
        normalizar_texto(r.enfermedad_en): (r.enfermedad_es, r.cie10_codigo) for r in lm.itertuples()
    }
    desconocidas = set(enfermedades_es) - set(presencia.index)
    if desconocidas:
        raise ValueError(f"label_map.csv tiene enfermedades que no están en el dataset: {sorted(desconocidas)}")

    return Catalogo(
        enfermedades=list(presencia.index),
        sintomas=sintomas,
        pares=pares,
        sintomas_sin_enfermedad=list(presencia.columns[~presencia.any()]),
        sintomas_es=sintomas_es,
        enfermedades_es=enfermedades_es,
    )


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
        f"{t}.{c}" for t, c in COLUMNAS_ES
        if not conn.execute(
            text("select 1 from information_schema.columns where table_name = :t and column_name = :c"),
            {"t": t, "c": c},
        ).first()
    ]
    if sin_columna:
        raise SystemExit(
            f"Faltan las columnas: {', '.join(sin_columna)}.\n"
            "Actualiza el esquema con: alembic upgrade head"
        )


def cargar(conn: Connection, cat: Catalogo) -> tuple[dict[str, tuple[int, int]], dict[str, int]]:
    """Inserta lo que falte. Devuelve ({tabla: (filas_antes, filas_despues)}, {traducidos: n})."""
    _verificar_tablas(conn)
    antes = _contar(conn)

    # enfermedades.descripcion no es unique en el diseño, así que se filtra aquí
    existentes = set(conn.execute(text("select descripcion from enfermedades")).scalars())
    nuevas = [{"d": e} for e in cat.enfermedades if e not in existentes]
    if nuevas:
        conn.execute(text("insert into enfermedades (descripcion) values (:d)"), nuevas)

    # Se insertan en el orden de columnas del CSV para que sintomaid siga ese orden
    conn.execute(
        text("insert into sintomas (nombresintoma) values (:n) "
             "on conflict (nombresintoma) do nothing"),
        [{"n": s} for s in cat.sintomas],
    )

    id_enfermedad = {d: i for i, d in conn.execute(
        text("select enfermedadid, descripcion from enfermedades"))}
    id_sintoma = {n: i for i, n in conn.execute(
        text("select sintomaid, nombresintoma from sintomas"))}

    conn.execute(
        text("insert into enfermedadesdetalle (enfermedadid, sintomaid) "
             "values (:e, :s) on conflict (enfermedadid, sintomaid) do nothing"),
        [{"e": id_enfermedad[e], "s": id_sintoma[s]} for e, s in cat.pares],
    )

    # Nombres en español (el inglés sigue siendo la clave estable)
    conn.execute(
        text("update sintomas set nombre_es = :es where nombresintoma = :en"),
        [{"en": en, "es": es} for en, es in cat.sintomas_es.items()],
    )
    conn.execute(
        text("update enfermedades set descripcion_es = :es, cie10_codigo = :c where descripcion = :en"),
        [{"en": en, "es": es, "c": c} for en, (es, c) in cat.enfermedades_es.items()],
    )

    despues = _contar(conn)
    traducidos = {
        "sintomas con nombre_es": conn.execute(text("select count(nombre_es) from sintomas")).scalar_one(),
        "enfermedades con descripcion_es": conn.execute(
            text("select count(descripcion_es) from enfermedades")).scalar_one(),
    }
    return {t: (antes[t], despues[t]) for t in antes}, traducidos


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--csv", type=Path, default=CSV_POR_DEFECTO)
    parser.add_argument("--dry-run", action="store_true",
                        help="analiza el CSV sin conectarse a la base de datos")
    args = parser.parse_args()

    cat = leer_catalogo(args.csv)
    print(f"CSV: {args.csv.name}")
    print(f"  enfermedades:                 {len(cat.enfermedades)}")
    print(f"  síntomas:                     {len(cat.sintomas)}")
    print(f"  relaciones enfermedad-síntoma: {len(cat.pares)}")
    print(f"  con nombre en español:        {len(cat.sintomas_es)} síntomas, {len(cat.enfermedades_es)} enfermedades")
    if cat.sintomas_sin_enfermedad:
        print(f"  síntomas sin ninguna enfermedad: {len(cat.sintomas_sin_enfermedad)} "
              "(se cargan igual para conservar el vocabulario completo)")

    if args.dry_run:
        print("Dry-run: no se modificó la base de datos.")
        return

    # Import tardío: así --dry-run funciona sin .env ni Postgres
    from app.core.database import engine

    with engine.begin() as conn:  # una sola transacción: o se carga todo o nada
        resumen, traducidos = cargar(conn, cat)

    print("Base de datos (filas antes -> después):")
    for tabla, (antes, despues) in resumen.items():
        print(f"  {tabla:<22} {antes} -> {despues}")
    for nombre, n in traducidos.items():
        print(f"  {nombre:<32} {n}")


if __name__ == "__main__":
    main()
