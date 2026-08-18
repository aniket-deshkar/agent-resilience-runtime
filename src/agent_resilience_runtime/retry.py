"""Operation-specific exponential retry execution."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TypeVar

from .failure import ClassifiedFailure, ErrorClassifier, FailureKind

ResultT = TypeVar("ResultT")


class RetryTelemetry(Protocol):
    def on_attempt(self, operation: str, attempt: int) -> None: ...

    def on_retry(
        self,
        operation: str,
        attempt: int,
        failure: ClassifiedFailure,
        delay_seconds: float,
    ) -> None: ...

    def on_exhausted(self, operation: str, attempts: int, failure: ClassifiedFailure) -> None: ...


class NoOpRetryTelemetry:
    def on_attempt(self, operation: str, attempt: int) -> None:
        return None

    def on_retry(
        self,
        operation: str,
        attempt: int,
        failure: ClassifiedFailure,
        delay_seconds: float,
    ) -> None:
        return None

    def on_exhausted(self, operation: str, attempts: int, failure: ClassifiedFailure) -> None:
        return None


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int
    initial_delay_seconds: float
    maximum_delay_seconds: float
    multiplier: float = 2.0
    jitter_ratio: float = 0.0
    retryable_kinds: frozenset[FailureKind] = frozenset(
        {FailureKind.TRANSIENT, FailureKind.RATE_LIMITED, FailureKind.TIMEOUT}
    )

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if self.initial_delay_seconds < 0 or self.maximum_delay_seconds < 0:
            raise ValueError("delays must be non-negative")
        if self.initial_delay_seconds > self.maximum_delay_seconds:
            raise ValueError("initial delay must not exceed maximum delay")
        if self.multiplier < 1:
            raise ValueError("multiplier must be at least one")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between zero and one")

    def delay(self, retry_number: int, random_value: float) -> float:
        if retry_number < 1:
            raise ValueError("retry_number must be positive")
        if not 0 <= random_value <= 1:
            raise ValueError("random_value must be between zero and one")
        base = min(
            self.maximum_delay_seconds,
            self.initial_delay_seconds * self.multiplier ** (retry_number - 1),
        )
        factor = 1 - self.jitter_ratio + (2 * self.jitter_ratio * random_value)
        return base * factor


@dataclass(frozen=True, slots=True)
class ModelRetryPolicy(RetryPolicy):
    max_attempts: int = 3
    initial_delay_seconds: float = 0.25
    maximum_delay_seconds: float = 4.0
    multiplier: float = 2.0
    jitter_ratio: float = 0.2


@dataclass(frozen=True, slots=True)
class ToolRetryPolicy(RetryPolicy):
    max_attempts: int = 2
    initial_delay_seconds: float = 0.1
    maximum_delay_seconds: float = 1.0
    multiplier: float = 2.0
    jitter_ratio: float = 0.1


class RetryExecutor:
    def __init__(
        self,
        classifier: ErrorClassifier | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        random_value: Callable[[], float] = random.random,
        telemetry: RetryTelemetry | None = None,
    ) -> None:
        self._classifier = classifier or ErrorClassifier()
        self._sleep = sleep
        self._random_value = random_value
        self._telemetry = telemetry or NoOpRetryTelemetry()

    def execute(
        self, operation_name: str, operation: Callable[[], ResultT], policy: RetryPolicy
    ) -> ResultT:
        for attempt in range(1, policy.max_attempts + 1):
            self._telemetry.on_attempt(operation_name, attempt)
            try:
                return operation()
            except Exception as error:
                failure = self._classifier.classify(error)
                should_retry = (
                    failure.kind in policy.retryable_kinds and attempt < policy.max_attempts
                )
                if not should_retry:
                    self._telemetry.on_exhausted(operation_name, attempt, failure)
                    raise
                policy_delay = policy.delay(attempt, self._random_value())
                delay = max(policy_delay, failure.retry_after_seconds or 0)
                self._telemetry.on_retry(operation_name, attempt, failure, delay)
                self._sleep(delay)
        raise AssertionError("retry loop must return or raise")
