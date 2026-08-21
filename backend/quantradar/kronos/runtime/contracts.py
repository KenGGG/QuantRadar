from __future__ import annotations

from dataclasses import dataclass

KRONOS_SOURCE_COMMIT = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"
KRONOS_MODEL_ID = "NeoQuasar/Kronos-base"
KRONOS_MODEL_REVISION = "2b554741eca47781b64468546e77fef3e85130e6"
KRONOS_TOKENIZER_ID = "NeoQuasar/Kronos-Tokenizer-base"
KRONOS_TOKENIZER_REVISION = "0e0117387f39004a9016484a186a908917e22426"
MAX_CONTEXT = 512
LOOKBACK_DAYS = 90
PREDICTION_DAYS = 10
FIXED_PATH_SEEDS = (101, 211, 307, 401, 503)


@dataclass(frozen=True)
class BenchmarkStage:
    name: str
    symbol_count: int | None
    path_count: int


REQUIRED_STAGES = (
    BenchmarkStage("one_symbol_one_path", 1, 1),
    BenchmarkStage("fifty_symbols_one_path", 50, 1),
    BenchmarkStage("full_pit_one_path", None, 1),
    BenchmarkStage("full_pit_five_paths", None, len(FIXED_PATH_SEEDS)),
)
