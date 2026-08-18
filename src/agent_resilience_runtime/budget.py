"""Step, deadline, token, and cost budget enforcement."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from .failure import BudgetExceededError


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class BudgetLimits:
    max_steps: int
    deadline: datetime | None = None
    max_tokens: int | None = None
    max_cost: Decimal | None = None

    def __post_init__(self) -> None:
        if self.max_steps < 1:
            raise ValueError("max_steps must be positive")
        if self.deadline is not None and self.deadline.tzinfo is None:
            raise ValueError("deadline must be timezone-aware")
        if self.max_tokens is not None and self.max_tokens < 0:
            raise ValueError("max_tokens must be non-negative")
        if self.max_cost is not None and self.max_cost < 0:
            raise ValueError("max_cost must be non-negative")


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    steps: int
    tokens: int
    cost: Decimal


class ExecutionBudget:
    def __init__(self, limits: BudgetLimits, *, clock: Clock | None = None) -> None:
        self.limits = limits
        self._clock = clock or SystemClock()
        self._steps = 0
        self._tokens = 0
        self._cost = Decimal(0)
        self._lock = threading.Lock()

    def before_step(self) -> BudgetSnapshot:
        with self._lock:
            self._check_deadline()
            if self._steps >= self.limits.max_steps:
                raise BudgetExceededError("maximum step budget exceeded")
            self._steps += 1
            return self._snapshot()

    def record_usage(
        self,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost: Decimal | None = None,
    ) -> BudgetSnapshot:
        token_delta = (input_tokens or 0) + (output_tokens or 0)
        cost_delta = cost or Decimal(0)
        if token_delta < 0 or cost_delta < 0:
            raise ValueError("usage deltas must be non-negative")
        with self._lock:
            self._check_deadline()
            new_tokens = self._tokens + token_delta
            new_cost = self._cost + cost_delta
            if self.limits.max_tokens is not None and new_tokens > self.limits.max_tokens:
                raise BudgetExceededError("token budget exceeded")
            if self.limits.max_cost is not None and new_cost > self.limits.max_cost:
                raise BudgetExceededError("cost budget exceeded")
            self._tokens = new_tokens
            self._cost = new_cost
            return self._snapshot()

    def snapshot(self) -> BudgetSnapshot:
        with self._lock:
            return self._snapshot()

    def _check_deadline(self) -> None:
        if self.limits.deadline is not None and self._clock.now() >= self.limits.deadline:
            raise BudgetExceededError("execution deadline exceeded")

    def _snapshot(self) -> BudgetSnapshot:
        return BudgetSnapshot(self._steps, self._tokens, self._cost)
