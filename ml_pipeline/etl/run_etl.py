"""Punto de entrada del ETL. Ejecutar desde backend/:

    python -m ml_pipeline.etl.run_etl
"""
import logging

from ml_pipeline.config import cargar_config, ruta
from ml_pipeline.etl.extract import leer_dataset, leer_label_map, leer_sintomas
from ml_pipeline.etl.load import guardar
from ml_pipeline.etl.transform import ErrorDeDatos, Resultado, transformar

log = logging.getLogger("etl")


def ejecutar(cfg: dict | None = None) -> Resultado:
    cfg = cfg or cargar_config()
    datos = cfg["data"]

    log.info("Extrayendo datos de %s", ruta(cfg, "raw"))
    df = leer_dataset(ruta(cfg, "raw") / datos["symptoms_csv"])
    label_map = leer_label_map(ruta(cfg, "mappings") / "label_map.csv")
    sintomas = leer_sintomas(ruta(cfg, "mappings") / "sintomas.csv")

    log.info("Transformando %s filas", f"{len(df):,}")
    resultado = transformar(
        df, label_map, sintomas,
        min_casos=datos["min_unique_cases"],
        val_size=datos["val_size"],
        test_size=datos["test_size"],
        seed=cfg["seed"],
    )

    log.info("Guardando resultados")
    salidas = guardar(resultado, ruta(cfg, "processed"), ruta(cfg, "artifacts"))

    r = resultado.reporte
    log.info("Filas: %s originales -> %s en el subconjunto -> %s tras quitar %s duplicados",
             f"{r['filas_originales']:,}", f"{r['filas_subconjunto']:,}",
             f"{r['filas_finales']:,}", f"{r['duplicados_eliminados']:,}")
    log.info("%d enfermedades | %d síntomas | split: %s",
             r["enfermedades"], r["sintomas_en_vocabulario"], r["filas_por_split"])
    if r["sintomas_del_vocabulario_sin_casos"]:
        log.warning("Síntomas del vocabulario sin ningún caso: %s", r["sintomas_del_vocabulario_sin_casos"])
    for nombre, destino in salidas.items():
        log.info("  %-11s %s", nombre, destino)
    return resultado


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    try:
        ejecutar()
    except ErrorDeDatos as error:
        raise SystemExit(f"ETL detenido: {error}")


if __name__ == "__main__":
    main()
