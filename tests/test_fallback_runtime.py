from decimal import Decimal

import pytest

from agent_resilience_runtime import (
    AgentResilienceRuntime,
    AuthorizationAgentError,
    BudgetLimits,
    ExecutionBudget,
    FallbackExhaustedError,
    FallbackModel,
    LoopDetectedError,
    ModelProvider,
    ModelRetryPolicy,
    RepeatedToolDetector,
    RetryExecutor,
    ToolRetryPolicy,
    TransientAgentError,
)


def test_model_falls_back_after_transient_failure() -> None:
    calls = []

    def primary(request):
        calls.append("primary")
        raise TransientAgentError("down")

    def secondary(request):
        calls.append("secondary")
        return {"text": "ok"}

    model = FallbackModel(
        [ModelProvider("primary", primary), ModelProvider("secondary", secondary)]
    )
    assert model.invoke({"prompt": "hello"}) == {"text": "ok"}
    assert calls == ["primary", "secondary"]


def test_authorization_failure_never_falls_back() -> None:
    secondary_called = False

    def secondary(request):
        nonlocal secondary_called
        secondary_called = True
        return {}

    model = FallbackModel(
        [
            ModelProvider(
                "primary", lambda request: (_ for _ in ()).throw(AuthorizationAgentError("denied"))
            ),
            ModelProvider("secondary", secondary),
        ]
    )
    with pytest.raises(AuthorizationAgentError):
        model.invoke({})
    assert secondary_called is False


def test_all_transient_providers_exhaust() -> None:
    model = FallbackModel(
        [
            ModelProvider("one", lambda request: (_ for _ in ()).throw(TransientAgentError("1"))),
            ModelProvider("two", lambda request: (_ for _ in ()).throw(TransientAgentError("2"))),
        ]
    )
    with pytest.raises(FallbackExhaustedError) as captured:
        model.invoke({})
    assert isinstance(captured.value.__cause__, TransientAgentError)


def test_runtime_applies_distinct_model_and_tool_policies() -> None:
    attempts = {"model": 0, "tool": 0}
    runtime = AgentResilienceRuntime(
        ExecutionBudget(BudgetLimits(5)),
        retry_executor=RetryExecutor(sleep=lambda _: None, random_value=lambda: 0.5),
        model_policy=ModelRetryPolicy(max_attempts=3, jitter_ratio=0),
        tool_policy=ToolRetryPolicy(max_attempts=2, jitter_ratio=0),
    )

    def model_operation():
        attempts["model"] += 1
        if attempts["model"] < 3:
            raise TransientAgentError("model")
        return "model-ok"

    def tool_operation():
        attempts["tool"] += 1
        if attempts["tool"] < 2:
            raise TransientAgentError("tool")
        return "tool-ok"

    assert runtime.model_call(model_operation) == "model-ok"
    assert runtime.tool_call("lookup", {"id": 1}, tool_operation) == "tool-ok"
    assert attempts == {"model": 3, "tool": 2}
    assert runtime.budget.snapshot().steps == 2


def test_runtime_blocks_repeated_tool_before_side_effect() -> None:
    calls = 0
    runtime = AgentResilienceRuntime(
        ExecutionBudget(BudgetLimits(5)),
        loop_detector=RepeatedToolDetector(maximum_repeats=2, window_size=2),
    )

    def tool():
        nonlocal calls
        calls += 1
        return "ok"

    runtime.tool_call("delete", {"id": 1}, tool)
    with pytest.raises(LoopDetectedError):
        runtime.tool_call("delete", {"id": 1}, tool)
    assert calls == 1


def test_runtime_records_supplied_usage_only() -> None:
    runtime = AgentResilienceRuntime(
        ExecutionBudget(BudgetLimits(1, max_tokens=10, max_cost=Decimal("2")))
    )
    snapshot = runtime.record_usage(input_tokens=4, output_tokens=2, cost=Decimal("0.25"))
    assert snapshot.tokens == 6
    assert snapshot.cost == Decimal("0.25")
