import sys
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
import src.config.database as db
from src.main import app
c=TestClient(app)
H={'Authorization':'Bearer '+c.post('/auth/login',json={'email':'operator@migration.local','password':'Migrate2026!'}).json()['token']}
def mp(name):return next(m for m in c.get('/mappings',headers=H).json() if m['name']==name)

def test_failed_commit_keeps_in_use_version(monkeypatch):
    m=mp('检验结果标准映射');base=m['active_version']
    d={'name':m['name'],'batch_id':m['batch_id'],'rules':m['rules'],'chunk_size':21,'note':''}
    c.put(f"/mappings/{m['id']}",json=d,headers=H)
    m=mp('检验结果标准映射')
    dry=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    real=db.Session
    calls={'n':0}
    class Boom:
        def __init__(self,*a,**k):self._s=real(*a,**k)
        def __getattr__(self,n):return getattr(self._s,n)
        def commit(self):
            calls['n']+=1
            raise OperationalError('COMMIT',{},Exception('simulated failure'))
        def rollback(self):return self._s.rollback()
        def __enter__(self):return self
        def __exit__(self,*a):
            try:self._s.rollback()
            finally:self._s.close()
    import src.services.versioning as v
    monkeypatch.setattr(db,'Session',lambda *a,**k: Boom())
    r=c.post(f"/dry-runs/{dry['id']}/confirm",headers=H)
    assert r.status_code==409,r.text
    monkeypatch.undo()
    m2=mp('检验结果标准映射')
    assert m2['active_version']['id']==base['id']
    assert m2['pending_version'] is not None
    # retry after the failure succeeds exactly once
    r2=c.post(f"/dry-runs/{dry['id']}/confirm",headers=H);assert r2.status_code==200 and r2.json()['activated']
    r3=c.post(f"/dry-runs/{dry['id']}/confirm",headers=H);assert r3.json()['already_applied'] and not r3.json()['activated']
