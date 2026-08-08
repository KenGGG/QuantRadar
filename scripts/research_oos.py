"""QuantRadar 样本外（OOS）稳健性验证端到端脚本。

链路：investment_data(Dolt) → build_qlib_data（或复用已有 qlib_data）
      → run_research_oos（grid 选优 + walk-forward 多折 OOS）→ 可复现报告(JSON+MD)

用法：
  # 复用已构建的 qlib_data 目录
  python scripts/research_oos.py --qlib-data-dir /path/to/qlib_data \
      --start 2020-01-01 --end 2022-12-31 --out reports/oos

  # 自动构建（需可达 investment_data）
  python scripts/research_oos.py --build --start 2020-01-01 --end 2022-12-31 \
      --max-instruments 50 --out reports/oos

报告：<out>.json（结构化，可复现）+ <out>.md（可读摘要）。任一步失败即非零退出。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

# 让脚本以仓库根目录为工作基准（可直接 `python scripts/research_oos.py` 运行）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from quantradar.qml import build_qlib_data, render_oos_markdown, run_research_oos  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="QuantRadar 样本外稳健性验证")
    parser.add_argument("--qlib-data-dir", default=None,
                        help="已构建的 qlib_data 目录；与 --build 互斥")
    parser.add_argument("--build", action="store_true",
                        help="从 investment_data 自动构建 qlib_data（需可达 Dolt）")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2022-12-31")
    parser.add_argument("--max-instruments", type=int, default=50)
    parser.add_argument("--model", default="lgb")
    parser.add_argument("--topk", type=int, default=50)
    parser.add_argument("--train-years", type=int, default=2)
    parser.add_argument("--valid-months", type=int, default=6)
    parser.add_argument("--test-months", type=int, default=6)
    parser.add_argument("--step-months", type=int, default=6)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--num-boost-round", type=int, default=50)
    parser.add_argument("--early-stopping-rounds", type=int, default=10)
    parser.add_argument("--no-grid", action="store_true", help="跳过 in-sample 网格寻优")
    parser.add_argument("--out", default="reports/oos", help="报告输出前缀（.json/.md）")
    args = parser.parse_args(argv)

    if args.build and args.qlib_data_dir:
        print("ERROR: --build 与 --qlib-data-dir 互斥", file=sys.stderr)
        return 2
    if not args.build and not args.qlib_data_dir:
        print("ERROR: 需提供 --qlib-data-dir 或 --build", file=sys.stderr)
        return 2

    qlib_data_dir = args.qlib_data_dir
    if args.build:
        qlib_data_dir = tempfile.mkdtemp(prefix="qr_oos_qlib_")
        print(f"[research_oos] 构建 qlib_data -> {qlib_data_dir}")
        build_qlib_data(
            qlib_data_dir, start=args.start, end=args.end,
            max_instruments=args.max_instruments,
        )

    print(f"[research_oos] 运行样本外验证 dir={qlib_data_dir} "
          f"window={args.start}~{args.end} seed={args.seed}")
    report = run_research_oos(
        qlib_data_dir, args.start, args.end,
        model=args.model, topk=args.topk,
        train_years=args.train_years, valid_months=args.valid_months,
        test_months=args.test_months, step_months=args.step_months,
        seed=args.seed, num_boost_round=args.num_boost_round,
        early_stopping_rounds=args.early_stopping_rounds,
        do_grid=not args.no_grid,
    )

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    json_path = args.out + ".json"
    md_path = args.out + ".md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_oos_markdown(report))

    o = report["oos"]
    print(f"[research_oos] 完成：折数={o['n_folds']} 平均OOS_IC={o['mean_ic']:.4f} "
          f"正IC折占比={o['positive_ic_ratio']:.2%}")
    print(f"[research_oos] 报告: {json_path} / {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
