"""Explicit local runtime paths and audited engine identity."""
from __future__ import annotations
import hashlib, os, sys
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

@dataclass(frozen=True)
class Runtime:
    root: Path
    data_config: Path
    timeout_seconds: float = 1800

    @classmethod
    def from_env(cls):
        root=Path(os.environ.get("QUANTRADAR2_RUNTIME",str(ROOT/"var/quantradar2"))).resolve()
        return cls(root,Path(os.environ.get("QUANTRADAR2_DATA_CONFIG",str(root/"data-service.env"))).resolve(),float(os.environ.get("QUANTRADAR2_TIMEOUT","1800")))

    def run_dir(self,run_id):
        if len(run_id)!=32 or any(c not in "0123456789abcdef" for c in run_id):raise ValueError("Invalid run id")
        return self.root/"runs"/run_id

def engine_identity():
    import bullet_trade
    package=Path(bullet_trade.__file__).resolve().parent
    expected=Path(os.environ.get("QUANTRADAR2_BULLETTRADE_SOURCE","D:/Projects/BulletTrade")).resolve()
    if package!=expected/"bullet_trade":raise RuntimeError("Unexpected BulletTrade load path: "+str(package))
    source_hash=hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        source_hash.update(str(path.relative_to(package)).encode());source_hash.update(path.read_bytes())
    adapter_hash=hashlib.sha256()
    for name in ["runtime.py","runner.py","provider.py","frozen.py"]:
        path=Path(__file__).parent/name
        adapter_hash.update(name.encode());adapter_hash.update(path.read_bytes())
    configs_hash=hashlib.sha256()
    for path in sorted((package/"config").glob("*.json")):
        configs_hash.update(path.name.encode());configs_hash.update(path.read_bytes())
    return {"adapter_fingerprint":adapter_hash.hexdigest(),"native_config_fingerprint":configs_hash.hexdigest(),"source_fingerprint":source_hash.hexdigest(),"dependency_versions":{name:version(name) for name in ["pandas","numpy","bullet-trade"]},"python":sys.executable,"python_version":sys.version,"bullettrade_version":version("bullet-trade"),
        "bullettrade_source":str(package),"engine_sha256":hashlib.sha256((package/"core/engine.py").read_bytes()).hexdigest()}
