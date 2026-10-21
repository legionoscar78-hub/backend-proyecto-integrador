"""Lectura de config.yaml y resolución de rutas, compartida por el ETL y el entrenamiento."""
from pathlib import Path

import yaml

BACKEND = Path(__file__).resolve().parents[1]
CONFIG_YAML = Path(__file__).resolve().parent / "config.yaml"


def cargar_config(ruta: Path = CONFIG_YAML) -> dict:
    return yaml.safe_load(ruta.read_text(encoding="utf-8"))


def ruta(cfg: dict, nombre: str) -> Path:
    """Ruta de cfg['paths'][nombre], que en el YAML es relativa a backend/."""
    return BACKEND / cfg["paths"][nombre]
