import json
import logging
from collections import Counter
from threading import Lock


class JsonFormatter(logging.Formatter):
    """CloudWatch-friendly structured logs without coupling to an SDK."""
    def format(self, record: logging.LogRecord) -> str:
        payload = {"level": record.levelname, "logger": record.name, "message": record.getMessage()}
        for key in ("request_id", "method", "path", "status_code", "duration_ms", "job_id"):
            if hasattr(record, key): payload[key] = getattr(record, key)
        return json.dumps(payload, default=str)


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("cloudmind")
    if not logger.handlers:
        handler = logging.StreamHandler(); handler.setFormatter(JsonFormatter())
        logger.addHandler(handler); logger.setLevel(logging.INFO); logger.propagate = False
    return logger


class Metrics:
    def __init__(self): self._counts: Counter[str] = Counter(); self._durations: Counter[str] = Counter(); self._lock = Lock()
    def increment(self, name: str) -> None:
        with self._lock: self._counts[name] += 1
    def observe_ms(self, name: str, duration_ms: float) -> None:
        with self._lock: self._durations[name] += duration_ms
    def prometheus(self) -> str:
        with self._lock:
            lines = ["# CloudMind process-local operational counters."]
            lines += [f"cloudmind_{key}_total {value}" for key, value in sorted(self._counts.items())]
            lines += [f"cloudmind_{key}_milliseconds_total {value:.3f}" for key, value in sorted(self._durations.items())]
        return "\n".join(lines) + "\n"


metrics = Metrics()
