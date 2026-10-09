"""Launch only the BulletTrade data service, outside the QMT installation."""
from __future__ import annotations
import argparse, os, secrets, subprocess, sys
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]

def prepare_config(source: Path, runtime: Path, port: int) -> Path:
    values = dotenv_values(source)
    password = values.get("BIG_QMT_GATEWAY_PASSWORD")
    if not password:
        raise ValueError("BIG_QMT_GATEWAY_PASSWORD missing from existing source config")
    runtime.mkdir(parents=True, exist_ok=True)
    path = runtime / "data-service.env"
    token_path = runtime / "data-service.token"
    if not token_path.exists():
        token_path.write_text(secrets.token_urlsafe(40), encoding="utf-8")
    token = token_path.read_text(encoding="utf-8").strip()
    if not token:
        raise ValueError("Empty data-service token")
    settings = {
        "QMT_SERVER_TYPE": "big_qmt", "QMT_SERVER_HOST": "127.0.0.1",
        "QMT_SERVER_LISTEN": "127.0.0.1", "QMT_SERVER_PORT": str(port),
        "QMT_SERVER_TOKEN": token, "QMT_SERVER_ENABLE_DATA": "true",
        "QMT_SERVER_ENABLE_BROKER": "false", "DEFAULT_DATA_PROVIDER": "qmt-remote",
        "BIG_QMT_GATEWAY_URL": values.get("BIG_QMT_GATEWAY_URL") or "http://127.0.0.1:9000",
        "BIG_QMT_GATEWAY_PASSWORD": password,
    }
    # dotenv escaping keeps arbitrary credential characters out of shell commands.
    import json
    path.write_text("\n".join(k+"="+json.dumps(v) for k,v in settings.items())+"\n", encoding="utf-8")
    return path

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-config",type=Path,default=Path("D:/Projects/BulletTrade/.env.bigqmt"))
    parser.add_argument("--runtime",type=Path,default=ROOT/"var"/"quantradar2")
    parser.add_argument("--port",type=int,default=58621)
    parser.add_argument("--prepare-only",action="store_true")
    args=parser.parse_args()
    config=prepare_config(args.source_config,args.runtime,args.port)
    if args.prepare_only:
        print("Prepared data-only configuration (credentials withheld)");return 0
    env=dict(os.environ)
    for key in list(env):
        if key.startswith(("QMT_","BIG_QMT_","JQDATA_")):
            env.pop(key,None)
    env["PYTHONUTF8"]="1"
    return subprocess.call([sys.executable,"-m","bullet_trade","--env-file",str(config),
        "server","--server-type","big_qmt","--listen","127.0.0.1","--port",str(args.port),
        "--enable-data","--disable-broker"],cwd=args.runtime,env=env)

if __name__=="__main__":
    raise SystemExit(main())
