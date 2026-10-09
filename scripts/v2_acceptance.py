"""Finite real-QMT capture and API/direct/native replay acceptance suite."""
import hashlib,json,os,subprocess,sys,time,urllib.request,uuid
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];RUNTIME=ROOT/"var/quantradar2"
OUT=ROOT/"docs/acceptance/quantradar2-g2"
BASE="http://127.0.0.1:7242/api/v2"
def api(path,body=None):
    request=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers={"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(request,timeout=20))
def wait(run):
    deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        result=api("/runs/"+run["id"])
        if result["status"] not in {"QUEUED","RUNNING"}:
            if result["status"]!="SUCCEEDED":raise RuntimeError(str(result))
            return result
        time.sleep(.3)
    raise TimeoutError("Acceptance task timeout")
def compare(left,right):
    checked={}
    for name in ["trades.csv","daily_positions.csv","daily_records.csv"]:
        assert (left/name).exists(),"Expected nonempty trade/position artifact: "+name
        pd.testing.assert_frame_equal(pd.read_csv(left/name),pd.read_csv(right/name),check_exact=True)
        checked[name]="exact"
    assert json.loads((left/"metrics.json").read_text(encoding="utf-8"))["metrics"]==json.loads((right/"metrics.json").read_text(encoding="utf-8"))["metrics"]
    checked["metrics"]="exact"
    return checked

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    cases=[("buy_hold","2026-09-01","2026-09-04","day",{}),
        ("daily_ma","2026-09-01","2026-09-30","day",{}),
        ("etf_monthly_momentum","2026-08-03","2026-09-30","day",{}),
        ("minute_sessions","2026-09-29","2026-09-30","minute",{"exit_date":"2026-09-30"})]
    evidence=[]
    for name,start,end,frequency,extras in cases:
        source=(ROOT/"examples/v2"/(name+".py")).read_text(encoding="utf-8")
        strategy=api("/strategies",{"name":"G2 "+name,"source":source})
        request={"revision_id":strategy["revision_id"],"start_date":start,"end_date":end,"frequency":frequency,"initial_cash":500000,"benchmark":"000300.XSHG","extras":extras,"reference_date":"2026-10-09","data_mode":"record"}
        recorded=wait(api("/runs",request));print(name,"recorded",recorded["id"],flush=True)
        replayed=wait(api("/runs/"+recorded["id"]+"/replay",{}));print(name,"API replay",replayed["id"],flush=True)
        left=RUNTIME/"runs"/recorded["id"];right=RUNTIME/"runs"/replayed["id"]
        api_parity=compare(left,right)
        direct=RUNTIME/"runs"/uuid.uuid4().hex;direct.mkdir()
        (direct/"strategy.py").write_bytes((left/"strategy.py").read_bytes())
        (direct/"request.json").write_text(json.dumps(replayed["request"]),encoding="utf-8")
        env=dict(os.environ,LOG_DIR=str(RUNTIME/"logs"),PYTHONPATH=str(ROOT/"backend"),PYTHONUTF8="1",QUANTRADAR2_DATA_CONFIG=str(RUNTIME/"absent-for-replay.env"))
        result=subprocess.run([sys.executable,"-B","-m","quantradar2.runner","--run-dir",str(direct)],cwd=ROOT,env=env,capture_output=True)
        (direct/"stdout.log").write_bytes(result.stdout+result.stderr)
        if result.returncode:raise RuntimeError("Direct replay failed: "+str(direct))
        direct_parity=compare(left,direct)
        manifest=json.loads((left/"frozen/manifest.json").read_bytes())
        trades=pd.read_csv(left/"trades.csv")
        item={"case":name,"recorded":recorded["id"],"api_replay":replayed["id"],"direct_replay":direct.name,"request":recorded["request"],"source_sha256":hashlib.sha256(source.encode()).hexdigest(),"frozen_requests":len(manifest["requests"]),"actions":sorted({r["action"] for r in manifest["requests"].values()}),"api_parity":api_parity,"direct_parity":direct_parity,"trades":len(trades),"fees":float(trades["commission"].sum()),"frozen_zip_sha256":hashlib.sha256((left/"frozen_data.zip").read_bytes()).hexdigest()}
        if name=="daily_ma":assert "MA warmup=10" in (left/"backtest.log").read_text(encoding="utf-8")
        if name=="etf_monthly_momentum":
            trade_dates=pd.to_datetime(trades.iloc[:,0]).dt.strftime("%Y-%m-%d").unique().tolist()
            assert set(trade_dates)<= {"2026-08-03","2026-09-01"}
            item["monthly_trade_dates"]=trade_dates
        if name=="minute_sessions":
            log=(left/"backtest.log").read_text(encoding="utf-8")
            assert log.count("MINUTE_CALLBACK ")==480
            assert log.count("SESSION_CHECK callbacks=240")==2
            assert len(trades)==2
            item["minute_callbacks"]=480;item["sessions_checked"]=2
        evidence.append(item)
        (OUT/"strategy-suite.json").write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding="utf-8")
        print(name,"exact native parity passed",len(trades),"trades",flush=True)
    print("All four strategy cases passed",flush=True)
if __name__=="__main__":main()
