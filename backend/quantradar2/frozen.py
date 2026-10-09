"""Finite per-run wire-response freezing. Replay has no network connection."""
from datetime import date,datetime,timezone
import hashlib,json,time
from pathlib import Path
from .provider import ResearchQmtProvider

class FrozenDataError(RuntimeError):pass

def canonical(value):
    def default(v):
        if isinstance(v,(date,datetime)):return v.isoformat()
        raise TypeError("Unfreezable type: "+type(v).__name__)
    return json.dumps(value,default=default,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode("utf-8")

def key_for(action,payload):return hashlib.sha256(canonical({"action":action,"payload":payload})).hexdigest()

def write(path,value):
    pending=path.with_suffix(".tmp");pending.write_bytes(canonical(value))
    for attempt in range(5):
        try:pending.replace(path);return
        except PermissionError:
            if attempt==4:raise
            time.sleep(.03*(attempt+1))

class Recorder:
    def __init__(self,connection,directory,identity):
        self.connection=connection;self.directory=Path(directory);self.directory.mkdir()
        self.manifest={"version":1,"source":"big_qmt via data-only qmt-remote","identity":identity,"requests":{}}
        self.errors=[]
        write(self.directory/"manifest.json",self.manifest)
    def request(self,action,payload,**kwargs):
        if not action.startswith("data."):raise FrozenDataError("Recording permits data actions only")
        key=key_for(action,payload)
        try:
            value=self.connection.request(action,payload,**kwargs)
            record={"action":action,"payload":json.loads(canonical(payload)),"response":value}
        except Exception as error:
            record={"action":action,"payload":json.loads(canonical(payload)),"error":{"type":type(error).__name__,"message":str(error)}}
            self.checked_save(key,record)
            raise
        self.checked_save(key,record)
        return value
    def checked_save(self,key,record):
        try:self.save(key,record)
        except Exception as error:
            self.errors.append("Recording failed: "+type(error).__name__+": "+str(error))
            raise
    def save(self,key,record):
        content=canonical(record);digest=hashlib.sha256(content).hexdigest()
        existing=self.manifest["requests"].get(key)
        if existing and existing["sha256"]!=digest:
            self.errors.append("Repeated request changed during recording: "+key)
            raise FrozenDataError(self.errors[-1])
        if not existing:
            (self.directory/(key+".json")).write_bytes(content)
            self.manifest["requests"][key]={"sha256":digest,"bytes":len(content),"acquired_at":datetime.now(timezone.utc).isoformat(),"action":record["action"]}
            write(self.directory/"manifest.json",self.manifest)
    def close(self):self.connection.close()

class Replay:
    def __init__(self,directory,identity):
        self.directory=Path(directory)
        self.manifest=json.loads((self.directory/"manifest.json").read_bytes())
        if self.manifest.get("version")!=1 or self.manifest.get("identity")!=identity:raise FrozenDataError("Frozen input/engine identity mismatch")
        self.errors=[];self.used=set()
        for key,entry in self.manifest["requests"].items():
            if len(key)!=64 or any(c not in "0123456789abcdef" for c in key):raise FrozenDataError("Invalid frozen request key")
            path=self.directory/(key+".json")
            if path.is_symlink():raise FrozenDataError("Invalid frozen response path")
            content=path.read_bytes()
            if len(content)!=entry["bytes"] or hashlib.sha256(content).hexdigest()!=entry["sha256"]:raise FrozenDataError("Frozen response checksum mismatch")
    def request(self,action,payload,**kwargs):
        key=key_for(action,payload)
        if key not in self.manifest["requests"]:
            error="Frozen request is missing; network fallback forbidden: "+action+" "+key
            self.errors.append(error);raise FrozenDataError(error)
        self.used.add(key)
        record=json.loads((self.directory/(key+".json")).read_bytes())
        if record.get("error"):raise RuntimeError(record["error"]["message"])
        return record["response"]
    def close(self):pass

class FrozenProvider(ResearchQmtProvider):
    requires_live_data=False
    def __init__(self,connection):
        # Do not call RemoteQmtProvider.__init__: it starts a TCP connection.
        self.config={};self._connection=connection
        self._tick_callback=None;self._tick_context=None;self._subscription_key="frozen-replay"
