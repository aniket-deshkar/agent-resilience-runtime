from dataclasses import dataclass

import pytest

from agent_resilience_runtime import (
    AgentTimeoutError,
    AuthorizationAgentError,
    ErrorClassifier,
    FailureKind,
    ModelRetryPolicy,
    RateLimitedAgentError,
    RetryExecutor,
    RetryPolicy,
    TransientAgentError,
    ValidationAgentError,
)


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (TransientAgentError("temporary"), FailureKind.TRANSIENT),
        (RateLimitedAgentError("slow"), FailureKind.RATE_LIMITED),
        (AgentTimeoutError("late"), FailureKind.TIMEOUT),
        (AuthorizationAgentError("denied"), FailureKind.AUTHORIZATION),
        (ValidationAgentError("invalid"), FailureKind.VALIDATION),
        (RuntimeError("unknown"), FailureKind.PERMANENT),
    ],
)
def test_classifier_is_conservative(error, kind) -> None:
    assert ErrorClassifier().classify(error).kind == kind


def test_http_status_classification() -> None:
    class HttpError(RuntimeError):
        status_code = 503

    assert ErrorClassifier().classify(HttpError()).kind == FailureKind.TRANSIENT


def test_exponential_backoff_with_deterministic_jitter() -> None:
    policy = RetryPolicy(4, 1, 10, multiplier=2, jitter_ratio=0.25)
    assert policy.delay(1, 0) == pytest.approx(0.75)
    assert policy.delay(2, 0.5) == pytest.approx(2)
    assert policy.delay(4, 1) == pytest.approx(10)


def test_retry_succeeds_after_transient_failures() -> None:
    attempts = 0
    sleeps = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TransientAgentError("temporary")
        return "ok"

    result = RetryExecutor(sleep=sleeps.append, random_value=lambda: 0.5).execute(
        "model", operation, ModelRetryPolicy(jitter_ratio=0)
    )
    assert result == "ok"
    assert attempts == 3
    assert sleeps == [0.25, 0.5]


def test_retry_after_is_respected() -> None:
    attempts = 0
    sleeps = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RateLimitedAgentError("slow", retry_after_seconds=3)
        return "ok"

    RetryExecutor(sleep=sleeps.append, random_value=lambda: 0.5).execute(
        "model", operation, ModelRetryPolicy(jitter_ratio=0)
    )
    assert sleeps == [3]


@pytest.mark.parametrize(
    "error",
    [AuthorizationAgentError("denied"), ValidationAgentError("invalid"), RuntimeError("unknown")],
)
def test_terminal_failures_are_never_retried(error) -> None:
    attempts = 0

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise error

    with pytest.raises(type(error)):
        RetryExecutor(sleep=lambda _: None).execute("tool", operation, ModelRetryPolicy())
    assert attempts == 1


def test_retry_exhaustion_emits_telemetry() -> None:
    @dataclass
    class Telemetry:
        exhausted: tuple | None = None

        def on_attempt(self, operation, attempt):
            return None

        def on_retry(self, operation, attempt, failure, delay_seconds):
            return None

        def on_exhausted(self, operation, attempts, failure):
            self.exhausted = (operation, attempts, failure.kind)

    telemetry = Telemetry()
    with pytest.raises(TransientAgentError):
        RetryExecutor(sleep=lambda _: None, telemetry=telemetry).execute(
            "model", lambda: (_ for _ in ()).throw(TransientAgentError("down")), ModelRetryPolicy()
        )
    assert telemetry.exhausted == ("model", 3, FailureKind.TRANSIENT)


def test_invalid_retry_configuration_fails_fast() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        RetryPolicy(0, 1, 2)
