"""FastExpr generation helpers."""

from .knowledge_pack import build_knowledge_packs
from .openai_provider import (
    LLMCallResult,
    OpenAILLMSettings,
    OpenAIProviderError,
    OpenAIResponsesJSONClient,
)
from .prompting import (
    ParseFailure,
    build_alpha_maker_prompt,
    build_fastexpr_prompt,
    build_gated_fastexpr_prompt,
    build_idea_researcher_prompt,
    parse_candidate_alpha,
    parse_idea_spec,
    parse_with_format_repair,
    repair_json_text,
)

__all__ = [
    "LLMCallResult",
    "OpenAILLMSettings",
    "OpenAIProviderError",
    "OpenAIResponsesJSONClient",
    "ParseFailure",
    "build_alpha_maker_prompt",
    "build_fastexpr_prompt",
    "build_gated_fastexpr_prompt",
    "build_idea_researcher_prompt",
    "parse_candidate_alpha",
    "parse_idea_spec",
    "parse_with_format_repair",
    "repair_json_text",
    "build_knowledge_packs",
]
