"""Command-line interface for the Brain alpha agent toolkit."""

from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
from typing import Any

from .brain_api.client import BrainAPISession, BrainCredentials, load_credentials, save_credentials
from .brain_api.diversity import get_diversity
from .config import AppConfig
from .metadata.sync import sync_all_metadata, sync_simulation_options
from .schemas import AlphaResult, CandidateAlpha, SimulationTarget
from .simulation.runner import SimulationRunner
from .storage.sqlite_store import MetadataStore
from .validation.static_validator import StaticValidator


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
        summary = sync_all_metadata(session, store, target, sync_fields=not args.skip_fields)
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

    p_meta = sub.add_parser("sync-metadata", help="Sync operators/datasets/data-fields")
    p_meta.add_argument("--credentials", default=None)
    p_meta.add_argument("--instrument-type", default="EQUITY")
    p_meta.add_argument("--region", default="USA")
    p_meta.add_argument("--universe", default="TOP3000")
    p_meta.add_argument("--delay", type=int, default=1)
    p_meta.add_argument("--skip-fields", action="store_true")

    p_val = sub.add_parser("validate-expression", help="Run static validation")
    p_val.add_argument("expression")
    p_val.add_argument("--alpha-type", default="REGULAR")

    p_sim = sub.add_parser("simulate-candidates", help="Run simulations from candidate JSON list")
    p_sim.add_argument("--credentials", default=None)
    p_sim.add_argument("--input", required=True)
    p_sim.add_argument("--output", default="data/simulation_results/latest.json")

    p_eval = sub.add_parser("evaluate-results", help="Evaluate AlphaResult JSON list")
    p_eval.add_argument("--input", required=True)
    p_eval.add_argument("--output", default="data/evaluation/latest_scorecards.json")

    p_div = sub.add_parser("diversity-snapshot", help="Fetch diversity endpoint payload")
    p_div.add_argument("--credentials", default=None)
    p_div.add_argument("--user-id", default="self")
    p_div.add_argument("--grouping", default="region,delay,dataCategory")
    p_div.add_argument("--output", default="data/diversity/latest.json")

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
    return BrainAPISession(creds)


if __name__ == "__main__":
    raise SystemExit(main())
