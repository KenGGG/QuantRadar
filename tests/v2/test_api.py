from pathlib import Path
from fastapi.testclient import TestClient
from quantradar2.api import create_app
from quantradar2.runtime import Runtime

def test_revisions_run_validation_cancel_and_no_trading(tmp_path):
    app=create_app(Runtime(tmp_path,tmp_path/"absent.env"),worker=False)
    with TestClient(app) as client:
        strategy=client.post("/api/v2/strategies",json={"name":"sample","source":"def initialize(context): pass"}).json()
        saved=client.put("/api/v2/strategies/"+strategy["id"],json={"name":"sample","source":"def initialize(context): context.a=1"}).json()
        assert saved["revision"]==2
        old=client.get("/api/v2/strategies/"+strategy["id"]+"/revisions").json()
        assert old[1]["id"]==strategy["revision_id"]
        request={"revision_id":strategy["revision_id"],"start_date":"2026-09-01","end_date":"2026-09-04"}
        assert client.post("/api/v2/runs",json=dict(request,end_date="2026-08-01")).status_code==422
        response=client.post("/api/v2/runs",json=request)
        assert response.status_code==202
        run=response.json()
        assert run["revision_id"]==strategy["revision_id"]
        assert client.post("/api/v2/runs/"+run["id"]+"/stop").json()["status"]=="CANCELLED"
        assert client.post("/api/v2/trade",json={}).status_code==404
        assert client.post("/api/v2/strategies",json={"name":"x","source":"pass"},headers={"Origin":"https://example.com"}).status_code==403
        assert client.get("/api/v2/data/health").status_code==503

def test_log_offsets_preserve_multibyte_and_unregistered_artifacts(tmp_path):
    app=create_app(Runtime(tmp_path,tmp_path/"absent.env"),worker=False)
    store=app.state.store
    strategy=store.save_strategy("sample","pass")
    run=store.create_run(strategy["revision_id"],{})
    directory=tmp_path/"runs"/run["id"];directory.mkdir(parents=True)
    original="????????"*10
    (directory/"stdout.log").write_bytes(original.encode())
    (directory/"secret.env").write_text("secret")
    with TestClient(app) as client:
        offset=0;joined=""
        while offset<len(original.encode()):
            chunk=client.get(f"/api/v2/runs/{run['id']}/logs",params={"offset":offset,"limit":7}).json()
            assert chunk["offset"]>offset
            offset=chunk["offset"];joined+=chunk["text"]
        assert joined==original
        assert client.get(f"/api/v2/runs/{run['id']}/artifacts/secret.env").status_code==404
