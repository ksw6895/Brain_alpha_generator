"""Agent orchestration package."""

from .llm_orchestrator import LLMOrchestrator, OrchestrationResult

try:  # pragma: no cover - optional heavy dependency chain (pandas)
    from .pipeline import BrainPipeline
except ModuleNotFoundError as exc:  # pragma: no cover - keep lightweight imports usable
    if exc.name != "pandas":
        raise
    BrainPipeline = None  # type: ignore[assignment]

__all__ = ["BrainPipeline", "LLMOrchestrator", "OrchestrationResult"]
