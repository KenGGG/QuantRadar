"""QuantRadar 因子研究（phase 9）：复用 BulletTrade 的 IC / RankIC / 分层 / 多空。"""

from .factors import (
    build_factor_panel,
    run_factor_research,
    run_momentum_research,
)

__all__ = [
    "build_factor_panel",
    "run_factor_research",
    "run_momentum_research",
]
