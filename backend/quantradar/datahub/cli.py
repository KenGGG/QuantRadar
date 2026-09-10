from __future__ import annotations

import argparse
import json

from .service import DataHubService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quantradar-data")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    audit = commands.add_parser("audit")
    audit.add_argument("--release")
    sample = commands.add_parser("sample")
    sample.add_argument("--release", required=True)
    sample.add_argument("--symbol", required=True)
    sample.add_argument("--date", required=True)
    for name in ("backfill", "sync", "update"):
        command = commands.add_parser(name)
        command.add_argument("--dataset", choices=("valuation_daily", "sw_industry_history", "security_lifecycle"), default="valuation_daily")
        command.add_argument("--start", default="2018-01-02")
        command.add_argument("--end")
        command.add_argument("--symbol", action="append", dest="symbols")
        command.add_argument("--resume", action="store_true")
        command.add_argument("--limit", type=int, default=0)
        command.add_argument("--retries", type=int, default=1)
    gaps = commands.add_parser("gaps")
    gaps.add_argument("--dataset", default="valuation_daily", choices=("valuation_daily",))
    repair = commands.add_parser("repair")
    repair.add_argument("--dataset", required=True, choices=("valuation_daily", "sw_industry_history", "security_lifecycle"))
    commands.add_parser("publish")
    resolve = commands.add_parser("resolve-false-positive-circuit")
    resolve.add_argument("--symbol", required=True)
    probe = commands.add_parser("health-probe")
    probe.add_argument("--symbol", action="append", dest="symbols", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    service = DataHubService()
    try:
        if args.command == "status":
            result = service.status()
        elif args.command == "audit":
            result = service.audit(args.release)
        elif args.command == "sample":
            from .reader import ReleaseReader
            from .sample import run_research_sample
            result = run_research_sample(ReleaseReader(service.config), release_id=args.release, symbol=args.symbol, as_of=args.date)
        elif args.command in {"backfill", "sync", "update"}:
            if args.dataset != "valuation_daily":
                raise ValueError(f"MVP dispatch is not implemented for {args.dataset}")
            symbols = args.symbols or service.valuation_universe()
            result = service.mvp_backfill(dataset=args.dataset, symbols=symbols, resume=args.resume, limit=args.limit)
        elif args.command == "gaps":
            result = service.mvp_gaps(dataset=args.dataset)
        elif args.command == "repair":
            result = service.mvp_repair(dataset=args.dataset)
        elif args.command == "publish":
            result = service.mvp_publish()
        elif args.command == "resolve-false-positive-circuit":
            result = service.resolve_false_positive_circuit(symbol=args.symbol)
        elif args.command == "health-probe":
            result = service.mvp_health_probe(symbols=args.symbols)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
