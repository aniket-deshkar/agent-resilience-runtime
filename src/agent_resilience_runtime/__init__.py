"""Agent-aware failure handling and execution budgets."""

from .budget import BudgetLimits, BudgetSnapshot, ExecutionBudget, SystemClock
from .failure import (
    AgentOperationError,
    AgentTimeoutError,
    AuthorizationAgentError,
    BudgetExceededError,
    ClassifiedFailure,
    ErrorClassifier,
    FailureKind,
    LoopDetectedError,
    PermanentAgentError,
    RateLimitedAgentError,
    TransientAgentError,
    ValidationAgentError,
)
from .fallback import FallbackExhaustedError, FallbackModel, ModelProvider
from .loop import RepeatedToolDetector
from .retry import (
    ModelRetryPolicy,
    NoOpRetryTelemetry,
    RetryExecutor,
    RetryPolicy,
    ToolRetryPolicy,
)
from .runtime import AgentResilienceRuntime

__all__ = [
    "AgentOperationError",
    "AgentResilienceRuntime",
    "AgentTimeoutError",
    "AuthorizationAgentError",
    "BudgetExceededError",
    "BudgetLimits",
    "BudgetSnapshot",
    "ClassifiedFailure",
    "ErrorClassifier",
    "ExecutionBudget",
    "FailureKind",
    "FallbackExhaustedError",
    "FallbackModel",
    "LoopDetectedError",
    "ModelProvider",
    "ModelRetryPolicy",
    "NoOpRetryTelemetry",
    "PermanentAgentError",
    "RateLimitedAgentError",
    "RepeatedToolDetector",
    "RetryExecutor",
    "RetryPolicy",
    "SystemClock",
    "ToolRetryPolicy",
    "TransientAgentError",
    "ValidationAgentError",
]
