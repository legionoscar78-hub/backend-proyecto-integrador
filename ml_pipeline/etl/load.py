"""Carga: escribe lo que produjo transform.py. Sobrescribe en cada ejecución."""
import json
from pathlib import Path

from ml_pipeline.etl.transform import Resultado


def _json(ruta: Path, contenido) -> None:
    ruta.write_text(json.dumps(contenido, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def guardar(res: Resultado, processed: Path, artifacts: Path) -> dict[str, Path]:
    """Escribe en processed/ el dataset, las clases y el reporte, y en artifacts/ el vocabulario.

    symptoms.json va a artifacts/ porque el predictor lo necesita junto al modelo: es el
    orden de las columnas con el que se entrenó. symptoms_es.json (inglés -> español) deja que
    el predictor acepte los nombres que guarda la BD.
    """
    processed.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    salidas = {
        "dataset": processed / "dataset.parquet",
        "clases": processed / "classes.json",
        "reporte": processed / "etl_report.json",
        "vocabulario": artifacts / "symptoms.json",
        "nombres_es": artifacts / "symptoms_es.json",
    }
    res.datos.to_parquet(salidas["dataset"], index=False)
    _json(salidas["clases"], res.clases)
    _json(salidas["reporte"], res.reporte)
    _json(salidas["vocabulario"], res.vocabulario)
    _json(salidas["nombres_es"], res.nombres_es)
    return salidas
