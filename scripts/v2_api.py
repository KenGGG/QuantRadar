"""Start only the V2 local service. A occupied port fails without killing it."""
import os,socket,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
if __name__=="__main__":
    port=int(os.environ.get("QUANTRADAR2_PORT","7242"))
    sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    if hasattr(socket,"SO_EXCLUSIVEADDRUSE"):sock.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
    try:sock.bind(("127.0.0.1",port));sock.listen(16)
    except OSError as error:raise SystemExit(f"V2 port {port} is unavailable: {error}")
    from quantradar2.api import create_app
    from quantradar2.runtime import Runtime
    import uvicorn
    runtime=Runtime.from_env();runtime.root.mkdir(parents=True,exist_ok=True)
    import psutil,json
    (runtime.root/"api-process.json").write_text(json.dumps({"pid":os.getpid(),"process_created":psutil.Process().create_time(),"port":port}),encoding="utf-8")
    uvicorn.Server(uvicorn.Config(create_app(runtime),host="127.0.0.1",port=port,log_level="info")).run(sockets=[sock])
