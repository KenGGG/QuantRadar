from pathlib import Path
from fastapi.testclient import TestClient
from quantradar2.api import create_app
from quantradar2.runtime import Runtime

def test_blank_strategy_draft_and_history_across_revisions(tmp_path):
    import hashlib
    app=create_app(Runtime(tmp_path,tmp_path/'absent.env'),worker=False)
    with TestClient(app) as client:
        draft=client.post('/api/v2/strategies',json={'name':'blank','source':''})
        assert draft.status_code==200
        first=draft.json()
        assert first['source']=='' and first['source_hash']==hashlib.sha256(b'').hexdigest()
        body={'revision_id':first['revision_id'],'start_date':'2024-01-02','end_date':'2024-01-03','data_mode':'live'}
        assert client.post('/api/v2/runs',json=body).status_code==400
        assert not client.get('/api/v2/runs').json()
        saved=client.put('/api/v2/strategies/'+first['id'],json={'name':'blank','source':'pass'}).json()
        assert client.get('/api/v2/revisions/'+first['revision_id']).json()['source']==''
        one=app.state.store.create_run(saved['revision_id'],{})
        another=client.put('/api/v2/strategies/'+first['id'],json={'name':'blank','source':'x=1'}).json()
        two=app.state.store.create_run(another['revision_id'],{})
        other=app.state.store.save_strategy('other','pass')
        app.state.store.create_run(other['revision_id'],{})
        history=client.get('/api/v2/runs',params={'strategy_id':first['id']}).json()
        assert {r['id'] for r in history}=={one['id'],two['id']}
        assert client.get('/api/v2/strategies/'+first['id']).json()['run_count']==2
        assert client.post('/api/v2/strategies',json={'name':' ','source':''}).status_code==400

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


def test_prepared_run_requires_valid_data_plan_and_rejects_minute_before_queue(tmp_path):
    app=create_app(Runtime(tmp_path,tmp_path/'absent.env'),worker=False)
    with TestClient(app) as client:
        strategy=client.post('/api/v2/strategies',json={'name':'prepared','source':'pass'}).json()
        body={'revision_id':strategy['revision_id'],'start_date':'2024-01-02','end_date':'2024-01-05','data_mode':'prepared'}
        assert client.post('/api/v2/runs',json=body).status_code==400
        body['data_requirements']={'securities':['510300.XSHG'],'warmup_bars':84}
        assert client.post('/api/v2/runs',json=dict(body,frequency='minute')).status_code==400
        result=client.post('/api/v2/runs',json=body)
        assert result.status_code==202
        assert result.json()['request']['data_requirements']==body['data_requirements']

def test_auto_mode_selects_prepared_or_record_and_keeps_invalid_plans_visible(tmp_path):
    app=create_app(Runtime(tmp_path,tmp_path/'absent.env'),worker=False)
    with TestClient(app) as client:
        strategy=client.post('/api/v2/strategies',json={'name':'new','source':'def initialize(context): pass'}).json()
        body={'revision_id':strategy['revision_id'],'start_date':'2019-01-01','end_date':'2019-01-03','data_mode':'auto'}
        result=client.post('/api/v2/runs',json=body)
        assert result.status_code==202
        assert result.json()['request']['data_mode']=='record'
        assert result.json()['request']['requested_data_mode']=='auto'
        assert result.json()['request']['data_mode_reason']
        plan={'securities':['510300.XSHG'],'warmup_bars':84}
        result=client.post('/api/v2/runs',json=dict(body,data_requirements=plan))
        assert result.status_code==202 and result.json()['request']['data_mode']=='prepared'
        fixed=client.post('/api/v2/strategies',json={'name':'fixed','source':f'DATA_REQUIREMENTS = {plan!r}\ndef initialize(context): pass'}).json()
        result=client.post('/api/v2/runs',json=dict(body,revision_id=fixed['revision_id']))
        assert result.status_code==202 and result.json()['request']['data_mode']=='prepared'
        result=client.post('/api/v2/runs',json=dict(body,revision_id=fixed['revision_id'],frequency='minute'))
        assert result.status_code==202 and result.json()['request']['data_mode']=='record'
        assert client.post('/api/v2/runs',json=dict(body,data_requirements={})).status_code==400
        invalid=client.post('/api/v2/strategies',json={'name':'invalid','source':'DATA_REQUIREMENTS = {}'}).json()
        assert client.post('/api/v2/runs',json=dict(body,revision_id=invalid['revision_id'])).status_code==400
        strict=client.post('/api/v2/runs',json=dict(body,data_mode='prepared'))
        assert strict.status_code==400 and '自动模式' in strict.json()['detail']
        broken=client.post('/api/v2/strategies',json={'name':'syntax','source':'def initialize('}).json()
        assert client.post('/api/v2/runs',json=dict(body,revision_id=broken['revision_id'])).status_code==400

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

def test_report_initial_equity_annotation_preserves_original_artifact(tmp_path):
    import json,hashlib
    app=create_app(Runtime(tmp_path,tmp_path/"absent.env"),worker=False)
    store=app.state.store;strategy=store.save_strategy("sample","pass")
    run=store.create_run(strategy["revision_id"],{});directory=tmp_path/"runs"/run["id"];directory.mkdir(parents=True)
    content=b"<html><body>Native overview initial: 499995</body></html>"
    (directory/"standard_report.html").write_bytes(content)
    (directory/"metrics.json").write_text(json.dumps({"meta":{"initial_total_value":500000}}))
    store.register_artifacts(run["id"],[{"name":"standard_report.html","sha256":hashlib.sha256(content).hexdigest(),"bytes":len(content)}])
    with TestClient(app) as client:
        response=client.get(f"/api/v2/runs/{run['id']}/report")
        assert response.status_code==200
        assert "500,000.00" in response.text and "Native overview initial: 499995" in response.text
    assert (directory/"standard_report.html").read_bytes()==content

def test_preview_range_limits_are_inclusive_and_checked_before_connecting(tmp_path):
    app=create_app(Runtime(tmp_path,tmp_path/"absent.env"),worker=False)
    with TestClient(app) as client:
        base={"security":"510300.XSHG","start":"2026-09-29","end":"2026-09-30","frequency":"minute"}
        assert client.get("/api/v2/data/preview",params=base).status_code==400
        assert client.get("/api/v2/data/preview",params=dict(base,end="2026-09-29")).status_code==503
        assert client.get("/api/v2/data/preview",params=dict(base,start="2026-09-01",end="2026-10-02",frequency="daily")).status_code==400
