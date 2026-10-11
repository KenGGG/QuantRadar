"""Loopback research API, no legacy bootstrap and no trading endpoints."""
from contextlib import asynccontextmanager
from datetime import date
import json
from pathlib import Path
from fastapi import FastAPI,HTTPException,Query
from fastapi.responses import FileResponse,JSONResponse,HTMLResponse
from pydantic import BaseModel,Field,model_validator
from .runtime import Runtime,ROOT,engine_identity
from .storage import Store
from .manager import Manager

class StrategyInput(BaseModel):
    name:str=Field(min_length=1,max_length=200)
    source:str=Field(min_length=1,max_length=500000)

class RunInput(BaseModel):
    revision_id:str=Field(pattern=r"^[0-9a-f]{32}$")
    start_date:date
    end_date:date
    frequency:str=Field(default="day",pattern=r"^(day|minute)$")
    initial_cash:float=Field(default=500000,gt=0,le=1e12,allow_inf_nan=False)
    benchmark:str|None=Field(default="000300.XSHG",max_length=50)
    extras:dict=Field(default_factory=dict)
    data_mode:str=Field(default="live",pattern=r"^(live|record|prepared)$")
    data_requirements:dict|None=None
    refresh_data:bool=False
    reference_date:date=Field(default_factory=date.today)
    @model_validator(mode="after")
    def dates(self):
        if self.end_date<self.start_date:raise ValueError("End date precedes start date")
        return self


def create_app(runtime=None,worker=True):
    runtime=runtime or Runtime.from_env()
    store=Store(runtime.root/"metadata.sqlite3")
    manager=Manager(store,runtime)
    @asynccontextmanager
    async def lifespan(app):
        if worker:manager.start()
        try:yield
        finally:
            if worker:manager.close()
    app=FastAPI(title="QuantRadar2 research",lifespan=lifespan)
    app.state.store=store;app.state.manager=manager
    @app.exception_handler(KeyError)
    async def missing(request,error):return JSONResponse(status_code=404,content={"detail":"Record not found"})
    @app.exception_handler(ValueError)
    async def invalid(request,error):return JSONResponse(status_code=400,content={"detail":str(error)})
    @app.middleware("http")
    async def local_only(request,call_next):
        # Browser pages may use the same-origin V2 proxy. Refuse other origins.
        origin=request.headers.get("origin")
        if origin:
            from urllib.parse import urlparse
            url=urlparse(origin)
            if url.hostname not in {"127.0.0.1","localhost"} or url.port not in {7242,5174}:
                return JSONResponse(status_code=403,content={"detail":"Local research origin required"})
        response=await call_next(request)
        response.headers["X-Content-Type-Options"]="nosniff"
        return response
    @app.get("/api/v2/health")
    def health():return {"status":"ok","trading":False,"engine":engine_identity(),"worker_error":manager.last_error}
    @app.get("/api/v2/strategies")
    def strategies(include_archived:bool=False):return store.strategies(include_archived)
    @app.post("/api/v2/strategies")
    def create_strategy(body:StrategyInput):return store.save_strategy(body.name,body.source)
    @app.get("/api/v2/strategies/{strategy_id}")
    def strategy(strategy_id:str):return store.strategy(strategy_id)
    @app.put("/api/v2/strategies/{strategy_id}")
    def save(strategy_id:str,body:StrategyInput):return store.save_strategy(body.name,body.source,strategy_id)
    @app.delete("/api/v2/strategies/{strategy_id}")
    def archive(strategy_id:str):return store.archive_strategy(strategy_id)
    @app.post("/api/v2/strategies/{strategy_id}/restore")
    def restore(strategy_id:str):return store.archive_strategy(strategy_id,False)
    @app.post("/api/v2/strategies/{strategy_id}/copy")
    def copy(strategy_id:str):
        old=store.strategy(strategy_id)
        return store.save_strategy(old["name"]+" copy",old["source"])
    @app.get("/api/v2/strategies/{strategy_id}/revisions")
    def revisions(strategy_id:str):
        store.strategy(strategy_id)
        with store.connection() as db:return [dict(r) for r in db.execute("SELECT * FROM revisions WHERE strategy_id=? ORDER BY revision DESC",(strategy_id,))]
    @app.get("/api/v2/revisions/{revision_id}")
    def revision(revision_id:str):return store.revision(revision_id)
    @app.get("/api/v2/runs")
    def runs(limit:int=Query(default=100,ge=1,le=1000)):return store.runs(limit)
    @app.post("/api/v2/runs",status_code=202)
    def run_create(body:RunInput):
        revision=store.revision(body.revision_id)
        if body.data_mode=="prepared":
            from .prepared import requirements
            import re
            if body.frequency!="day":raise ValueError('Prepared data currently supports daily backtests only')
            if body.benchmark and not re.fullmatch(r'\d{6}\.(XSHG|XSHE)',body.benchmark):raise ValueError('Invalid prepared benchmark')
            requirements(revision['source'],body.data_requirements)
        strategy=store.strategy(revision["strategy_id"])
        request=body.model_dump(mode="json",exclude={"revision_id"})
        request["strategy_name"]=strategy["name"]
        return store.create_run(body.revision_id,request)
    @app.get("/api/v2/runs/{run_id}")
    def run(run_id:str):return store.run(run_id)
    @app.post("/api/v2/runs/{run_id}/stop")
    def stop(run_id:str):return manager.stop_run(run_id)
    @app.post("/api/v2/runs/{run_id}/replay",status_code=202)
    def replay_run(run_id:str):
        source=store.run(run_id)
        if source["status"]!="SUCCEEDED" or source["request"].get("data_mode") not in {"record","prepared"}:raise HTTPException(400,"A successful recorded or prepared run is required")
        if not (source.get("effective") or {}).get("engine_policy",{}).get("strict_data"):
            raise HTTPException(400,"Experimental snapshot lacks the strict engine policy; record a new run")
        request=dict(source["request"],data_mode="replay",frozen_source_run_id=run_id)
        return store.create_run(source["revision_id"],request)
    @app.get("/api/v2/runs/{run_id}/logs")
    def logs(run_id:str,offset:int=Query(default=0,ge=0),limit:int=Query(default=65536,ge=4,le=262144)):
        store.run(run_id);path=runtime.run_dir(run_id)/"stdout.log"
        if not path.exists():return {"text":"","offset":0}
        with path.open("rb") as file:
            file.seek(offset);data=file.read(limit)
            import codecs
            decoder=codecs.getincrementaldecoder("utf-8")(errors="replace")
            text=decoder.decode(data,final=file.tell()>=path.stat().st_size)
            pending,_=decoder.getstate()
            return {"text":text,"offset":offset+len(data)-len(pending)}
    @app.get("/api/v2/runs/{run_id}/artifacts")
    def artifacts(run_id:str):return store.artifacts(run_id)
    @app.get("/api/v2/runs/{run_id}/artifacts/{name}")
    def artifact(run_id:str,name:str):
        registered={x["name"] for x in store.artifacts(run_id)}
        if name not in registered or Path(name).name!=name:raise HTTPException(404,"Artifact not found")
        path=runtime.run_dir(run_id)/name
        if path.is_symlink() or not path.is_file():raise HTTPException(404,"Artifact not found")
        return FileResponse(path,filename=name)
    @app.get("/api/v2/runs/{run_id}/report")
    def report(run_id:str):
        if "standard_report.html" not in {x["name"] for x in store.artifacts(run_id)}:raise HTTPException(404,"Report not ready")
        import html,re
        directory=runtime.run_dir(run_id)
        metrics=json.loads((directory/"metrics.json").read_text(encoding="utf-8"))
        initial=(metrics.get("meta") or {}).get("initial_total_value")
        content=(directory/"standard_report.html").read_text(encoding="utf-8")
        if isinstance(initial,(int,float)):
            note=("<div style='padding:16px;margin:16px;background:#fff9e6;border:1px solid #ffe58f;border-radius:8px'>"
                "\u5b9e\u9645\u521d\u59cb\u6743\u76ca\uff08\u5f15\u64ce\u7ed3\u679c\uff09\uff1a<b>"+html.escape(f"{initial:,.2f}")+" \u5143</b>\u3002"
                "\u539f\u751f\u6982\u89c8\u4e2d\u7684\u201c\u521d\u59cb\u8d44\u91d1\u201d\u53d6\u9996\u65e5\u6536\u76d8\u6743\u76ca\u3002"
                "\u6307\u6807\u4e0e\u56fe\u8868\u4fdd\u7559\u539f\u751f\u7ed3\u679c\u3002</div>")
            content=re.sub(r"(<body[^>]*>)",lambda match:match.group(1)+note,content,count=1,flags=re.I)
        return HTMLResponse(content,headers={"Content-Security-Policy":"sandbox allow-scripts; default-src 'self' data: https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com"})

    @app.get("/api/v2/data/capabilities")
    def capabilities():return {"source":"big_qmt","trading":False,"periods":["day","minute"],"historical_limits":"native engine estimate","historical_constituents":"unqualified","financial_point_in_time":"unqualified","tick":"unqualified"}
    @app.get("/api/v2/data/health")
    def data_health():
        from dotenv import dotenv_values
        from .provider import ResearchQmtProvider
        values=dotenv_values(runtime.data_config)
        if not values.get("QMT_SERVER_TOKEN"):raise HTTPException(503,"Data service is not configured")
        p=ResearchQmtProvider({"host":"127.0.0.1","port":int(values.get("QMT_SERVER_PORT",58621)),"token":values["QMT_SERVER_TOKEN"]})
        try:
            result=p._connection.request("admin.health",{},timeout=10)
            return result.get("value",result)
        except Exception:raise HTTPException(503,"Data service unavailable; inspect local service log")
        finally:p._connection.close()
    @app.get("/api/v2/data/preview")
    def preview(security:str=Query(pattern=r"^[0-9]{6}\.(XSHG|XSHE)$"),start:date=Query(),end:date=Query(),frequency:str=Query(default="daily",pattern=r"^(daily|minute)$")):
        if end<start or (end-start).days>=(31 if frequency=="daily" else 1):raise HTTPException(400,"Preview range is limited to 31 daily days or one minute day")
        from dotenv import dotenv_values
        from .provider import ResearchQmtProvider
        from .runner import plain
        values=dotenv_values(runtime.data_config)
        if not values.get("QMT_SERVER_TOKEN"):raise HTTPException(503,"Data service is not configured")
        provider=ResearchQmtProvider({"host":"127.0.0.1","port":int(values.get("QMT_SERVER_PORT",58621)),"token":values["QMT_SERVER_TOKEN"]})
        try:
            frame=provider.get_price(security,start_date=str(start),end_date=str(end)+(" 15:00:00" if frequency=="minute" else ""),frequency=frequency,fields=["open","high","low","close","volume","money"],fq="none")
            data=json.loads(frame.reset_index().to_json(orient="records",date_format="iso"))
            return {"source":"big_qmt","count":len(frame),"columns":list(frame.columns),"records":data[:250]}
        except Exception as error:raise HTTPException(502,str(error))
        finally:provider._connection.close()
    build=ROOT/"frontend/dist-v2"
    if (build/"v2.html").exists():
        from fastapi.staticfiles import StaticFiles
        app.mount("/assets",StaticFiles(directory=build/"assets"),name="v2-assets")
        @app.get("/")
        def index():return FileResponse(build/"v2.html",media_type="text/html")
    return app
