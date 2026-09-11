from __future__ import annotations

import argparse
import json
import time

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
        command.add_argument("--start")
        command.add_argument("--end")
        command.add_argument("--symbol", action="append", dest="symbols")
        command.add_argument("--resume", action="store_true")
        command.add_argument("--limit", type=int, default=0)
        command.add_argument("--retries", type=int, default=1)
    gaps = commands.add_parser("gaps")
    gaps.add_argument("--dataset", default="valuation_daily", choices=("valuation_daily",))
    repair = commands.add_parser("repair")
    repair.add_argument("--dataset", required=True, choices=("valuation_daily", "sw_industry_history", "security_lifecycle"))
    repair.add_argument('--symbol', action='append', dest='symbols')
    commands.add_parser("publish")
    commands.add_parser("security-master")
    update_all = commands.add_parser("update-all")
    update_all.add_argument('--wait', action='store_true', help='Keep the timer service alive until its update finishes')
    run_update = commands.add_parser('run-update')
    run_update.add_argument('--job-id', required=True)
    run_update.add_argument('--mode', required=True)
    run_update.add_argument('--start')
    run_update.add_argument('--end')
    resolve = commands.add_parser("resolve-false-positive-circuit")
    resolve.add_argument("--symbol", required=True)
    probe = commands.add_parser("health-probe")
    probe.add_argument("--symbol", action="append", dest="symbols", required=True)
    low_beta_collect = commands.add_parser("collect-low-beta-status")
    low_beta_collect.add_argument("--start", required=True)
    low_beta_collect.add_argument("--end", required=True)
    low_beta_collect.add_argument("--release")
    low_beta_collect.add_argument("--limit", type=int, default=0)
    commands.add_parser("publish-low-beta-status")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    service = DataHubService()
    try:
        if args.command == 'run-update':
            from .daily import DailyUpdate
            result = DailyUpdate(service).run(args.job_id, args.mode, args.start, args.end)
        elif args.command in ('update-all', 'sync', 'update'):
            from .daily import DailyUpdate
            if getattr(args, 'dataset', 'valuation_daily') != 'valuation_daily':
                raise ValueError('该数据集没有已验收的增量入口；update-all 会明确报告来源受阻')
            if getattr(args, 'retries', 1) != 1 or getattr(args, 'limit', 0) or getattr(args, 'symbols', None) or getattr(args, 'start', None) or getattr(args, 'resume', False):
                raise ValueError('sync/update 不支持 retries/limit/symbol/start/resume；指定历史范围请使用 backfill')
            result = DailyUpdate(service).start('sync' if args.command == 'sync' else 'update-all', end=getattr(args, 'end', None))
            if getattr(args, 'wait', False) and result['status'] != 'ALREADY_RUNNING':
                job_id = result['job_id']
                while result['status'] == 'RUNNING':
                    time.sleep(1)
                    result = DailyUpdate(service).status()
                    if result.get('job_id') != job_id:
                        raise RuntimeError('update reservation changed while waiting')
                if result['status'] in ('FAILED', 'INTERRUPTED'):
                    raise RuntimeError(result.get('error', result['status']))
        elif args.command == "status":
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
            if args.retries != 1:
                raise ValueError('retries is unsupported; Governor owns bounded retries')
            if args.resume and (args.start or args.end):
                raise ValueError('resume 恢复未完成任务；指定日期范围请去掉 --resume')
            if args.resume and not args.end:
                symbols = args.symbols or service.valuation_universe()
                result = service.mvp_backfill(dataset=args.dataset, symbols=symbols, resume=True, limit=args.limit)
            else:
                if args.limit or args.symbols:
                    raise ValueError('ranged backfill does not support limit/symbol')
                from .daily import DailyUpdate
                result = DailyUpdate(service).start('backfill', args.start, args.end)
        elif args.command == "gaps":
            result = service.mvp_gaps(dataset=args.dataset)
        elif args.command == "repair":
            result = service.mvp_repair(dataset=args.dataset, symbols=args.symbols)
        elif args.command == "publish":
            result = service.mvp_publish()
        elif args.command == "security-master":
            result = service.refresh_security_master()
        elif args.command == "resolve-false-positive-circuit":
            result = service.resolve_false_positive_circuit(symbol=args.symbol)
        elif args.command == "health-probe":
            result = service.mvp_health_probe(symbols=args.symbols)
        elif args.command == "collect-low-beta-status":
            result = service.collect_low_beta_status(args.start, args.end, release_id=args.release, limit=args.limit)
        elif args.command == "publish-low-beta-status":
            result = service.publish_low_beta_status()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
