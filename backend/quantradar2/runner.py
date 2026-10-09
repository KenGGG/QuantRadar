"""One trusted strategy, one process, BulletTrade native backtest and reports."""
from __future__ import annotations
import argparse,dataclasses,hashlib,json,math,os,sys,traceback
from datetime import date,datetime
from pathlib import Path
from .runtime import Runtime,engine_identity


def plain(value):
    if dataclasses.is_dataclass(value):return plain(dataclasses.asdict(value))
    if isinstance(value,dict):return {str(k):plain(v) for k,v in value.items()}
    if isinstance(value,(list,tuple,set)):return [plain(v) for v in value]
    if isinstance(value,(date,datetime,Path)):return str(value)
    if isinstance(value,float) and not math.isfinite(value):return None
    if value is None or isinstance(value,(str,int,float,bool)):return value
    return {"type":type(value).__name__,"value":"unknown"}


def write_json(path,value):
    pending=path.with_suffix(path.suffix+".tmp")
    pending.write_text(json.dumps(plain(value),ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    pending.replace(path)


def execute(run_dir:Path,runtime:Runtime):
    import psutil
    write_json(run_dir/"runner-process.json",{"pid":os.getpid(),"process_created":psutil.Process().create_time()})
    environment=engine_identity()
    write_json(run_dir/"environment.json",environment)
    request=json.loads((run_dir/"request.json").read_text(encoding="utf-8"))
    source=(run_dir/"strategy.py").read_text(encoding="utf-8")
    if not source.strip():raise ValueError("Empty strategy source")
    from dotenv import dotenv_values
    values=dotenv_values(runtime.data_config)
    token=values.get("QMT_SERVER_TOKEN")
    if not token:raise ValueError("V2 data service is not configured")
    # Explicit provider config: no account id, Gateway password or live broker.
    from .provider import ResearchQmtProvider
    from bullet_trade.data.api import set_data_provider
    provider=ResearchQmtProvider({"host":"127.0.0.1","port":int(values.get("QMT_SERVER_PORT",58621)),"token":token})
    try:
        raw=provider._connection.request("admin.health",{},timeout=15)
        health=raw.get("value",raw)
        if health.get("features")!=["data"] or health.get("backend_type")!="big_qmt":
            raise RuntimeError("Backtest requires the dedicated data-only big QMT service")
        set_data_provider(provider)
        from bullet_trade.core.engine import create_backtest
        from bullet_trade.core.settings import get_settings
        from bullet_trade.core.analysis import generate_report
        from bullet_trade.reporting import generate_cli_report
        # Native 0.10.0 ignores constructor benchmark. Apply the webpage default
        # through its public setting API, only when the strategy did not set one.
        bootstrap = "exec(compile(open(" + repr(str(run_dir/"strategy.py")) + ", encoding='utf-8').read(), " + repr(str(run_dir/"strategy.py")) + ", 'exec'), globals())\n"
        bootstrap += "_user_initialize = globals().get('initialize')\ndef initialize(context):\n    if _user_initialize: _user_initialize(context)\n    from bullet_trade.core.settings import get_settings, set_benchmark\n    if get_settings().benchmark is None and " + repr(request.get("benchmark")) + ":\n        set_benchmark(" + repr(request.get("benchmark")) + ")\n"
        (run_dir/"bootstrap.py").write_text(bootstrap,encoding="utf-8")
        result=create_backtest(strategy_file=str(run_dir/"bootstrap.py"),start_date=request["start_date"],
            end_date=request["end_date"],frequency=request.get("frequency","day"),
            initial_cash=request.get("initial_cash",500000),benchmark=request.get("benchmark"),
            extras=request.get("extras",{}),log_file=str(run_dir/"backtest.log"))
        settings=get_settings()
        effective={"request":request,"benchmark":(result.get("meta") or {}).get("benchmark",settings.benchmark),
            "data_limitations":["Historical price limits unavailable: native BulletTrade estimates apply; historical ST/listing limits not qualified"],
            "settings":{key:plain(getattr(settings,key,None)) for key in
                ["options","order_cost","order_cost_overrides","slippage","slippage_map","subportfolios"]}}
        write_json(run_dir/"effective_config.json",effective)
        if result.get("daily_records") is None or result["daily_records"].empty:
            raise ValueError("Backtest returned no daily records")
        generate_report(result,output_dir=str(run_dir),gen_images=True,gen_csv=True,gen_html=True)
        generate_cli_report(input_dir=str(run_dir),output_path=str(run_dir/"standard_report.html"),fmt="html",title=request.get("strategy_name","Strategy"))
        for name in ["metrics.json","daily_records.csv","report.html","standard_report.html"]:
            if not (run_dir/name).is_file():raise RuntimeError("Native report artifact missing: "+name)
        artifacts=[]
        for path in sorted(run_dir.iterdir()):
            if path.is_file() and path.name not in {"completion.json","stdout.log"} and not path.name.endswith(".tmp"):
                artifacts.append({"name":path.name,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size})
        write_json(run_dir/"completion.json",{"status":"SUCCEEDED","artifacts":artifacts})
        return 0
    finally:provider._connection.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--run-dir",type=Path,required=True)
    args=parser.parse_args();run_dir=args.run_dir.resolve();run_dir.mkdir(parents=True,exist_ok=True)
    try:return execute(run_dir,Runtime.from_env())
    except BaseException as error:
        traceback.print_exc()
        write_json(run_dir/"completion.json",{"status":"FAILED","error":type(error).__name__+": "+str(error),"artifacts":[]})
        return 1

if __name__=="__main__":raise SystemExit(main())
