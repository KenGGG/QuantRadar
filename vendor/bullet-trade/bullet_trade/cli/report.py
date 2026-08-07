"""
回测报告命令

提供 `bullet-trade report` 子命令实现。
"""

from typing import List, Optional

from bullet_trade.reporting import ReportGenerationError, generate_cli_report


def _parse_metrics(metrics: Optional[str]) -> Optional[List[str]]:
    if not metrics:
        return None
    parts = [item.strip() for item in metrics.split(",")]
    filtered = [item for item in parts if item]
    return filtered or None


def run_report(args):
    """
    生成回测报告。
    """
    metrics_keys = _parse_metrics(getattr(args, "metrics", None))
    try:
        output_path = generate_cli_report(
            input_dir=args.input,
            output_path=args.output,
            fmt=args.format,
            template_path=args.template,
            metrics_keys=metrics_keys,
            title=args.title,
        )
        print(f"✓ 报告已生成: {output_path}")
        return 0
    except ReportGenerationError as exc:
        print(f"❌ 报告生成失败: {exc}")
        return 1
    except FileNotFoundError as exc:
        print(f"❌ 文件缺失: {exc}")
        return 1
    except Exception as exc:  # pragma: no cover - 防御性兜底
        print(f"❌ 未预期的错误: {exc}")
        import traceback

        traceback.print_exc()
        return 1
