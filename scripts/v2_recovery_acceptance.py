"""Actual owned Windows subprocess cancellation, timeout and restart tests."""
import json,os,subprocess,sys,time,urllib.request,uuid
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parents[1]
BASE="http://127.0.0.1:7243/api/v2"
RUNTIME=ROOT/"var/quantradar2"/("recovery-"+uuid.uuid4().hex)
OUT=ROOT/"docs/acceptance/quantradar2-g2"
def api(path,body=None):
    req=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers={"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(req,timeout=10))
def wait_for(callback,timeout=25):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        try:
            value=callback()
            if value:return value
        except (OSError,ValueError):pass
        time.sleep(.2)
    raise TimeoutError("Expected condition not met")
def start():
    env=dict(os.environ,QUANTRADAR2_RUNTIME=str(RUNTIME),QUANTRADAR2_DATA_CONFIG=str(ROOT/"var/quantradar2/data-service.env"),QUANTRADAR2_PORT="7243",QUANTRADAR2_TIMEOUT="8",PYTHONUTF8="1")
    with (RUNTIME/"api.log").open("ab") as output:
        process=subprocess.Popen([sys.executable,"-B","scripts/v2_api.py"],cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    wait_for(lambda:api("/health"));return process

def create(source,name):
    strategy=api("/strategies",{"name":name,"source":source})
    return api("/runs",{"revision_id":strategy["revision_id"],"start_date":"2026-09-01","end_date":"2026-09-01","frequency":"day","initial_cash":500000,"benchmark":None})
def sleep_ready(run):
    def condition():
        result=api("/runs/"+run["id"])
        text=api("/runs/"+run["id"]+"/logs")["text"]
        return result if result.get("pid") and "SLEEP_ENTERED" in text else None
    return wait_for(condition)
def gone(run):
    try:return abs(psutil.Process(run["pid"]).create_time()-run["process_created"])>0.001
    except psutil.NoSuchProcess:return True

def main():
    RUNTIME.mkdir(parents=True);OUT.mkdir(parents=True,exist_ok=True)
    process=start();evidence=[]
    slow="def initialize(context):\n    import time,subprocess,sys\n    child=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n    print('SLEEP_ENTERED CHILD='+str(child.pid), flush=True)\n    time.sleep(60)\n"
    try:
        run=create(slow,"cancel owned simulation");running=sleep_ready(run)
        children=[{"pid":p.pid,"process_created":p.create_time()} for p in psutil.Process(running["pid"]).children(recursive=True)]
        assert children,"Expected owned descendant process"
        queued=create("def initialize(context): pass", "cancel queued simulation")
        assert api("/runs/"+queued["id"]+"/stop",{})["status"]=="CANCELLED"
        assert api("/runs/"+run["id"]+"/stop",{})["status"]=="CANCELLED"
        wait_for(lambda:gone(running))
        for child in children:wait_for(lambda:gone(child))
        evidence.append({"descendants_verified":len(children),"test":"queued and running cancel","status":"passed","pid_identity_checked":True});print("real cancellation passed",flush=True)
        failed=create("def initialize(context): pass\ndef handle_data(context, data): raise RuntimeError('intentional G2 callback failure')", "callback failure")
        result=wait_for(lambda:(r if (r:=api("/runs/"+failed["id"]))["status"]=="FAILED" else None))
        assert "callback failed" in result["error"]
        evidence.append({"test":"swallowed native callback error mapped to FAILED","status":"passed"});print("callback failure passed",flush=True)
        timed=create(slow,"timeout owned simulation");running=sleep_ready(timed)
        result=wait_for(lambda:(r if (r:=api("/runs/"+timed["id"]))["status"]=="FAILED" else None))
        assert result["error"]=="Task timeout";wait_for(lambda:gone(running))
        evidence.append({"test":"8 second timeout stops owned process","status":"passed"});print("real timeout passed",flush=True)
        restarted=create(slow,"restart owned simulation");running=sleep_ready(restarted)
        process.terminate();process.wait(5)
        process=start()
        recovered=api("/runs/"+restarted["id"])
        assert recovered["status"]=="INTERRUPTED"
        wait_for(lambda:gone(running))
        time.sleep(.5)
        assert api("/runs/"+restarted["id"])["status"]=="INTERRUPTED"
        evidence.append({"test":"unclean API restart stops verified orphan and does not reexecute","status":"passed"});print("real restart recovery passed",flush=True)
        (OUT/"recovery-suite.json").write_text(json.dumps({"tests":evidence,"runtime":str(RUNTIME),"data_service":"existing data-only 58621","trading_calls":0},indent=2),encoding="utf-8")
    finally:
        if process.poll() is None:process.terminate();process.wait(5)
if __name__=="__main__":main()
