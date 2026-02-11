"""Command-line interface for the Brain alpha agent toolkit."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional runtime dependency
    load_dotenv = None

from .brain_api.client import BrainAPISession, BrainCredentials, load_credentials, save_credentials
from .brain_api.diversity import get_diversity
from .config import AppConfig
from .exceptions import ManualActionRequired
from .agents.llm_orchestrator import LLMOrchestrator
from .generation.knowledge_pack import build_knowledge_packs
from .generation.openai_provider import OpenAILLMSettings, OpenAIProviderError
from .metadata.sync import sync_all_metadata, sync_simulation_options
from .retrieval.pack_builder import (
    RetrievalPack,
    build_retrieval_pack,
    load_retrieval_budget,
    summarize_pack_for_event,
)
from .schemas import AlphaResult, CandidateAlpha, IdeaSpec, SimulationTarget
from .simulation.runner import SimulationRunner
from .storage.sqlite_store import MetadataStore
from .validation.static_validator import StaticValidator

if load_dotenv is not None:
    # Enables .env-based credentials in local development.
    load_dotenv()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = AppConfig()
    store = MetadataStore(config.paths.db_path)

    if args.command == "prepare-credentials":
        return cmd_prepare_credentials(args)

    if args.command == "sync-options":
        session = _session_from_args(args)
        payload = sync_simulation_options(session, store, meta_dir=config.paths.meta_dir)
        print(json.dumps({"saved": True, "keys": list(payload.get("allowed", {}).keys())}, ensure_ascii=False))
        return 0

    if args.command == "sync-metadata":
        session = _session_from_args(args)
        target = _target_from_args(args)
        max_field_datasets = args.max_field_datasets
        if isinstance(max_field_datasets, int) and max_field_datasets <= 0:
            max_field_datasets = None
        wait_on_rate_limit = not bool(args.no_wait_on_rate_limit)
        summary = sync_all_metadata(
            session,
            store,
            target,
            sync_fields=not args.skip_fields,
            max_field_datasets=max_field_datasets,
            wait_on_rate_limit=wait_on_rate_limit,
        )
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    if args.command == "validate-expression":
        operators = store.list_operators()
        fields = store.list_data_fields()
        validator = StaticValidator(operators=operators, fields=fields)
        report = validator.validate(args.expression, alpha_type=args.alpha_type)
        print(report.model_dump_json(indent=2))
        return 0 if report.is_valid else 2

    if args.command == "simulate-candidates":
        session = _session_from_args(args)
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        candidates = [CandidateAlpha.model_validate(item) for item in payload]
        runner = SimulationRunner(session, store)

        if len(candidates) > 1:
            results = runner.run_candidates_multi(candidates)
        else:
            one = runner.run_candidate(candidates[0])
            results = [one] if one else []

        out = [result.model_dump(mode="python") for result in results]
        if args.output:
            Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"simulated": len(out), "output": args.output}, ensure_ascii=False))
        return 0

    if args.command == "evaluate-results":
        from .evaluation.evaluator import Evaluator

        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        results = [AlphaResult.model_validate(item) for item in payload]
        evaluator = Evaluator()
        scorecards = evaluator.evaluate(results)
        out = [x.model_dump(mode="python") for x in scorecards]
        if args.output:
            Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"evaluated": len(out), "output": args.output}, ensure_ascii=False))
        return 0

    if args.command == "diversity-snapshot":
        session = _session_from_args(args)
        payload = get_diversity(session, user_id=args.user_id, grouping=args.grouping)
        if args.output:
            Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"saved": bool(args.output), "output": args.output}, ensure_ascii=False))
        return 0

    if args.command == "build-retrieval-pack":
        payload = json.loads(Path(args.idea).read_text(encoding="utf-8"))
        idea = _load_idea_spec(payload)
        budget = load_retrieval_budget(args.budget_config)
        pack = build_retrieval_pack(
            idea=idea,
            store=store,
            budget=budget,
            meta_dir=args.meta_dir,
            query_override=args.query,
        )
        _save_retrieval_pack(args.output, pack)
        event_payload = summarize_pack_for_event(pack)
        if args.output:
            event_payload["output"] = args.output
        event_payload.update(
            {
                "run_id": f"retrieval-{pack.idea_id}",
                "stage": "retrieval",
                "message": "Top-K retrieval pack built",
                "severity": "info",
            }
        )
        store.append_event("retrieval.pack_built", event_payload)
        print(
            json.dumps(
                {
                    "built": True,
                    "idea_id": pack.idea_id,
                    "output": args.output,
                    "candidate_counts": pack.telemetry.candidate_counts,
                    "token_estimate": pack.token_estimate.model_dump(mode="python"),
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "build-knowledge-pack":
        result = build_knowledge_packs(
            store=store,
            output_dir=args.output_dir,
            meta_dir=args.meta_dir,
        )
        payload = {
            "success": result.success,
            "output_dir": result.output_dir,
            "generated_files": result.generated_files,
            "failed_parts": result.failed_parts,
            "counts": result.counts,
            "fallback_used": result.fallback_used,
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0 if result.success else 2

    if args.command == "run-idea-agent":
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Idea agent input must be a JSON object")

        raw_output = Path(args.raw_output).read_text(encoding="utf-8") if args.raw_output else None
        llm_settings = OpenAILLMSettings(
            model=args.llm_model,
            reasoning_effort=args.reasoning_effort,
            verbosity=args.verbosity,
            reasoning_summary=args.reasoning_summary,
            max_output_tokens=args.max_output_tokens,
        )
        try:
            orchestrator = LLMOrchestrator(
                store=store,
                meta_dir=args.meta_dir,
                max_idea_regenerations=args.max_regenerations,
                llm_provider=args.llm_provider,
                llm_settings=llm_settings,
            )
            idea, run_id = orchestrator.run_idea_agent(
                input_payload=payload,
                run_id=args.run_id,
                raw_output=raw_output,
            )
        except OpenAIProviderError as exc:
            print(json.dumps({"error": "openai_provider_error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 2
        if args.output:
            Path(args.output).write_text(idea.model_dump_json(indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "ok": True,
                    "run_id": run_id,
                    "idea_id": idea.idea_id,
                    "output": args.output,
                    "llm_provider": args.llm_provider,
                    "llm_model": args.llm_model,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "run-alpha-maker":
        idea = _load_idea_spec(json.loads(Path(args.idea).read_text(encoding="utf-8")))
        retrieval_pack = RetrievalPack.model_validate(
            json.loads(Path(args.retrieval_pack).read_text(encoding="utf-8"))
        )
        raw_output = Path(args.raw_output).read_text(encoding="utf-8") if args.raw_output else None

        llm_settings = OpenAILLMSettings(
            model=args.llm_model,
            reasoning_effort=args.reasoning_effort,
            verbosity=args.verbosity,
            reasoning_summary=args.reasoning_summary,
            max_output_tokens=args.max_output_tokens,
        )
        try:
            orchestrator = LLMOrchestrator(
                store=store,
                meta_dir=args.meta_dir,
                max_alpha_regenerations=args.max_regenerations,
                llm_provider=args.llm_provider,
                llm_settings=llm_settings,
            )
            candidate, run_id = orchestrator.run_alpha_maker(
                idea=idea,
                retrieval_pack=retrieval_pack,
                knowledge_pack_dir=args.knowledge_pack_dir,
                run_id=args.run_id,
                raw_output=raw_output,
            )
        except OpenAIProviderError as exc:
            print(json.dumps({"error": "openai_provider_error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 2
        if args.output:
            Path(args.output).write_text(candidate.model_dump_json(indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "ok": True,
                    "run_id": run_id,
                    "idea_id": idea.idea_id,
                    "output": args.output,
                    "used_fields": candidate.generation_notes.used_fields,
                    "used_operators": candidate.generation_notes.used_operators,
                    "llm_provider": args.llm_provider,
                    "llm_model": args.llm_model,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "serve-live-events":
        try:
            import uvicorn
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "error": "missing_dependency",
                        "message": f"uvicorn import failed: {exc}",
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 2

        try:
            from .runtime.event_bus import EventBus
            from .server.app import create_app
        except ModuleNotFoundError as exc:
            print(
                json.dumps(
                    {
                        "error": "missing_dependency",
                        "message": f"server import failed: {exc}",
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 2

        app = create_app(
            store=store,
            event_bus=EventBus(store=store),
            poll_interval_sec=args.poll_interval_sec,
        )
        uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)
        return 0

    parser.print_help()
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Brain alpha agent CLI")
    sub = parser.add_subparsers(dest="command")

    p_creds = sub.add_parser("prepare-credentials", help="Create ~/.brain_credentials")
    p_creds.add_argument("--email")
    p_creds.add_argument("--password")
    p_creds.add_argument("--path", default=None)

    p_options = sub.add_parser("sync-options", help="Sync OPTIONS /simulations")
    p_options.add_argument("--credentials", default=None)
    p_options.add_argument("--interactive-login", action="store_true")

    p_meta = sub.add_parser("sync-metadata", help="Sync operators/datasets/data-fields")
    p_meta.add_argument("--credentials", default=None)
    p_meta.add_argument("--interactive-login", action="store_true")
    p_meta.add_argument("--instrument-type", default="EQUITY")
    p_meta.add_argument("--region", default="USA")
    p_meta.add_argument("--universe", default="TOP3000")
    p_meta.add_argument("--delay", type=int, default=1)
    p_meta.add_argument("--skip-fields", action="store_true")
    p_meta.add_argument(
        "--max-field-datasets",
        type=int,
        default=0,
        help="Limit number of datasets used for /data-fields sync (<=0 means no limit).",
    )
    p_meta.add_argument(
        "--no-wait-on-rate-limit",
        action="store_true",
        help="Fail fast on 429 instead of waiting and continuing.",
    )

    p_val = sub.add_parser("validate-expression", help="Run static validation")
    p_val.add_argument("expression")
    p_val.add_argument("--alpha-type", default="REGULAR")

    p_sim = sub.add_parser("simulate-candidates", help="Run simulations from candidate JSON list")
    p_sim.add_argument("--credentials", default=None)
    p_sim.add_argument("--interactive-login", action="store_true")
    p_sim.add_argument("--input", required=True)
    p_sim.add_argument("--output", default="data/simulation_results/latest.json")

    p_eval = sub.add_parser("evaluate-results", help="Evaluate AlphaResult JSON list")
    p_eval.add_argument("--input", required=True)
    p_eval.add_argument("--output", default="data/evaluation/latest_scorecards.json")

    p_div = sub.add_parser("diversity-snapshot", help="Fetch diversity endpoint payload")
    p_div.add_argument("--credentials", default=None)
    p_div.add_argument("--interactive-login", action="store_true")
    p_div.add_argument("--user-id", default="self")
    p_div.add_argument("--grouping", default="region,delay,dataCategory")
    p_div.add_argument("--output", default="data/diversity/latest.json")

    p_rpack = sub.add_parser("build-retrieval-pack", help="Build Top-K retrieval pack from IdeaSpec JSON")
    p_rpack.add_argument("--idea", required=True, help="Path to IdeaSpec JSON")
    p_rpack.add_argument("--query", default=None, help="Optional query override for retrieval")
    p_rpack.add_argument(
        "--meta-dir",
        default=str(configure_default_meta_dir()),
        help="Metadata root directory containing index artifacts.",
    )
    p_rpack.add_argument(
        "--budget-config",
        default="configs/retrieval_budget.json",
        help="Path to retrieval budget JSON (uses defaults if missing).",
    )
    p_rpack.add_argument("--output", default="data/retrieval/latest_pack.json")

    p_kpack = sub.add_parser("build-knowledge-pack", help="Build FastExpr knowledge packs (step-18)")
    p_kpack.add_argument("--output-dir", default="data/meta/index")
    p_kpack.add_argument("--meta-dir", default=str(configure_default_meta_dir()))

    p_idea = sub.add_parser("run-idea-agent", help="Run Idea Researcher contract parser/repair flow (step-19)")
    p_idea.add_argument("--input", required=True, help="Path to idea input JSON")
    p_idea.add_argument("--raw-output", default=None, help="Optional raw LLM output text file for parse/repair tests")
    p_idea.add_argument("--run-id", default=None, help="Optional run id override")
    p_idea.add_argument("--max-regenerations", type=int, default=2)
    p_idea.add_argument("--meta-dir", default=str(configure_default_meta_dir()))
    p_idea.add_argument(
        "--llm-provider",
        choices=["openai", "mock", "auto"],
        default=str(os.getenv("BRAIN_LLM_PROVIDER") or "openai"),
    )
    p_idea.add_argument("--llm-model", default=str(os.getenv("BRAIN_LLM_MODEL") or "gpt-5.2"))
    p_idea.add_argument("--reasoning-effort", choices=["minimal", "low", "medium", "high"], default=str(os.getenv("BRAIN_LLM_REASONING_EFFORT") or "medium"))
    p_idea.add_argument("--verbosity", choices=["low", "medium", "high"], default=str(os.getenv("BRAIN_LLM_VERBOSITY") or "medium"))
    p_idea.add_argument("--reasoning-summary", choices=["auto", "concise", "detailed"], default=str(os.getenv("BRAIN_LLM_REASONING_SUMMARY") or "auto"))
    p_idea.add_argument("--max-output-tokens", type=int, default=_env_int("BRAIN_LLM_MAX_OUTPUT_TOKENS", 2200))
    p_idea.add_argument("--output", default="/tmp/idea_out.json")

    p_alpha = sub.add_parser("run-alpha-maker", help="Run Alpha Maker contract parser/repair flow (step-19)")
    p_alpha.add_argument("--idea", required=True, help="Path to IdeaSpec JSON")
    p_alpha.add_argument("--retrieval-pack", required=True, help="Path to retrieval pack JSON")
    p_alpha.add_argument("--knowledge-pack-dir", default="data/meta/index")
    p_alpha.add_argument("--raw-output", default=None, help="Optional raw LLM output text file for parse/repair tests")
    p_alpha.add_argument("--run-id", default=None, help="Optional run id override")
    p_alpha.add_argument("--max-regenerations", type=int, default=2)
    p_alpha.add_argument("--meta-dir", default=str(configure_default_meta_dir()))
    p_alpha.add_argument(
        "--llm-provider",
        choices=["openai", "mock", "auto"],
        default=str(os.getenv("BRAIN_LLM_PROVIDER") or "openai"),
    )
    p_alpha.add_argument("--llm-model", default=str(os.getenv("BRAIN_LLM_MODEL") or "gpt-5.2"))
    p_alpha.add_argument("--reasoning-effort", choices=["minimal", "low", "medium", "high"], default=str(os.getenv("BRAIN_LLM_REASONING_EFFORT") or "medium"))
    p_alpha.add_argument("--verbosity", choices=["low", "medium", "high"], default=str(os.getenv("BRAIN_LLM_VERBOSITY") or "medium"))
    p_alpha.add_argument("--reasoning-summary", choices=["auto", "concise", "detailed"], default=str(os.getenv("BRAIN_LLM_REASONING_SUMMARY") or "auto"))
    p_alpha.add_argument("--max-output-tokens", type=int, default=_env_int("BRAIN_LLM_MAX_OUTPUT_TOKENS", 2200))
    p_alpha.add_argument("--output", default="/tmp/candidate_alpha.json")

    p_live = sub.add_parser("serve-live-events", help="Serve FastAPI live event bridge (step-19)")
    p_live.add_argument("--host", default="127.0.0.1")
    p_live.add_argument("--port", type=int, default=8765)
    p_live.add_argument("--poll-interval-sec", type=float, default=0.5)
    p_live.add_argument("--log-level", default="info")

    return parser


def cmd_prepare_credentials(args: argparse.Namespace) -> int:
    email = args.email or input("Email: ")
    password = args.password or getpass.getpass("Password: ")

    path = save_credentials(
        BrainCredentials(email=email, password=password),
        path=args.path if args.path else Path("~/.brain_credentials").expanduser(),
    )
    print(json.dumps({"saved": str(path)}, ensure_ascii=False))
    return 0


def _target_from_args(args: argparse.Namespace) -> SimulationTarget:
    return SimulationTarget(
        instrumentType=args.instrument_type,
        region=args.region,
        universe=args.universe,
        delay=args.delay,
    )


def _session_from_args(args: argparse.Namespace) -> BrainAPISession:
    creds = load_credentials(args.credentials) if args.credentials else load_credentials()
    interactive = bool(getattr(args, "interactive_login", False))
    return BrainAPISession(creds, interactive_login_default=interactive)


def _load_idea_spec(payload: Any) -> IdeaSpec:
    if isinstance(payload, dict):
        return _validate_idea_payload(payload)
    if isinstance(payload, list) and payload:
        return _validate_idea_payload(payload[0])
    raise ValueError("Idea input must be a JSON object or non-empty JSON array")


def _validate_idea_payload(payload: dict[str, Any]) -> IdeaSpec:
    return IdeaSpec.model_validate(payload)


def _save_retrieval_pack(path: str | None, pack: RetrievalPack) -> None:
    if not path:
        return
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(pack.model_dump_json(indent=2), encoding="utf-8")


def configure_default_meta_dir() -> Path:
    return AppConfig().paths.meta_dir


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except Exception:
        return default


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ManualActionRequired as exc:
        payload = {
            "error": "manual_action_required",
            "message": str(exc),
            "action_url": exc.action_url,
            "hint": "Run the command with --interactive-login to complete biometrics in-terminal.",
        }
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(3)
