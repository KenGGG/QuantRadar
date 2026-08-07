"""
因子研究核心接口
"""

from .pipeline import (
    FactorPipelineConfig,
    FilterConfig,
    FactorPipelineResult,
    run_factor_pipeline,
)
from .evaluation import (
    CostConfig,
    BacktestConfig,
    EvaluationResult,
    evaluate_factor_performance,
)
from .io import save_results, load_results

__all__ = [
    "FactorPipelineConfig",
    "FilterConfig",
    "FactorPipelineResult",
    "run_factor_pipeline",
    "CostConfig",
    "BacktestConfig",
    "EvaluationResult",
    "evaluate_factor_performance",
    "save_results",
    "load_results",
]
