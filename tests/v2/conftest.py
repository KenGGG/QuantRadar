"""Keep native dependency test logs inside the current runtime directory."""
import os
from pathlib import Path
os.environ.setdefault("LOG_DIR",str(Path(__file__).resolve().parents[2]/"var/quantradar2/logs"))
