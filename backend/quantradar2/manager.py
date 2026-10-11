"""Single FIFO worker; only the API writes SQLite."""
import hashlib,json,os,subprocess,sys,threading,time
from pathlib import Path
from datetime import datetime,timezone
import psutil
from .runtime import ROOT
from .storage import encode

class Manager:
    def __init__(self,store,runtime):
        self.store,self.runtime=store,runtime
        self.halt=threading.Event();self.lock=threading.RLock();self.child=None
        self.thread=threading.Thread(target=self.loop,name="v2-task-worker",daemon=True)
        self.last_error=None

    def owned(self,run):
        try:
            if not run.get("pid") or not run.get("process_created"):return None
            p=psutil.Process(run["pid"])
            if abs(p.create_time()-run["process_created"])>0.001:return None
            command=p.cmdline()
            if "quantradar2.runner" not in command:return None
            index=command.index("--run-dir")
            if Path(command[index+1]).resolve()!=self.runtime.run_dir(run["id"]).resolve():return None
            return p
        except (psutil.Error,ValueError,IndexError):return None

    def terminate(self,run):
        p=self.owned(run)
        if p is None:return
        children=p.children(recursive=True)
        for c in reversed(children):
            try:c.terminate()
            except psutil.NoSuchProcess:pass
        try:p.terminate()
        except psutil.NoSuchProcess:pass
        _,alive=psutil.wait_procs(children+[p],timeout=3)
        for c in alive:
            try:c.kill()
            except psutil.NoSuchProcess:pass

    def finish(self,run,exit_code=None):
        directory=self.runtime.run_dir(run["id"])
        marker=directory/"completion.json"
        if not marker.exists():
            self.store.transition(run["id"],"FAILED",exit_code=exit_code,error="Runner ended without a completion marker")
            return
        result=json.loads(marker.read_text(encoding="utf-8"))
        status=result["status"]
        if status not in {"SUCCEEDED","FAILED"}:raise ValueError("Invalid completion status")
        artifacts=result.get("artifacts",[])
        for item in artifacts:
            name=item["name"]
            if Path(name).name!=name or name in {".",".."}:raise ValueError("Unsafe artifact name")
            path=directory/name
            if path.is_symlink() or not path.is_file():raise ValueError("Invalid artifact")
            if path.stat().st_size!=item["bytes"] or hashlib.sha256(path.read_bytes()).hexdigest()!=item["sha256"]:raise ValueError("Artifact checksum mismatch")
        fields={"exit_code":exit_code,"error":result.get("error")}
        for name in ["effective_config","environment"]:
            path=directory/(name+".json")
            if path.exists():fields[("effective" if name=="effective_config" else name)+"_json"]=encode(json.loads(path.read_text(encoding="utf-8")))
        self.store.register_artifacts(run["id"],artifacts)
        self.store.transition(run["id"],status,**fields)

    def start(self):
        # Never re-execute a task that was already running when the API stopped.
        for run in self.store.active_runs():
            if not run.get("pid"):
                # The child publishes its identity independently, covering an
                # API crash between Popen and the SQLite identity update.
                marker=self.runtime.run_dir(run["id"])/"runner-process.json"
                deadline=time.monotonic()+2
                while not marker.exists() and time.monotonic()<deadline:time.sleep(.05)
                if marker.exists():
                    try:
                        identity=json.loads(marker.read_text(encoding="utf-8"))
                        candidate=dict(run,pid=identity["pid"],process_created=identity["process_created"])
                        if type(candidate["pid"]) is int and isinstance(candidate["process_created"],(int,float)) and self.owned(candidate):
                            run=self.store.transition(run["id"],"RUNNING",pid=candidate["pid"],process_created=candidate["process_created"])
                    except (KeyError,ValueError,OSError):pass
            if self.owned(run):self.terminate(run)
            marker=self.runtime.run_dir(run["id"])/"completion.json"
            if marker.exists():
                try:self.finish(run)
                except Exception as error:self.store.transition(run["id"],"FAILED",error=str(error))
            else:self.store.transition(run["id"],"INTERRUPTED",error="API restarted before completion; task was not rerun")
        self.thread.start()

    def stop_run(self,run_id):
        with self.lock:
            run=self.store.run(run_id)
            if run["status"] in {"QUEUED","RUNNING"}:
                if run["status"]=="RUNNING":self.terminate(run)
                return self.store.transition(run_id,"CANCELLED",error="Stopped by user")
            return run

    def close(self):
        self.halt.set();self.thread.join(timeout=5)
        with self.lock:
            for run in self.store.active_runs():
                self.terminate(run)
                self.store.transition(run["id"],"INTERRUPTED",error="API shut down")

    def launch(self,run):
        directory=self.runtime.run_dir(run["id"]);directory.mkdir(parents=True,exist_ok=False)
        revision=self.store.revision(run["revision_id"])
        (directory/"strategy.py").write_text(revision["source"],encoding="utf-8")
        (directory/"request.json").write_text(encode(run["request"]),encoding="utf-8")
        env={k:v for k,v in os.environ.items() if not k.startswith(("QMT_","BIG_QMT_","JQDATA_"))}
        env.update(PYTHONPATH=str(ROOT/"backend"),PYTHONUTF8="1",QUANTRADAR2_RUNTIME=str(self.runtime.root),QUANTRADAR2_DATA_CONFIG=str(self.runtime.data_config))
        env['LOG_DIR']=str(directory/'logs')
        with (directory/"stdout.log").open("wb") as output:
            self.child=subprocess.Popen([sys.executable,"-B","-m","quantradar2.runner","--run-dir",str(directory)],cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        process=psutil.Process(self.child.pid)
        self.store.transition(run["id"],"RUNNING",pid=process.pid,process_created=process.create_time())

    def loop(self):
        while not self.halt.wait(0.25):
            with self.lock:
                try:
                    active=self.store.active_runs()
                    if active:
                        run=active[0]
                        elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(run["started_at"])).total_seconds()
                        if elapsed>self.runtime.timeout_seconds:
                            self.terminate(run);self.store.transition(run["id"],"FAILED",error="Task timeout")
                        elif self.owned(run) is None:
                            code=self.child.poll() if self.child else None
                            self.finish(run,code)
                    else:
                        run=self.store.claim_next()
                        if run:
                            try:self.launch(run)
                            except Exception as error:self.store.transition(run["id"],"FAILED",error=str(error))
                except Exception as error:
                    self.last_error=str(error)
                    for run in self.store.active_runs():
                        self.terminate(run)
                        self.store.transition(run["id"],"FAILED",error=str(error))
