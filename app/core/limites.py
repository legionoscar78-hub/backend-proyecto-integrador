"""Límite de intentos fallidos (login y acceso con llave), en memoria.

Cuenta los fallos de cada clave dentro de una ventana de tiempo deslizante. Cuando una clave llega
al máximo, queda bloqueada hasta que su fallo más antiguo salga de la ventana.

Alcance (a propósito simple):
  - Vive en la memoria del proceso: si el servidor se reinicia, los contadores empiezan de cero, y
    con varios procesos (uvicorn --workers N) cada uno cuenta por separado. Para eso haría falta
    Redis o una tabla; el esquema de la base está fijado por docs/ScriptDb.sql y no la incluye.
  - La IP es la del cliente que ve el servidor: detrás de un proxy inverso será la del proxy
    (configurar uvicorn con --proxy-headers y --forwarded-allow-ips)."""
import math
import threading
import time
from collections import deque
from collections.abc import Callable

MAX_CLAVES = 10_000  # tope de memoria: nadie debe poder llenarla inventando claves


class LimiteIntentos:
    def __init__(self, ventana_segundos: float, reloj: Callable[[], float] = time.monotonic):
        self.ventana = ventana_segundos
        self._reloj = reloj
        self._fallos: dict[str, deque[float]] = {}
        self._candado = threading.Lock()

    def _vigentes(self, clave: str, ahora: float) -> deque[float] | None:
        fallos = self._fallos.get(clave)
        if fallos is None:
            return None
        while fallos and fallos[0] <= ahora - self.ventana:
            fallos.popleft()
        if not fallos:
            del self._fallos[clave]
            return None
        return fallos

    def espera(self, clave: str, maximo: int) -> int:
        """Segundos que faltan para poder intentar de nuevo; 0 si la clave no está bloqueada."""
        with self._candado:
            ahora = self._reloj()
            fallos = self._vigentes(clave, ahora)
            if fallos is None or len(fallos) < maximo:
                return 0
            # el bloqueo termina cuando salga de la ventana el fallo que deja la cuenta bajo el máximo
            libera = fallos[len(fallos) - maximo]
            return max(1, math.ceil(libera + self.ventana - ahora))

    def fallo(self, clave: str) -> None:
        with self._candado:
            ahora = self._reloj()
            if clave not in self._fallos and len(self._fallos) >= MAX_CLAVES:
                self._purgar(ahora)
            self._fallos.setdefault(clave, deque()).append(ahora)

    def reiniciar(self, clave: str) -> None:
        with self._candado:
            self._fallos.pop(clave, None)

    def limpiar(self) -> None:
        """Borra todos los contadores (para las pruebas)."""
        with self._candado:
            self._fallos.clear()

    def _purgar(self, ahora: float) -> None:
        for clave in list(self._fallos):
            self._vigentes(clave, ahora)
        if len(self._fallos) >= MAX_CLAVES:  # todo sigue vigente: se descartan las claves más viejas
            viejas = sorted(self._fallos, key=lambda c: self._fallos[c][-1])[: MAX_CLAVES // 2]
            for clave in viejas:
                del self._fallos[clave]


def _crear() -> tuple[LimiteIntentos, LimiteIntentos]:
    from app.core.config import settings  # import tardío: así el módulo se prueba sin Settings

    ventana = settings.intentos_ventana_minutos * 60
    return LimiteIntentos(ventana), LimiteIntentos(ventana)


intentos_login, intentos_llave = _crear()
