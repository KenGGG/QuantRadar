from quantradar.etf_research import _run_group

def test_group_recovery_does_not_resubmit_existing_child(monkeypatch, tmp_path):
    updates=[]
    class Worker:
        def get_status(self, run_id): return {'status':'SUCCESS','error':None}
        def submit(self, _): raise AssertionError('must not resubmit persisted child')
    monkeypatch.setattr('quantradar.worker.get_worker',lambda:Worker())
    monkeypatch.setattr('quantradar.storage.update_experiment',lambda *_a,**kw:updates.append(kw['config']))
    config={'items':[{'template':'equal_weight','status':'PENDING','run_id':'run_old'}]}
    _run_group('group',None,config)
    assert config['items'][0]['status']=='SUCCESS'
