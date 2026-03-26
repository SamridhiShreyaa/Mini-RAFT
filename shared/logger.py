import logging
from datetime import datetime
from typing import Any


class ElectionLogger:
    """Election and failover events."""

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self._logger = logging.getLogger(f"consensus.{node_id}")
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter("%(message)s")
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)
            self._logger.setLevel(logging.INFO)

    def _emit(self, level: int, event: str, **meta: Any) -> None:
        payload = {
            "ts": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "node": self.node_id,
            "event": event,
            "meta": meta,
        }
        self._logger.log(level, str(payload))

    def info(self, event: str, **meta: Any) -> None:
        self._emit(logging.INFO, event, **meta)

    def warning(self, event: str, **meta: Any) -> None:
        self._emit(logging.WARNING, event, **meta)

    def error(self, event: str, **meta: Any) -> None:
        self._emit(logging.ERROR, event, **meta)
