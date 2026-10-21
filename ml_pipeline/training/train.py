"""Entrenamiento del MLP. Ejecutar desde backend/ (después del ETL):

    python -m ml_pipeline.training.train

Usa solo los splits train y val: val decide cuándo parar y qué época guardar. El split
test no se carga aquí; lo usa evaluate.py una sola vez al final.
"""
import copy
import hashlib
import json
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn

from app.ml.features import cargar_vocabulario
from app.ml.model import crear_mlp
from ml_pipeline.config import cargar_config, ruta

log = logging.getLogger("train")

COLUMNAS_META = ("enfermedad_en", "clase", "split")
TOLERANCIA_MEJORA = 1e-4  # una época cuenta como mejor solo si baja la pérdida de val más que esto


class ErrorDeEntrenamiento(ValueError):
    """Los datos o la configuración no permiten entrenar."""


@dataclass
class Datos:
    X_train: np.ndarray
    y_train: np.ndarray
    X_val: np.ndarray
    y_val: np.ndarray
    vocabulario: list[str]
    clases: list[dict]


@dataclass
class Resultado:
    estado: dict[str, torch.Tensor]  # pesos de la mejor época
    historial: list[dict]
    mejor_epoca: int
    metricas_val: dict


def leer_dataset(processed: Path, artifacts: Path) -> tuple[pd.DataFrame, list[str], list[dict]]:
    """Lee la salida del ETL y comprueba que sea coherente. Devuelve (df, vocabulario, clases).

    Lo usan este script y evaluate.py, para que los dos validen los datos igual.
    """
    vocabulario = cargar_vocabulario(artifacts / "symptoms.json")
    clases = json.loads((processed / "classes.json").read_text(encoding="utf-8"))
    df = pd.read_parquet(processed / "dataset.parquet")

    columnas = [c for c in df.columns if c not in COLUMNAS_META]
    if columnas != vocabulario:
        raise ErrorDeEntrenamiento(
            "Las columnas de dataset.parquet no coinciden con symptoms.json (nombres u orden). "
            "Vuelve a ejecutar el ETL."
        )
    if [c["indice"] for c in clases] != list(range(len(clases))):
        raise ErrorDeEntrenamiento("classes.json debe numerar las clases 0..n-1 en orden")
    esperado = {c["indice"]: c["enfermedad_en"] for c in clases}
    real = dict(df[["clase", "enfermedad_en"]].drop_duplicates().itertuples(index=False))
    if real != esperado:
        raise ErrorDeEntrenamiento("Las clases de dataset.parquet no coinciden con classes.json")
    return df, vocabulario, clases


def tomar_split(df: pd.DataFrame, vocabulario: list[str], split: str) -> tuple[np.ndarray, np.ndarray]:
    """(X float32, y int64) de las filas del split indicado."""
    parte = df[df["split"] == split]
    if parte.empty:
        raise ErrorDeEntrenamiento(f"El dataset no tiene filas en el split '{split}'")
    # copy=True: pandas puede devolver vistas de solo lectura y torch.from_numpy las rechaza
    return (parte[vocabulario].to_numpy(dtype=np.float32, copy=True),
            parte["clase"].to_numpy(dtype=np.int64, copy=True))


def cargar_datos(processed: Path, artifacts: Path) -> Datos:
    """Datos para entrenar: solo train y val. El split test no sale de esta función."""
    df, vocabulario, clases = leer_dataset(processed, artifacts)
    X_train, y_train = tomar_split(df, vocabulario, "train")
    X_val, y_val = tomar_split(df, vocabulario, "val")
    return Datos(X_train, y_train, X_val, y_val, vocabulario, clases)


def pesos_por_clase(y: np.ndarray, n_clases: int) -> torch.Tensor:
    """Peso inversamente proporcional a la frecuencia: n / (n_clases * casos_de_la_clase)."""
    conteo = np.bincount(y, minlength=n_clases)
    if (conteo == 0).any():
        raise ErrorDeEntrenamiento("Hay clases sin ningún ejemplo en train")
    return torch.tensor(len(y) / (n_clases * conteo), dtype=torch.float32)


def _fijar_semilla(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def _evaluar(modelo: nn.Module, X: torch.Tensor, y: torch.Tensor, perdida: nn.Module, lote: int) -> dict:
    """Pérdida y exactitud top-1 y top-3 sobre (X, y), sin gradientes y con dropout apagado."""
    modelo.eval()
    perdida_total, top1, top3 = 0.0, 0, 0
    with torch.no_grad():
        for i in range(0, len(X), lote):
            xb, yb = X[i:i + lote], y[i:i + lote]
            logits = modelo(xb)
            # La pérdida ponderada se normaliza por la suma de pesos; se acumula multiplicando
            # de vuelta para promediar bien entre lotes de pesos distintos.
            perdida_total += perdida(logits, yb).item() * _peso_lote(perdida, yb)
            mejores = logits.topk(min(3, logits.shape[1]), dim=1).indices
            top1 += (mejores[:, 0] == yb).sum().item()
            top3 += (mejores == yb[:, None]).any(dim=1).sum().item()
    return {
        "loss": perdida_total / _peso_lote(perdida, y),
        "top1": top1 / len(y),
        "top3": top3 / len(y),
    }


def _peso_lote(perdida: nn.Module, y: torch.Tensor) -> float:
    """Suma de los pesos de las muestras de y (o su cantidad si la pérdida no tiene pesos)."""
    pesos = getattr(perdida, "weight", None)
    return float(pesos[y].sum()) if pesos is not None else float(len(y))


def entrenar(
    X_train: np.ndarray, y_train: np.ndarray, X_val: np.ndarray, y_val: np.ndarray,
    n_clases: int, hp: dict, seed: int,
) -> Resultado:
    """Entrena el MLP y devuelve los pesos de la época con menor pérdida en val.

    hp: hidden_layers, dropout, learning_rate, batch_size, epochs, patience, class_weights.
    Misma semilla y mismos datos dan el mismo resultado.
    """
    if hp["class_weights"] not in ("balanced", "none"):
        raise ErrorDeEntrenamiento("class_weights debe ser 'balanced' o 'none'")
    _fijar_semilla(seed)

    modelo = crear_mlp(X_train.shape[1], n_clases, hp["hidden_layers"], hp["dropout"])
    pesos = pesos_por_clase(y_train, n_clases) if hp["class_weights"] == "balanced" else None
    perdida = nn.CrossEntropyLoss(weight=pesos)
    optimizador = torch.optim.Adam(modelo.parameters(), lr=hp["learning_rate"])

    Xt, yt = torch.from_numpy(X_train), torch.from_numpy(y_train)
    Xv, yv = torch.from_numpy(X_val), torch.from_numpy(y_val)
    lote = hp["batch_size"]
    barajador = torch.Generator().manual_seed(seed)  # orden de los lotes, independiente del resto

    historial: list[dict] = []
    mejor_estado, mejor_loss, mejor_epoca, sin_mejora = None, float("inf"), 0, 0
    for epoca in range(1, hp["epochs"] + 1):
        modelo.train()
        orden = torch.randperm(len(Xt), generator=barajador)
        for i in range(0, len(orden), lote):
            idx = orden[i:i + lote]
            optimizador.zero_grad()
            perdida(modelo(Xt[idx]), yt[idx]).backward()
            optimizador.step()

        fila = {
            "epoca": epoca,
            **{f"train_{k}": v for k, v in _evaluar(modelo, Xt, yt, perdida, 2048).items()},
            **{f"val_{k}": v for k, v in _evaluar(modelo, Xv, yv, perdida, 2048).items()},
        }
        historial.append(fila)
        log.info("época %02d | train loss %.4f top1 %.3f | val loss %.4f top1 %.3f top3 %.3f",
                 epoca, fila["train_loss"], fila["train_top1"],
                 fila["val_loss"], fila["val_top1"], fila["val_top3"])

        if fila["val_loss"] < mejor_loss - TOLERANCIA_MEJORA:
            mejor_loss, mejor_epoca, sin_mejora = fila["val_loss"], epoca, 0
            mejor_estado = copy.deepcopy(modelo.state_dict())
        else:
            sin_mejora += 1
            if sin_mejora >= hp["patience"]:
                log.info("Sin mejora en val durante %d épocas: se detiene el entrenamiento", sin_mejora)
                break

    if mejor_estado is None:  # la pérdida nunca fue finita o epochs=0
        raise ErrorDeEntrenamiento("El entrenamiento no produjo ninguna época válida")
    mejor = historial[mejor_epoca - 1]
    return Resultado(
        estado=mejor_estado,
        historial=historial,
        mejor_epoca=mejor_epoca,
        metricas_val={k.removeprefix("val_"): v for k, v in mejor.items() if k.startswith("val_")},
    )


def _huella(estado: dict[str, torch.Tensor]) -> str:
    """Hash de los pesos: identifica la versión del modelo y es igual si el entrenamiento se repite."""
    h = hashlib.sha256()
    for nombre in sorted(estado):
        h.update(nombre.encode())
        h.update(estado[nombre].cpu().numpy().tobytes())
    return h.hexdigest()


def guardar(res: Resultado, datos: Datos, hp: dict, seed: int, artifacts: Path) -> dict[str, Path]:
    """Escribe model.pt (solo pesos) y metadata.json en artifacts/."""
    artifacts.mkdir(parents=True, exist_ok=True)
    destino = {"modelo": artifacts / "model.pt", "metadata": artifacts / "metadata.json"}
    torch.save(res.estado, destino["modelo"])

    vocabulario_bytes = (artifacts / "symptoms.json").read_bytes()
    metadata = {
        "version": f"mlp-{_huella(res.estado)[:8]}",
        "fecha_entrenamiento": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "semilla": seed,
        "arquitectura": {
            "n_entrada": len(datos.vocabulario),
            "n_clases": len(datos.clases),
            "hidden_layers": hp["hidden_layers"],
            "dropout": hp["dropout"],
        },
        "entrenamiento": {
            "learning_rate": hp["learning_rate"],
            "batch_size": hp["batch_size"],
            "epochs_max": hp["epochs"],
            "patience": hp["patience"],
            "class_weights": hp["class_weights"],
            "mejor_epoca": res.mejor_epoca,
            "epocas_ejecutadas": len(res.historial),
        },
        "datos": {
            "filas_train": int(len(datos.y_train)),
            "filas_val": int(len(datos.y_val)),
            # Permite al predictor comprobar que symptoms.json es el del entrenamiento
            "vocabulario_sha256": hashlib.sha256(vocabulario_bytes).hexdigest(),
            "torch": torch.__version__,
        },
        "metricas_val": res.metricas_val,
        "clases": datos.clases,
    }
    destino["metadata"].write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destino


def ejecutar(cfg: dict | None = None) -> Resultado:
    cfg = cfg or cargar_config()
    hp = cfg["train"]
    artifacts = ruta(cfg, "artifacts")

    datos = cargar_datos(ruta(cfg, "processed"), artifacts)
    log.info("Datos: train %s | val %s | %d síntomas | %d clases",
             f"{len(datos.y_train):,}", f"{len(datos.y_val):,}", len(datos.vocabulario), len(datos.clases))
    log.info("Hiperparámetros: %s", hp)

    res = entrenar(datos.X_train, datos.y_train, datos.X_val, datos.y_val, len(datos.clases), hp, cfg["seed"])
    salidas = guardar(res, datos, hp, cfg["seed"], artifacts)

    m = res.metricas_val
    log.info("Mejor época: %d de %d | val: loss %.4f, top1 %.3f, top3 %.3f",
             res.mejor_epoca, len(res.historial), m["loss"], m["top1"], m["top3"])
    for nombre, destino in salidas.items():
        log.info("  %-9s %s", nombre, destino)
    return res


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    try:
        ejecutar()
    except ErrorDeEntrenamiento as error:
        raise SystemExit(f"Entrenamiento detenido: {error}")


if __name__ == "__main__":
    main()
