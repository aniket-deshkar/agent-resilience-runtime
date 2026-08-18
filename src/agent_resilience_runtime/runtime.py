"""Small composition layer for agent-aware guards and retry policies."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any, TypeVar

from .budget import BudgetSnapshot, ExecutionBudget
from .loop import RepeatedToolDetector
from .retry import ModelRetryPolicy, RetryExecutor, ToolRetryPolicy

ResultT = TypeVar("ResultT")


class AgentResilienceRuntime:
    def __init__(
        self,
        budget: ExecutionBudget,
        *,
        retry_executor: RetryExecutor | None = None,
        model_policy: ModelRetryPolicy | None = None,
        tool_policy: ToolRetryPolicy | None = None,
        loop_detector: RepeatedToolDetector | None = None,
    ) -> None:
        self.budget = budget
        self.retry_executor = retry_executor or RetryExecutor()
        self.model_policy = model_policy or ModelRetryPolicy()
        self.tool_policy = tool_policy or ToolRetryPolicy()
        self.loop_detector = loop_detector or RepeatedToolDetector()

    def model_call(self, operation: Callable[[], ResultT]) -> ResultT:
        self.budget.before_step()
        return self.retry_executor.execute("model", operation, self.model_policy)

    def tool_call(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        operation: Callable[[], ResultT],
    ) -> ResultT:
        self.loop_detector.record(tool_name, arguments)
        self.budget.before_step()
        return self.retry_executor.execute(f"tool:{tool_name}", operation, self.tool_policy)

    def record_usage(
        self,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost: Decimal | None = None,
    ) -> BudgetSnapshot:
        return self.budget.record_usage(
            input_tokens=input_tokens, output_tokens=output_tokens, cost=cost
        )
