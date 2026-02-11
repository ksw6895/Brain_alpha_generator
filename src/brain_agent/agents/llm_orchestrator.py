"""Step-19 LLM orchestration for Idea Researcher and Alpha Maker."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from ..constants import DEFAULT_META_DIR
from ..generation.openai_provider import (
    LLMCallResult,
    OpenAILLMSettings,
    OpenAIProviderError,
    OpenAIResponsesJSONClient,
)
from ..generation.prompting import (
    ParseFailure,
    build_alpha_maker_prompt,
    build_idea_researcher_prompt,
    parse_candidate_alpha,
    parse_idea_spec,
    repair_json_text,
)
from ..retrieval.pack_builder import (
    RetrievalPack,
    build_retrieval_pack,
    load_retrieval_budget,
    summarize_pack_for_event,
)
from ..runtime.event_bus import EventBus
from ..schemas import CandidateAlpha, IdeaSpec
from ..storage.sqlite_store import MetadataStore

IdeaGenerator = Callable[[str], str | LLMCallResult | dict[str, Any]]
AlphaGenerator = Callable[[str], str | LLMCallResult | dict[str, Any]]
ProviderMode = Literal["openai", "mock", "auto"]


@dataclass
class OrchestrationResult:
    run_id: str
    idea: IdeaSpec
    retrieval_pack: RetrievalPack
    candidate_alpha: CandidateAlpha


class LLMOrchestrator:
    """Contract-first 2-agent orchestration with parse repair and event emission."""

    def __init__(
        self,
        *,
        store: MetadataStore,
        event_bus: EventBus | None = None,
        idea_generator: IdeaGenerator | None = None,
        alpha_generator: AlphaGenerator | None = None,
        meta_dir: str | Path = DEFAULT_META_DIR,
        retrieval_budget_config: str | Path = "configs/retrieval_budget.json",
        max_idea_regenerations: int = 2,
        max_alpha_regenerations: int = 2,
        llm_provider: ProviderMode = "auto",
        llm_settings: OpenAILLMSettings | None = None,
        openai_client: OpenAIResponsesJSONClient | None = None,
    ) -> None:
        self.store = store
        self.event_bus = event_bus or EventBus(store=store)
        self.idea_generator = idea_generator
        self.alpha_generator = alpha_generator
        self.meta_dir = Path(meta_dir)
        self.retrieval_budget = load_retrieval_budget(retrieval_budget_config)
        self.max_idea_regenerations = max(0, int(max_idea_regenerations))
        self.max_alpha_regenerations = max(0, int(max_alpha_regenerations))

        provider_mode = str(llm_provider or "auto").strip().lower()
        if provider_mode not in {"openai", "mock", "auto"}:
            raise ValueError(f"Unsupported llm_provider: {llm_provider}")
        self.llm_provider: ProviderMode = provider_mode  # type: ignore[assignment]
        self.llm_settings = llm_settings or OpenAILLMSettings.from_env()

        self.openai_client: OpenAIResponsesJSONClient | None = openai_client

    def run_idea_agent(
        self,
        *,
        input_payload: dict[str, Any],
        run_id: str | None = None,
        raw_output: str | None = None,
    ) -> tuple[IdeaSpec, str]:
        active_run_id = run_id or _new_run_id()
        fallback_idea_id = str(input_payload.get("idea_id") or f"idea-{uuid.uuid4().hex[:8]}")

        self.event_bus.publish(
            event_type="agent.idea_started",
            run_id=active_run_id,
            idea_id=fallback_idea_id,
            stage="idea_research",
            message="Idea Researcher stage started",
            severity="info",
            payload={"input_keys": sorted(input_payload.keys())},
        )

        prompt = ""
        raw_candidate = raw_output
        generation: LLMCallResult | None = None

        if raw_candidate is None:
            prompt = build_idea_researcher_prompt(
                category=_text_or_none(input_payload.get("category")),
                subcategory=_text_or_none(input_payload.get("subcategory")),
                target=input_payload.get("target"),
                overview=_text_or_none(input_payload.get("overview") or input_payload.get("hypothesis")),
                recent_performance_summary=_text_or_none(input_payload.get("recent_performance_summary")),
            )
            generation = self._generate_idea(prompt, input_payload)
            raw_candidate = generation.text

        idea = self._parse_idea_with_repair(
            raw_candidate,
            run_id=active_run_id,
            idea_id=fallback_idea_id,
            prompt=prompt,
            input_payload=input_payload,
        )

        self.event_bus.publish(
            event_type="agent.idea_generated",
            run_id=active_run_id,
            idea_id=idea.idea_id,
            stage="idea_research",
            message="IdeaSpec contract validated",
            severity="info",
            payload={
                "candidate_subcategories": idea.candidate_subcategories,
                "keywords_for_retrieval": idea.keywords_for_retrieval,
            },
        )

        self._emit_usage_point(
            run_id=active_run_id,
            idea_id=idea.idea_id,
            stage="idea_research",
            prompt=prompt,
            completion=raw_candidate,
            llm_call=generation,
        )
        return idea, active_run_id

    def build_retrieval_for_idea(
        self,
        *,
        idea: IdeaSpec,
        run_id: str,
        query_override: str | None = None,
    ) -> RetrievalPack:
        pack = build_retrieval_pack(
            idea=idea,
            store=self.store,
            budget=self.retrieval_budget,
            meta_dir=self.meta_dir,
            query_override=query_override,
        )

        payload = summarize_pack_for_event(pack)
        self.event_bus.publish(
            event_type="retrieval.pack_built",
            run_id=run_id,
            idea_id=idea.idea_id,
            stage="retrieval",
            message="Top-K retrieval pack built",
            severity="info",
            payload=payload,
        )
        return pack

    def run_alpha_maker(
        self,
        *,
        idea: IdeaSpec,
        retrieval_pack: RetrievalPack,
        knowledge_pack_dir: str | Path,
        run_id: str | None = None,
        raw_output: str | None = None,
    ) -> tuple[CandidateAlpha, str]:
        active_run_id = run_id or _new_run_id()

        self.event_bus.publish(
            event_type="agent.alpha_started",
            run_id=active_run_id,
            idea_id=idea.idea_id,
            stage="alpha_maker",
            message="Alpha Maker stage started",
            severity="info",
            payload={
                "retrieval_candidates": retrieval_pack.telemetry.candidate_counts,
            },
        )

        knowledge_bundle = _load_knowledge_bundle(Path(knowledge_pack_dir))

        prompt = ""
        raw_candidate = raw_output
        generation: LLMCallResult | None = None
        if raw_candidate is None:
            prompt = build_alpha_maker_prompt(
                idea,
                retrieval_pack,
                knowledge_pack=knowledge_bundle,
            )
            generation = self._generate_alpha(prompt, idea, retrieval_pack, knowledge_bundle)
            raw_candidate = generation.text

        candidate = self._parse_alpha_with_repair(
            raw_candidate,
            run_id=active_run_id,
            idea_id=idea.idea_id,
            prompt=prompt,
            idea=idea,
            retrieval_pack=retrieval_pack,
            knowledge_bundle=knowledge_bundle,
        )
        candidate = _align_generation_notes(candidate)

        self.event_bus.publish(
            event_type="agent.alpha_generated",
            run_id=active_run_id,
            idea_id=idea.idea_id,
            stage="alpha_maker",
            message="CandidateAlpha contract validated",
            severity="info",
            payload={
                "used_fields": candidate.generation_notes.used_fields,
                "used_operators": candidate.generation_notes.used_operators,
                "candidate_lane": candidate.generation_notes.candidate_lane,
            },
        )

        self._emit_usage_point(
            run_id=active_run_id,
            idea_id=idea.idea_id,
            stage="alpha_maker",
            prompt=prompt,
            completion=raw_candidate,
            llm_call=generation,
        )
        return candidate, active_run_id

    def run_full_cycle(
        self,
        *,
        input_payload: dict[str, Any],
        knowledge_pack_dir: str | Path,
        run_id: str | None = None,
        query_override: str | None = None,
        idea_raw_output: str | None = None,
        alpha_raw_output: str | None = None,
    ) -> OrchestrationResult:
        idea, active_run_id = self.run_idea_agent(
            input_payload=input_payload,
            run_id=run_id,
            raw_output=idea_raw_output,
        )
        retrieval_pack = self.build_retrieval_for_idea(
            idea=idea,
            run_id=active_run_id,
            query_override=query_override,
        )
        candidate, _ = self.run_alpha_maker(
            idea=idea,
            retrieval_pack=retrieval_pack,
            knowledge_pack_dir=knowledge_pack_dir,
            run_id=active_run_id,
            raw_output=alpha_raw_output,
        )
        return OrchestrationResult(
            run_id=active_run_id,
            idea=idea,
            retrieval_pack=retrieval_pack,
            candidate_alpha=candidate,
        )

    def _parse_idea_with_repair(
        self,
        raw_output: str,
        *,
        run_id: str,
        idea_id: str,
        prompt: str,
        input_payload: dict[str, Any],
    ) -> IdeaSpec:
        candidate = str(raw_output or "")
        attempt = 0

        while True:
            try:
                return parse_idea_spec(candidate)
            except ParseFailure as exc:
                self.event_bus.publish(
                    event_type="agent.idea_parse_failed",
                    run_id=run_id,
                    idea_id=idea_id,
                    stage="idea_research",
                    message=f"Idea parse failed: {exc.code}",
                    severity="error",
                    payload={"code": exc.code, "detail": exc.detail, "attempt": attempt},
                )

                try:
                    repaired = repair_json_text(candidate)
                    self.event_bus.publish(
                        event_type="agent.idea_repair_attempted",
                        run_id=run_id,
                        idea_id=idea_id,
                        stage="idea_research",
                        message="Idea parse repair attempted",
                        severity="warn",
                        payload={"attempt": attempt},
                    )
                    return parse_idea_spec(repaired)
                except ParseFailure as repair_exc:
                    if not prompt or attempt >= self.max_idea_regenerations:
                        raise repair_exc
                    if not self._can_generate_idea():
                        raise repair_exc
                    attempt += 1
                    candidate = self._generate_idea(prompt, input_payload).text

    def _parse_alpha_with_repair(
        self,
        raw_output: str,
        *,
        run_id: str,
        idea_id: str,
        prompt: str,
        idea: IdeaSpec,
        retrieval_pack: RetrievalPack,
        knowledge_bundle: dict[str, Any],
    ) -> CandidateAlpha:
        candidate = str(raw_output or "")
        attempt = 0

        while True:
            try:
                return parse_candidate_alpha(candidate)
            except ParseFailure as exc:
                self.event_bus.publish(
                    event_type="agent.alpha_parse_failed",
                    run_id=run_id,
                    idea_id=idea_id,
                    stage="alpha_maker",
                    message=f"Alpha parse failed: {exc.code}",
                    severity="error",
                    payload={"code": exc.code, "detail": exc.detail, "attempt": attempt},
                )

                try:
                    repaired = repair_json_text(candidate)
                    self.event_bus.publish(
                        event_type="agent.alpha_repair_attempted",
                        run_id=run_id,
                        idea_id=idea_id,
                        stage="alpha_maker",
                        message="Alpha parse repair attempted",
                        severity="warn",
                        payload={"attempt": attempt},
                    )
                    return parse_candidate_alpha(repaired)
                except ParseFailure as repair_exc:
                    if not prompt or attempt >= self.max_alpha_regenerations:
                        raise repair_exc
                    if not self._can_generate_alpha():
                        raise repair_exc
                    attempt += 1
                    candidate = self._generate_alpha(prompt, idea, retrieval_pack, knowledge_bundle).text

    def _generate_idea(self, prompt: str, input_payload: dict[str, Any] | None = None) -> LLMCallResult:
        if self.idea_generator is not None:
            return _coerce_generation_result(self.idea_generator(prompt), provider="custom")

        client = self._get_openai_client(required=self.llm_provider == "openai")
        if client is not None:
            return client.generate_idea_spec(prompt)

        payload = dict(input_payload or {})
        synthesized = {
            "idea_id": str(payload.get("idea_id") or f"idea-{uuid.uuid4().hex[:8]}"),
            "hypothesis": _text_or_none(payload.get("hypothesis") or payload.get("overview"))
            or "quality-aware mean reversion around earnings surprises",
            "theme_tags": _to_str_list(payload.get("theme_tags"), fallback=["quality", "mean-reversion"]),
            "target": payload.get("target") or {},
            "candidate_datasets": _to_str_list(payload.get("candidate_datasets")),
            "keywords_for_retrieval": _to_str_list(
                payload.get("keywords_for_retrieval"),
                fallback=["earnings", "surprise", "reversion"],
            ),
            "candidate_subcategories": _to_str_list(payload.get("candidate_subcategories")),
            "retrieval_context_id": _text_or_none(payload.get("retrieval_context_id")),
            "exploration_intent": _text_or_none(payload.get("exploration_intent")),
        }
        return LLMCallResult(
            text=json.dumps(synthesized, ensure_ascii=False),
            provider="mock",
            model=self.llm_settings.model,
        )

    def _generate_alpha(
        self,
        prompt: str,
        idea: IdeaSpec,
        retrieval_pack: RetrievalPack,
        knowledge_bundle: dict[str, Any],
    ) -> LLMCallResult:
        if self.alpha_generator is not None:
            return _coerce_generation_result(self.alpha_generator(prompt), provider="custom")

        client = self._get_openai_client(required=self.llm_provider == "openai")
        if client is not None:
            return client.generate_candidate_alpha(prompt)

        expression, lane = _default_expression(idea, retrieval_pack, knowledge_bundle)
        used_fields, used_operators = _infer_expression_usage(expression)
        payload = {
            "idea_id": idea.idea_id,
            "alpha_id": None,
            "simulation_settings": {
                "type": "REGULAR",
                "settings": {
                    "instrumentType": idea.target.instrumentType,
                    "region": idea.target.region,
                    "universe": idea.target.universe,
                    "delay": idea.target.delay,
                    "language": "FASTEXPR",
                },
                "regular": expression,
            },
            "generation_notes": {
                "used_fields": used_fields,
                "used_operators": used_operators,
                "candidate_lane": lane,
            },
        }
        return LLMCallResult(
            text=json.dumps(payload, ensure_ascii=False),
            provider="mock",
            model=self.llm_settings.model,
        )

    def _emit_usage_point(
        self,
        *,
        run_id: str,
        idea_id: str,
        stage: str,
        prompt: str,
        completion: str,
        llm_call: LLMCallResult | None,
    ) -> None:
        prompt_chars = len(prompt or "")
        completion_chars = len(completion or "")
        payload: dict[str, Any] = {
            "prompt_chars": prompt_chars,
            "completion_chars": completion_chars,
            "prompt_tokens_rough": _rough_token_estimate(prompt_chars),
            "completion_tokens_rough": _rough_token_estimate(completion_chars),
        }

        if llm_call is not None:
            payload.update(
                {
                    "provider": llm_call.provider,
                    "model": llm_call.model,
                    "response_id": llm_call.response_id,
                    "usage": llm_call.usage,
                    "reasoning": {
                        "effort": self.llm_settings.reasoning_effort,
                        "summary": self.llm_settings.reasoning_summary,
                        "verbosity": self.llm_settings.verbosity,
                    },
                }
            )

        self.event_bus.publish(
            event_type="llm.usage_point",
            run_id=run_id,
            idea_id=idea_id,
            stage=stage,
            message="Token/cost log point inserted for step-20 budget layer",
            severity="info",
            payload=payload,
        )

    def _can_generate_idea(self) -> bool:
        if self.idea_generator is not None:
            return True
        return self.llm_provider in {"openai", "auto"}

    def _can_generate_alpha(self) -> bool:
        if self.alpha_generator is not None:
            return True
        return self.llm_provider in {"openai", "auto"}

    def _get_openai_client(self, *, required: bool) -> OpenAIResponsesJSONClient | None:
        if self.openai_client is not None:
            return self.openai_client
        if self.llm_provider == "mock":
            return None

        try:
            self.openai_client = OpenAIResponsesJSONClient(settings=self.llm_settings)
        except OpenAIProviderError:
            if required:
                raise
            return None
        return self.openai_client


def _coerce_generation_result(value: str | LLMCallResult | dict[str, Any], *, provider: str) -> LLMCallResult:
    if isinstance(value, LLMCallResult):
        if not value.provider:
            value.provider = provider
        return value

    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            usage = value.get("usage") if isinstance(value.get("usage"), dict) else {}
            model = str(value.get("model") or "")
            response_id = str(value.get("response_id") or "") or None
            return LLMCallResult(
                text=text,
                usage=usage,
                provider=str(value.get("provider") or provider),
                model=model,
                response_id=response_id,
            )
        return LLMCallResult(text=json.dumps(value, ensure_ascii=False), provider=provider)

    return LLMCallResult(text=str(value), provider=provider)


def _load_knowledge_bundle(directory: Path) -> dict[str, Any]:
    required = {
        "operator_signature_pack": directory / "operator_signature_pack.json",
        "simulation_settings_allowed_pack": directory / "simulation_settings_allowed_pack.json",
        "fastexpr_examples_pack": directory / "fastexpr_examples_pack.json",
        "fastexpr_visual_pack": directory / "fastexpr_visual_pack.json",
    }

    bundle: dict[str, Any] = {}
    missing: list[str] = []
    for key, path in required.items():
        if not path.exists():
            missing.append(str(path))
            continue
        bundle[key] = json.loads(path.read_text(encoding="utf-8"))

    if missing:
        raise RuntimeError("Missing required knowledge pack files: " + ", ".join(missing))
    return bundle


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _to_str_list(value: Any, *, fallback: list[str] | None = None) -> list[str]:
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            text = _text_or_none(item)
            if text and text not in out:
                out.append(text)
        if out:
            return out
    return list(fallback or [])


def _default_expression(
    idea: IdeaSpec,
    retrieval_pack: RetrievalPack,
    knowledge_bundle: dict[str, Any],
) -> tuple[str, str]:
    _ = idea
    field_ids = [x.id for x in retrieval_pack.candidate_fields if x.id]
    operator_names = {x.name for x in retrieval_pack.candidate_operators if x.name}

    lane = "exploit" if retrieval_pack.lanes.get("exploit") else "explore"
    base_field = field_ids[0] if field_ids else "close"

    if "rank" in operator_names:
        return f"rank({base_field})", lane
    if "zscore" in operator_names:
        return f"zscore({base_field})", lane
    if base_field:
        return base_field, lane

    examples_pack = knowledge_bundle.get("fastexpr_examples_pack", {})
    examples = examples_pack.get("examples") if isinstance(examples_pack, dict) else []
    if isinstance(examples, list):
        for row in examples:
            if not isinstance(row, dict):
                continue
            expr = _text_or_none(row.get("expression"))
            if expr:
                return expr, lane

    return "ts_step(1)", lane


def _align_generation_notes(candidate: CandidateAlpha) -> CandidateAlpha:
    expression = candidate.simulation_settings.regular or ""
    used_fields, used_operators = _infer_expression_usage(expression)

    candidate.generation_notes.used_fields = used_fields
    candidate.generation_notes.used_operators = used_operators
    if not candidate.generation_notes.candidate_lane:
        candidate.generation_notes.candidate_lane = "exploit"
    return candidate


def _infer_expression_usage(expression: str) -> tuple[list[str], list[str]]:
    op_matches = re_findall_operator_calls(expression)
    operators = _unique(op_matches)

    all_identifiers = re_findall_identifiers(expression)
    blacklist = set(operators) | {
        "if",
        "else",
        "and",
        "or",
        "not",
        "true",
        "false",
        "null",
    }
    fields = _unique([tok for tok in all_identifiers if tok not in blacklist])
    return fields, operators


def re_findall_operator_calls(expression: str) -> list[str]:
    return [match.group(1) for match in _OPERATOR_CALL_RE.finditer(expression or "")]


def re_findall_identifiers(expression: str) -> list[str]:
    return _IDENT_RE.findall(expression or "")


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _rough_token_estimate(char_count: int) -> int:
    return max(0, int(char_count / 4))


def _new_run_id() -> str:
    return f"run-{uuid.uuid4().hex[:12]}"


_OPERATOR_CALL_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
