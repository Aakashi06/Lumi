"""Local-only timings. No source text or telemetry is transmitted externally."""

from collections import deque
from contextlib import contextmanager
from threading import Lock
from time import perf_counter

from fastapi.responses import JSONResponse

STAGES = (
    "document_parsing",
    "chunking",
    "entity_extraction",
    "relationship_extraction",
    "embedding_generation",
    "graph_construction",
    "serialization",
)
_samples = deque(maxlen=100)
_lock = Lock()


def record(name: str, duration_ms: float, **metadata):
    with _lock:
        _samples.append({"stage": name, "duration_ms": round(duration_ms, 3), **metadata})


def snapshot():
    with _lock:
        return list(_samples)


class Timings:
    def __init__(self):
        self.ms = dict.fromkeys(STAGES, 0.0)

    @contextmanager
    def measure(self, stage):
        started = perf_counter()
        try:
            yield
        finally:
            self.ms[stage] = self.ms.get(stage, 0.0) + (perf_counter() - started) * 1000

    def values(self):
        return {key: round(value, 3) for key, value in self.ms.items()}


class TimedJSONResponse(JSONResponse):
    def render(self, content):
        started = perf_counter()
        result = super().render(content)
        duration = (perf_counter() - started) * 1000
        self.serialization_ms = duration
        record("serialization", duration, bytes=len(result))
        return result

    def init_headers(self, headers=None):
        super().init_headers(headers)
        self.headers["Server-Timing"] = f"json;dur={getattr(self, 'serialization_ms', 0):.3f}"
