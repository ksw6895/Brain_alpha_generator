"""OpenAI Responses API provider for structured JSON agent outputs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Literal


ReasoningEffort = Literal["minimal", "low", "medium", "high"]
VerbosityLevel = Literal["low", "medium", "high"]
ReasoningSummary = Literal["auto", "concise", "detailed"]


class OpenAIProviderError(RuntimeError):
    """Raised when OpenAI provider setup or API calls fail."""


@dataclass
class OpenAILLMSettings:
    model: str = "gpt-5.2"
    reasoning_effort: ReasoningEffort = "medium"
    verbosity: VerbosityLevel = "medium"
    reasoning_summary: ReasoningSummary = "auto"
    max_output_tokens: int = 2200
    timeout_sec: float = 90.0

    @classmethod
    def from_env(cls) -> "OpenAILLMSettings":
        model = str(os.getenv("BRAIN_LLM_MODEL") or "gpt-5.2").strip() or "gpt-5.2"

        effort_raw = str(os.getenv("BRAIN_LLM_REASONING_EFFORT") or "medium").strip().lower()
        effort = effort_raw if effort_raw in {"minimal", "low", "medium", "high"} else "medium"

        verbosity_raw = str(os.getenv("BRAIN_LLM_VERBOSITY") or "medium").strip().lower()
        verbosity = verbosity_raw if verbosity_raw in {"low", "medium", "high"} else "medium"

        summary_raw = str(os.getenv("BRAIN_LLM_REASONING_SUMMARY") or "auto").strip().lower()
        summary = summary_raw if summary_raw in {"auto", "concise", "detailed"} else "auto"

        max_output_tokens_raw = os.getenv("BRAIN_LLM_MAX_OUTPUT_TOKENS")
        try:
            max_output_tokens = max(256, int(max_output_tokens_raw)) if max_output_tokens_raw else 2200
        except Exception:
            max_output_tokens = 2200

        timeout_raw = os.getenv("BRAIN_LLM_TIMEOUT_SEC")
        try:
            timeout_sec = max(5.0, float(timeout_raw)) if timeout_raw else 90.0
        except Exception:
            timeout_sec = 90.0

        return cls(
            model=model,
            reasoning_effort=effort,  # type: ignore[arg-type]
            verbosity=verbosity,  # type: ignore[arg-type]
            reasoning_summary=summary,  # type: ignore[arg-type]
            max_output_tokens=max_output_tokens,
            timeout_sec=timeout_sec,
        )


@dataclass
class LLMCallResult:
    text: str
    usage: dict[str, Any] = field(default_factory=dict)
    provider: str = "openai"
    model: str = ""
    response_id: str | None = None
    refusal: str | None = None


class OpenAIResponsesJSONClient:
    """Structured JSON generation via OpenAI Responses API."""

    def __init__(
        self,
        *,
        settings: OpenAILLMSettings | None = None,
        api_key: str | None = None,
    ) -> None:
        self.settings = settings or OpenAILLMSettings.from_env()

        key = str(api_key or os.getenv("OPENAI_API_KEY") or "").strip()
        if not key:
            raise OpenAIProviderError("OPENAI_API_KEY is not set")

        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
            raise OpenAIProviderError("openai SDK is not installed. Run pip install -r requirements.txt") from exc

        self.client = OpenAI(api_key=key, timeout=self.settings.timeout_sec)

    def generate_idea_spec(self, prompt: str) -> LLMCallResult:
        return self._generate_structured_json(
            prompt=prompt,
            schema_name="idea_spec",
            schema=IDEA_SPEC_JSON_SCHEMA,
            stage_hint="idea_research",
        )

    def generate_candidate_alpha(self, prompt: str) -> LLMCallResult:
        return self._generate_structured_json(
            prompt=prompt,
            schema_name="candidate_alpha",
            schema=CANDIDATE_ALPHA_JSON_SCHEMA,
            stage_hint="alpha_maker",
        )

    def _generate_structured_json(
        self,
        *,
        prompt: str,
        schema_name: str,
        schema: dict[str, Any],
        stage_hint: str,
    ) -> LLMCallResult:
        text_cfg: dict[str, Any] = {
            "verbosity": self.settings.verbosity,
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": schema,
            },
        }

        request: dict[str, Any] = {
            "model": self.settings.model,
            "input": [
                {
                    "role": "developer",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Return only a JSON object that matches the schema exactly. "
                                f"Stage={stage_hint}. No markdown, no prose."
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                },
            ],
            "text": text_cfg,
            "max_output_tokens": self.settings.max_output_tokens,
            "reasoning": {
                "effort": self.settings.reasoning_effort,
                "summary": self.settings.reasoning_summary,
            },
        }

        try:
            response = self.client.responses.create(**request)
        except Exception as exc:  # pragma: no cover - network/runtime failure
            raise OpenAIProviderError(f"OpenAI responses.create failed: {exc}") from exc

        response_dict = _to_dict(response)
        refusal = _extract_refusal(response_dict)
        output_text = _extract_output_text(response, response_dict)
        usage = _extract_usage(response, response_dict)

        if not output_text:
            if refusal:
                raise OpenAIProviderError(f"Model refused request: {refusal}")
            raise OpenAIProviderError("OpenAI response did not contain output_text")

        return LLMCallResult(
            text=output_text,
            usage=usage,
            provider="openai",
            model=self.settings.model,
            response_id=str(response_dict.get("id") or "") or None,
            refusal=refusal,
        )


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump(mode="python")
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            return {}
    return {}


def _extract_output_text(response: Any, response_dict: dict[str, Any]) -> str:
    text = getattr(response, "output_text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    output = response_dict.get("output")
    if not isinstance(output, list):
        return ""

    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for chunk in content:
            if not isinstance(chunk, dict):
                continue
            if chunk.get("type") != "output_text":
                continue
            text_value = chunk.get("text")
            if isinstance(text_value, str) and text_value.strip():
                parts.append(text_value)

    return "\n".join(parts).strip()


def _extract_refusal(response_dict: dict[str, Any]) -> str | None:
    direct = response_dict.get("refusal")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    output = response_dict.get("output")
    if not isinstance(output, list):
        return None

    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for chunk in content:
            if not isinstance(chunk, dict):
                continue
            if chunk.get("type") != "refusal":
                continue
            ref = chunk.get("refusal")
            if isinstance(ref, str) and ref.strip():
                return ref.strip()
    return None


def _extract_usage(response: Any, response_dict: dict[str, Any]) -> dict[str, Any]:
    usage = response_dict.get("usage")
    if isinstance(usage, dict):
        return usage

    obj = getattr(response, "usage", None)
    if hasattr(obj, "model_dump"):
        try:
            usage_dump = obj.model_dump(mode="python")
            if isinstance(usage_dump, dict):
                return usage_dump
        except Exception:
            return {}

    if isinstance(obj, dict):
        return obj
    return {}


IDEA_TARGET_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "instrumentType": {"type": "string"},
        "region": {"type": "string"},
        "universe": {"type": "string"},
        "delay": {"type": "integer"},
    },
    "required": ["instrumentType", "region", "universe", "delay"],
}

IDEA_SPEC_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "idea_id": {"type": "string"},
        "hypothesis": {"type": "string"},
        "theme_tags": {"type": "array", "items": {"type": "string"}},
        "target": IDEA_TARGET_SCHEMA,
        "candidate_datasets": {"type": "array", "items": {"type": "string"}},
        "keywords_for_retrieval": {"type": "array", "items": {"type": "string"}},
        "candidate_subcategories": {"type": "array", "items": {"type": "string"}},
        "retrieval_context_id": {"type": ["string", "null"]},
        "exploration_intent": {"type": ["string", "null"]},
    },
    "required": [
        "idea_id",
        "hypothesis",
        "theme_tags",
        "target",
        "candidate_datasets",
        "keywords_for_retrieval",
        "candidate_subcategories",
        "retrieval_context_id",
        "exploration_intent",
    ],
}

SIMULATION_SETTINGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "instrumentType": {"type": "string"},
        "region": {"type": "string"},
        "universe": {"type": "string"},
        "delay": {"type": "integer"},
        "decay": {"type": "integer"},
        "neutralization": {"type": "string"},
        "truncation": {"type": "number"},
        "maxTrade": {"type": "string", "enum": ["ON", "OFF"]},
        "pasteurization": {"type": "string", "enum": ["ON", "OFF"]},
        "testPeriod": {"type": "string"},
        "unitHandling": {"type": "string"},
        "nanHandling": {"type": "string", "enum": ["ON", "OFF"]},
        "language": {"type": "string", "enum": ["FASTEXPR"]},
        "visualization": {"type": "boolean"},
    },
    "required": [
        "instrumentType",
        "region",
        "universe",
        "delay",
        "decay",
        "neutralization",
        "truncation",
        "maxTrade",
        "pasteurization",
        "testPeriod",
        "unitHandling",
        "nanHandling",
        "language",
        "visualization",
    ],
}

CANDIDATE_ALPHA_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "idea_id": {"type": "string"},
        "alpha_id": {"type": ["string", "null"]},
        "simulation_settings": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "type": {"type": "string", "enum": ["REGULAR"]},
                "settings": SIMULATION_SETTINGS_SCHEMA,
                "regular": {"type": "string"},
                "selection": {"type": ["string", "null"]},
                "combo": {"type": ["string", "null"]},
            },
            "required": ["type", "settings", "regular", "selection", "combo"],
        },
        "generation_notes": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "used_fields": {"type": "array", "items": {"type": "string"}},
                "used_operators": {"type": "array", "items": {"type": "string"}},
                "candidate_lane": {"type": ["string", "null"]},
            },
            "required": ["used_fields", "used_operators", "candidate_lane"],
        },
    },
    "required": ["idea_id", "alpha_id", "simulation_settings", "generation_notes"],
}
