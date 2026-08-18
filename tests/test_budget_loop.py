from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from agent_resilience_runtime import (
    BudgetExceededError,
    BudgetLimits,
    ErrorClassifier,
    ExecutionBudget,
    FailureKind,
    LoopDetectedError,
    RepeatedToolDetector,
)


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.value = now

    def now(self) -> datetime:
        return self.value


def test_step_budget_stops_at_boundary() -> None:
    budget = ExecutionBudget(BudgetLimits(max_steps=2))
    assert budget.before_step().steps == 1
    assert budget.before_step().steps == 2
    with pytest.raises(BudgetExceededError, match="step"):
        budget.before_step()


def test_deadline_is_deterministic() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    clock = FakeClock(now)
    budget = ExecutionBudget(BudgetLimits(2, deadline=now + timedelta(seconds=1)), clock=clock)
    budget.before_step()
    clock.value = now + timedelta(seconds=1)
    with pytest.raises(BudgetExceededError, match="deadline"):
        budget.before_step()


def test_token_and_cost_usage_are_atomic_on_rejection() -> None:
    budget = ExecutionBudget(BudgetLimits(3, max_tokens=10, max_cost=Decimal("1.00")))
    budget.record_usage(input_tokens=3, output_tokens=2, cost=Decimal("0.40"))
    with pytest.raises(BudgetExceededError, match="token"):
        budget.record_usage(input_tokens=6, cost=Decimal("0.10"))
    assert budget.snapshot().tokens == 5
    assert budget.snapshot().cost == Decimal("0.40")


def test_missing_usage_metadata_does_not_invent_values() -> None:
    budget = ExecutionBudget(BudgetLimits(1, max_tokens=1, max_cost=Decimal("0.01")))
    snapshot = budget.record_usage()
    assert snapshot.tokens == 0
    assert snapshot.cost == 0


def test_repeated_tool_detector_normalizes_argument_order() -> None:
    detector = RepeatedToolDetector(maximum_repeats=3, window_size=4)
    detector.record("search", {"q": "one", "page": 1})
    detector.record("other", {})
    detector.record("search", {"page": 1, "q": "one"})
    with pytest.raises(LoopDetectedError, match="search"):
        detector.record("search", {"q": "one", "page": 1})


def test_loop_reset_allows_new_sequence() -> None:
    detector = RepeatedToolDetector(maximum_repeats=2, window_size=2)
    detector.record("search", {"q": "one"})
    detector.reset()
    detector.record("search", {"q": "one"})


def test_budget_and_loop_failures_are_classified_terminally() -> None:
    classifier = ErrorClassifier()
    assert classifier.classify(BudgetExceededError("budget")).kind == FailureKind.BUDGET_EXCEEDED
    assert classifier.classify(LoopDetectedError("loop")).kind == FailureKind.LOOP_DETECTED


def test_concurrent_step_claims_never_exceed_budget() -> None:
    budget = ExecutionBudget(BudgetLimits(max_steps=10))

    def claim() -> bool:
        try:
            budget.before_step()
            return True
        except BudgetExceededError:
            return False

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(lambda _: claim(), range(20)))

    assert results.count(True) == 10
    assert budget.snapshot().steps == 10
