"""Append-only JSONL trace. Every step, LLM call and finding of a run is one line,
so any metric can be recomputed offline from the trace alone."""

from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Lock


class Trace:
    def __init__(self, path: Path, run_id: str):
        self.path = path
        self.run_id = run_id
        self._lock = Lock()
        self._fh = path.open("a", encoding="utf-8")
        self.t0 = time.time()

    def event(self, type_: str, **data) -> None:
        rec = {"t": round(time.time() - self.t0, 3), "type": type_, **data}
        line = json.dumps(rec, ensure_ascii=False, default=str)
        with self._lock:
            self._fh.write(line + "\n")
            self._fh.flush()

    def close(self) -> None:
        self._fh.close()


def read_trace(path: Path) -> list[dict]:
    out = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out
