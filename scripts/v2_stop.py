"""Stop only the recorded V2 API. Data service and QMT remain separate."""
import json
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parents[1]
if __name__=="__main__":
    info=json.loads((ROOT/"var/quantradar2/api-process.json").read_text())
    try:process=psutil.Process(info["pid"])
    except psutil.NoSuchProcess:raise SystemExit("V2 API is already stopped")
    if abs(process.create_time()-info["process_created"])>0.001:raise SystemExit("PID identity mismatch; no process stopped")
    if not any(Path(arg).name=="v2_api.py" for arg in process.cmdline()):raise SystemExit("Command identity mismatch; no process stopped")
    process.terminate();process.wait(5)
    print("V2 API stopped. Interrupted tasks will be reconciled at next startup.")
