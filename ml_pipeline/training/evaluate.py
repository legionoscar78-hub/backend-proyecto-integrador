"""Evaluación final del modelo sobre el split test. Ejecutar desde backend/ después de entrenar:

    python -m ml_pipeline.training.evaluate

Es la medición definitiva: test no se usó para entrenar ni para elegir la época. Por eso se
corre una sola vez por modelo; si se ajustan hiperparámetros mirando estos números, dejan de
ser una estimación honesta. Si metadata.json ya tiene metricas_test, el script se niega a
repetirse salvo que se pase --forzar. Al reentrenar, metadata.json se reescribe y el modelo
nuevo vuelve a quedar sin evaluar.
"""
import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

from app.ml.model import ErrorDeArtefactos, cargar_modelo
from ml_pipeline.config import cargar_config, ruta
from ml_pipeline.training.train import ErrorDeEntrenamiento, leer_dataset, tomar_split

log = logging.getLogger("evaluate")

KS = (1, 3, 5)
N_PEOR_CLASES = 10
N_CONFUSIONES = 15
BINS_CALIBRACION = 10


def probabilidades(modelo: torch.nn.Module, X: np.ndarray, lote: int = 2048) -> np.ndarray:
    """Softmax de las salidas del modelo, una fila por caso. float64 para sumar sin pérdida."""
    modelo.eval()
    salidas = []
    with torch.no_grad():
        for i in range(0, len(X), lote):
            salidas.append(torch.softmax(modelo(torch.from_numpy(X[i:i + lote])), dim=1).double().numpy())
    return np.concatenate(salidas)


def matriz_confusion(y: np.ndarray, pred: np.ndarray, n_clases: int) -> np.ndarray:
    """m[real, predicho] = número de casos."""
    m = np.zeros((n_clases, n_clases), dtype=np.int64)
    np.add.at(m, (y, pred), 1)
    return m


def _dividir(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    """num/den, con 0 donde el denominador es 0 (clase que nunca se predijo, por ejemplo)."""
    return np.divide(num, den, out=np.zeros(len(num)), where=den > 0)


def metricas_globales(probs: np.ndarray, y: np.ndarray, matriz: np.ndarray) -> dict:
    n_clases = probs.shape[1]
    orden = np.argsort(-probs, axis=1)
    resultado = {"casos": int(len(y))}
    for k in KS:  # con menos de k clases, top-k es 1.0; la clave se mantiene para no cambiar el formato
        resultado[f"top{k}"] = float((orden[:, :min(k, n_clases)] == y[:, None]).any(axis=1).mean())

    diag = np.diag(matriz).astype(float)
    soporte, predichos = matriz.sum(axis=1), matriz.sum(axis=0)
    recall, precision = _dividir(diag, soporte), _dividir(diag, predichos)
    f1 = _dividir(2 * precision * recall, precision + recall)
    con_casos = soporte > 0  # el macro se promedia solo sobre enfermedades que aparecen en test
    resultado["macro_f1"] = float(f1[con_casos].mean())
    resultado["macro_recall"] = float(recall[con_casos].mean())  # = exactitud balanceada
    resultado["macro_precision"] = float(precision[con_casos].mean())
    resultado["log_loss"] = float(-np.log(np.clip(probs[np.arange(len(y)), y], 1e-12, 1)).mean())
    # Referencia mínima: siempre responder la enfermedad más frecuente en test
    resultado["top1_clase_mayoritaria"] = float(soporte.max() / len(y))
    return resultado


def metricas_por_clase(matriz: np.ndarray, clases: list[dict]) -> list[dict]:
    diag = np.diag(matriz).astype(float)
    soporte, predichos = matriz.sum(axis=1), matriz.sum(axis=0)
    recall, precision = _dividir(diag, soporte), _dividir(diag, predichos)
    f1 = _dividir(2 * precision * recall, precision + recall)
    return [
        {
            "indice": c["indice"], "enfermedad_en": c["enfermedad_en"], "enfermedad_es": c["enfermedad_es"],
            "casos": int(soporte[i]), "precision": float(precision[i]), "recall": float(recall[i]), "f1": float(f1[i]),
        }
        for i, c in enumerate(clases)
    ]


def confusiones_principales(matriz: np.ndarray, clases: list[dict], n: int) -> list[dict]:
    """Las n parejas (real -> predicho) con más errores."""
    errores = matriz.copy()
    np.fill_diagonal(errores, 0)
    soporte = matriz.sum(axis=1)
    planos = np.argsort(-errores, axis=None, kind="stable")[:n]
    salida = []
    for plano in planos:
        real, pred = divmod(int(plano), matriz.shape[1])
        casos = int(errores[real, pred])
        if casos == 0:
            break
        salida.append({
            "real_en": clases[real]["enfermedad_en"], "real_es": clases[real]["enfermedad_es"],
            "predicho_en": clases[pred]["enfermedad_en"], "predicho_es": clases[pred]["enfermedad_es"],
            "casos": casos, "porcentaje_de_la_real": float(casos / soporte[real]),
        })
    return salida


def calibracion(probs: np.ndarray, y: np.ndarray, bins: int = BINS_CALIBRACION) -> dict:
    """Compara la confianza del modelo (probabilidad de su primera opción) con su acierto real.

    ECE = promedio, ponderado por casos, de |acierto - confianza| en cada tramo de confianza.
    Con 0 estaría perfectamente calibrado.
    """
    confianza = probs.max(axis=1)
    acierto = (probs.argmax(axis=1) == y).astype(float)
    bordes = np.linspace(0, 1, bins + 1)
    tramo = np.clip(np.digitize(confianza, bordes[1:-1]), 0, bins - 1)
    ece, detalle = 0.0, []
    for b in range(bins):
        en_tramo = tramo == b
        if not en_tramo.any():
            continue
        c, a = float(confianza[en_tramo].mean()), float(acierto[en_tramo].mean())
        ece += en_tramo.mean() * abs(a - c)
        detalle.append({"desde": float(bordes[b]), "hasta": float(bordes[b + 1]),
                        "casos": int(en_tramo.sum()), "confianza": c, "acierto": a})
    return {
        "ece": float(ece),
        "confianza_media": float(confianza.mean()),
        "confianza_media_si_acierta": float(confianza[acierto == 1].mean()) if acierto.any() else None,
        "confianza_media_si_falla": float(confianza[acierto == 0].mean()) if (acierto == 0).any() else None,
        "tramos": detalle,
    }


def ambiguedad(X_train: np.ndarray, X_test: np.ndarray, acierta: np.ndarray) -> dict:
    """Mide cuánto del error viene de casos que el dataset no distingue.

    El ETL quita las filas exactamente repetidas (síntomas + enfermedad) antes de dividir, así
    que si el vector de síntomas de un caso de test aparece en train es porque allí tiene OTRA
    enfermedad: ningún modelo puede acertar los dos. Separa el acierto en esos casos del resto.
    """
    firmas_train = {fila.tobytes() for fila in X_train.astype(np.uint8)}
    ambiguo = np.array([fila.tobytes() in firmas_train for fila in X_test.astype(np.uint8)])
    def _tasa(mascara):
        return float(acierta[mascara].mean()) if mascara.any() else None
    return {
        "casos_ambiguos": int(ambiguo.sum()),
        "porcentaje_ambiguos": float(ambiguo.mean()),
        "top1_en_ambiguos": _tasa(ambiguo),
        "top1_en_no_ambiguos": _tasa(~ambiguo),
    }


def evaluar(modelo: torch.nn.Module, X_train: np.ndarray, X_test: np.ndarray, y_test: np.ndarray,
            clases: list[dict]) -> dict:
    """Todas las métricas sobre test, listas para guardar como JSON."""
    probs = probabilidades(modelo, X_test)
    pred = probs.argmax(axis=1)
    matriz = matriz_confusion(y_test, pred, len(clases))
    por_clase = metricas_por_clase(matriz, clases)
    return {
        "globales": metricas_globales(probs, y_test, matriz),
        "calibracion": calibracion(probs, y_test),
        "ambiguedad": ambiguedad(X_train, X_test, pred == y_test),
        "peores_clases_por_recall": sorted(por_clase, key=lambda c: (c["recall"], c["indice"]))[:N_PEOR_CLASES],
        "confusiones_principales": confusiones_principales(matriz, clases, N_CONFUSIONES),
        "por_clase": por_clase,
    }


def _escribir_json(destino: Path, contenido) -> None:
    destino.write_text(json.dumps(contenido, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ejecutar(cfg: dict | None = None, forzar: bool = False) -> dict:
    cfg = cfg or cargar_config()
    artifacts, processed = ruta(cfg, "artifacts"), ruta(cfg, "processed")

    modelo, metadata = cargar_modelo(artifacts)
    if "metricas_test" in metadata and not forzar:
        raise ErrorDeEntrenamiento(
            f"El modelo {metadata['version']} ya se evaluó en test el {metadata['metricas_test']['evaluado_en']}. "
            "Repetir la evaluación mirando test para ajustar el modelo sesga el resultado. "
            "Si de verdad hace falta, usa --forzar."
        )

    df, vocabulario, clases = leer_dataset(processed, artifacts)
    if [c["indice"] for c in clases] != [c["indice"] for c in metadata["clases"]] or \
            [c["enfermedad_en"] for c in clases] != [c["enfermedad_en"] for c in metadata["clases"]]:
        raise ErrorDeEntrenamiento("Las clases del dataset no coinciden con las del modelo. Reentrena.")

    X_train, _ = tomar_split(df, vocabulario, "train")
    X_test, y_test = tomar_split(df, vocabulario, "test")
    log.info("Evaluando %s sobre %s casos de test", metadata["version"], f"{len(y_test):,}")
    informe = evaluar(modelo, X_train, X_test, y_test, clases)

    evaluado_en = datetime.now(timezone.utc).isoformat(timespec="seconds")
    informe = {"modelo": metadata["version"], "evaluado_en": evaluado_en, **informe}
    destino = processed / "evaluacion_test.json"
    _escribir_json(destino, informe)

    # Resumen en metadata.json: lo que el predictor puede mostrar sin leer el informe completo
    metadata["metricas_test"] = {"evaluado_en": evaluado_en, **informe["globales"],
                                 "ece": informe["calibracion"]["ece"]}
    _escribir_json(artifacts / "metadata.json", metadata)
    log.info("Informe completo: %s", destino)
    return informe


def _resumen(informe: dict) -> str:
    g, cal, amb = informe["globales"], informe["calibracion"], informe["ambiguedad"]
    lineas = [
        f"Modelo {informe['modelo']} en test ({g['casos']:,} casos)",
        f"  top-1 {g['top1']:.3f} | top-3 {g['top3']:.3f} | top-5 {g['top5']:.3f}",
        f"  macro-F1 {g['macro_f1']:.3f} | macro-recall {g['macro_recall']:.3f} | log-loss {g['log_loss']:.3f}",
        f"  referencia (siempre la clase más frecuente): top-1 {g['top1_clase_mayoritaria']:.3f}",
        f"  calibración: ECE {cal['ece']:.3f} | confianza media {cal['confianza_media']:.3f} "
        f"(si acierta {cal['confianza_media_si_acierta']:.3f}, si falla {cal['confianza_media_si_falla']:.3f})",
        f"  casos ambiguos (mismo vector de síntomas visto en train con otra enfermedad): "
        f"{amb['porcentaje_ambiguos']:.1%} | top-1 en ellos {amb['top1_en_ambiguos']:.3f}, "
        f"en el resto {amb['top1_en_no_ambiguos']:.3f}",
        "",
        f"Las {len(informe['peores_clases_por_recall'])} enfermedades con menor recall:",
    ]
    lineas += [f"  {c['recall']:.2f}  {c['enfermedad_es']} ({c['casos']} casos)"
               for c in informe["peores_clases_por_recall"]]
    lineas += ["", "Confusiones más frecuentes (real -> predicho):"]
    lineas += [f"  {c['casos']:>3}  {c['real_es']} -> {c['predicho_es']} ({c['porcentaje_de_la_real']:.0%} de la real)"
               for c in informe["confusiones_principales"][:10]]
    return "\n".join(lineas)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evalúa el modelo entrenado sobre el split test.")
    parser.add_argument("--forzar", action="store_true", help="repite la evaluación aunque el modelo ya se haya evaluado")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    try:
        informe = ejecutar(forzar=args.forzar)
    except (ErrorDeEntrenamiento, ErrorDeArtefactos) as error:
        raise SystemExit(f"Evaluación detenida: {error}")
    print("\n" + _resumen(informe))


if __name__ == "__main__":
    main()
