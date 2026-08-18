"""Ordered model-provider fallback without hidden retries."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from .failure import ErrorClassifier, FailureKind


class FallbackTelemetry(Protocol):
    def on_provider(self, provider: str, index: int) -> None: ...

    def on_fallback(
        self, failed_provider: str, next_provider: str, failure: FailureKind
    ) -> None: ...


class NoOpFallbackTelemetry:
    def on_provider(self, provider: str, index: int) -> None:
        return None

    def on_fallback(self, failed_provider: str, next_provider: str, failure: FailureKind) -> None:
        return None


@dataclass(frozen=True, slots=True)
class ModelProvider:
    name: str
    invoke: Callable[[Mapping[str, Any]], Mapping[str, Any]]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("provider name must not be blank")


class FallbackExhaustedError(RuntimeError):
    pass


class FallbackModel:
    def __init__(
        self,
        providers: Sequence[ModelProvider],
        *,
        classifier: ErrorClassifier | None = None,
        fallback_kinds: frozenset[FailureKind] = frozenset(
            {FailureKind.TRANSIENT, FailureKind.RATE_LIMITED, FailureKind.TIMEOUT}
        ),
        telemetry: FallbackTelemetry | None = None,
    ) -> None:
        if not providers:
            raise ValueError("at least one provider is required")
        self._providers = tuple(providers)
        self._classifier = classifier or ErrorClassifier()
        self._fallback_kinds = fallback_kinds
        self._telemetry = telemetry or NoOpFallbackTelemetry()

    def invoke(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        last_error: Exception | None = None
        for index, provider in enumerate(self._providers):
            self._telemetry.on_provider(provider.name, index)
            try:
                return provider.invoke(request)
            except Exception as error:
                failure = self._classifier.classify(error)
                last_error = error
                has_next = index + 1 < len(self._providers)
                if failure.kind not in self._fallback_kinds or not has_next:
                    if not has_next and failure.kind in self._fallback_kinds:
                        raise FallbackExhaustedError("all model providers failed") from error
                    raise
                next_provider = self._providers[index + 1]
                self._telemetry.on_fallback(provider.name, next_provider.name, failure.kind)
        raise FallbackExhaustedError("all model providers failed") from last_error
