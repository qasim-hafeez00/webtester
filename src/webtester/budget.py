"""Shared run budget. All workers of a run draw from one budget, which is what
makes "equal total budget" comparisons across conditions possible."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .config import BudgetConfig


@dataclass
class Budget:
    cfg: BudgetConfig
    steps: int = 0
    tokens: int = 0
    browser_seconds: float = 0.0  # summed over workers
    started: float = field(default_factory=time.monotonic)

    def elapsed_min(self) -> float:
        return (time.monotonic() - self.started) / 60

    def charge(self, *, steps: int = 0, tokens: int = 0, browser_seconds: float = 0.0) -> None:
        self.steps += steps
        self.tokens += tokens
        self.browser_seconds += browser_seconds

    def exhausted(self) -> str | None:
        if self.steps >= self.cfg.max_steps:
            return "max_steps"
        if self.tokens >= self.cfg.max_tokens:
            return "max_tokens"
        if self.elapsed_min() >= self.cfg.max_minutes:
            return "max_minutes"
        return None

    def snapshot(self) -> dict:
        return {
            "steps": self.steps,
            "tokens": self.tokens,
            "browser_minutes": round(self.browser_seconds / 60, 3),
            "wall_minutes": round(self.elapsed_min(), 3),
        }
