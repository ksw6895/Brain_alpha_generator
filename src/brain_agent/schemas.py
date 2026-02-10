"""Pydantic schemas for pipeline payloads."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class SimulationTarget(BaseModel):
    instrumentType: str = "EQUITY"
    region: str = "USA"
    universe: str = "TOP3000"
    delay: int = 1


class IdeaSpec(BaseModel):
    idea_id: str
    hypothesis: str
    theme_tags: list[str] = Field(default_factory=list)
    target: SimulationTarget = Field(default_factory=SimulationTarget)
    candidate_datasets: list[str] = Field(default_factory=list)
    keywords_for_retrieval: list[str] = Field(default_factory=list)


class SimulationSettings(BaseModel):
    instrumentType: str = "EQUITY"
    region: str = "USA"
    universe: str = "TOP3000"
    delay: int = 1
    decay: int = 15
    neutralization: str = "SUBINDUSTRY"
    truncation: float = 0.08
    maxTrade: Literal["ON", "OFF"] = "ON"
    pasteurization: Literal["ON", "OFF"] = "ON"
    testPeriod: str = "P1Y6M"
    unitHandling: str = "VERIFY"
    nanHandling: Literal["ON", "OFF"] = "OFF"
    language: str = "FASTEXPR"
    visualization: bool = False


class CandidateSimulation(BaseModel):
    type: Literal["REGULAR", "SUPER"] = "REGULAR"
    settings: SimulationSettings = Field(default_factory=SimulationSettings)
    regular: str | None = None
    selection: str | None = None
    combo: str | None = None

    @field_validator("regular")
    @classmethod
    def regular_required_for_regular(cls, value: str | None, info: Any) -> str | None:
        if info.data.get("type", "REGULAR") == "REGULAR" and not value:
            raise ValueError("regular expression is required when type=REGULAR")
        return value


class GenerationNotes(BaseModel):
    used_fields: list[str] = Field(default_factory=list)
    used_operators: list[str] = Field(default_factory=list)


class CandidateAlpha(BaseModel):
    idea_id: str
    alpha_id: str | None = None
    simulation_settings: CandidateSimulation
    generation_notes: GenerationNotes = Field(default_factory=GenerationNotes)


class SummaryMetrics(BaseModel):
    sharpe: float | None = None
    fitness: float | None = None
    turnover: float | None = None
    drawdown: float | None = None
    coverage: float | None = None


class AlphaResult(BaseModel):
    idea_id: str
    alpha_id: str
    settings_fingerprint: str
    expression_fingerprint: str
    summary_metrics: SummaryMetrics
    recordsets_saved: list[str] = Field(default_factory=list)
    created_at: str
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class ScoreCard(BaseModel):
    alpha_id: str
    passed: bool
    score: float
    reasons: list[str] = Field(default_factory=list)
    metrics: SummaryMetrics


class ValidationReport(BaseModel):
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    used_operators: list[str] = Field(default_factory=list)
    used_fields: list[str] = Field(default_factory=list)


class FailureReason(BaseModel):
    label: str
    rationale: str
    actions: list[str] = Field(default_factory=list)
