"""Agent-operation failure taxonomy and deterministic classification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FailureKind(StrEnum):
    TRANSIENT = "transient"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    AUTHORIZATION = "authorization"
    VALIDATION = "validation"
    PERMANENT = "permanent"
    BUDGET_EXCEEDED = "budget_exceeded"
    LOOP_DETECTED = "loop_detected"


@dataclass(frozen=True, slots=True)
class ClassifiedFailure:
    kind: FailureKind
    retry_after_seconds: float | None = None

    @property
    def retryable(self) -> bool:
        return self.kind in {
            FailureKind.TRANSIENT,
            FailureKind.RATE_LIMITED,
            FailureKind.TIMEOUT,
        }


class AgentOperationError(RuntimeError):
    pass


class TransientAgentError(AgentOperationError):
    pass


class RateLimitedAgentError(AgentOperationError):
    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class AgentTimeoutError(AgentOperationError):
    pass


class AuthorizationAgentError(AgentOperationError):
    pass


class ValidationAgentError(AgentOperationError):
    pass


class PermanentAgentError(AgentOperationError):
    pass


class BudgetExceededError(AgentOperationError):
    pass


class LoopDetectedError(AgentOperationError):
    pass


class ErrorClassifier:
    """Classifies known errors conservatively; unknown failures are permanent."""

    def classify(self, error: BaseException) -> ClassifiedFailure:
        if isinstance(error, BudgetExceededError):
            return ClassifiedFailure(FailureKind.BUDGET_EXCEEDED)
        if isinstance(error, LoopDetectedError):
            return ClassifiedFailure(FailureKind.LOOP_DETECTED)
        if isinstance(error, AuthorizationAgentError):
            return ClassifiedFailure(FailureKind.AUTHORIZATION)
        if isinstance(error, ValidationAgentError | ValueError | TypeError):
            return ClassifiedFailure(FailureKind.VALIDATION)
        if isinstance(error, RateLimitedAgentError):
            return ClassifiedFailure(FailureKind.RATE_LIMITED, error.retry_after_seconds)
        if isinstance(error, AgentTimeoutError | TimeoutError):
            return ClassifiedFailure(FailureKind.TIMEOUT)
        if isinstance(error, TransientAgentError | ConnectionError):
            return ClassifiedFailure(FailureKind.TRANSIENT)
        if isinstance(error, PermanentAgentError):
            return ClassifiedFailure(FailureKind.PERMANENT)

        status_code = getattr(error, "status_code", None)
        if status_code in {401, 403}:
            return ClassifiedFailure(FailureKind.AUTHORIZATION)
        if status_code == 429:
            retry_after = getattr(error, "retry_after_seconds", None)
            return ClassifiedFailure(FailureKind.RATE_LIMITED, retry_after)
        if isinstance(status_code, int) and 500 <= status_code <= 599:
            return ClassifiedFailure(FailureKind.TRANSIENT)
        if isinstance(status_code, int) and 400 <= status_code <= 499:
            return ClassifiedFailure(FailureKind.VALIDATION)
        return ClassifiedFailure(FailureKind.PERMANENT)
