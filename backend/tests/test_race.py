import sys,threading
from fastapi.testclient import TestClient
from src.main import app
from src.services import versioning
c=TestClient(app)
H={'Authorization':'Bearer '+c.post('/auth/login',json={'email':'operator@migration.local','password':'Migrate2026!'}).json()['token']}
def mp(name):return next(m for m in c.get('/mappings',headers=H).json() if m['name']==name)
def put(m,**kw):
 d={'name':m['name'],'batch_id':m['batch_id'],'rules':m['rules'],'chunk_size':m['chunk_size'],'note':m['note']};d.update(kw)
 return c.put(f"/mappings/{m['id']}",json=d,headers=H)

def test_cas_rejects_second_confirmation():
    m=mp('空批次映射')
    put(m,chunk_size=11)
    m=mp('空批次映射');d1=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    put(m,chunk_size=12)
    m=mp('空批次映射');d2=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    # first confirmation wins
    assert c.post(f"/dry-runs/{d2['id']}/confirm",headers=H).json()['activated']
    # pretend both were judged fresh: the CAS must still permit only one
    orig=versioning._stale_reasons
    versioning._stale_reasons=lambda *a: []
    try:
        r=c.post(f"/dry-runs/{d1['id']}/confirm",headers=H)
    finally:
        versioning._stale_reasons=orig
    assert r.status_code==409, r.text
    m=mp('空批次映射')
    assert m['active_version']['id']==d2['candidate_version_id']

def test_concurrent_confirm_one_wins():
    m=mp('检验结果标准映射')
    put(m,chunk_size=13)
    m=mp('检验结果标准映射');d1=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    put(m,chunk_size=14)
    m=mp('检验结果标准映射');d2=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    orig=versioning._stale_reasons
    versioning._stale_reasons=lambda *a: []
    barrier=threading.Barrier(2);results=[]
    def go(i):
        client=TestClient(app)
        barrier.wait()
        results.append((i,client.post(f"/dry-runs/{i}/confirm",headers=H).status_code))
    ts=[threading.Thread(target=go,args=(d,)) for d in (d1['id'],d2['id'])]
    try:
        [t.start() for t in ts];[t.join() for t in ts]
    finally:
        versioning._stale_reasons=orig
    codes=sorted(x[1] for x in results)
    print(codes)
    assert codes.count(200)<=1
    # at most one active version
    versions=c.get(f"/mappings/{m['id']}",headers=H).json()['versions']
    assert len([v for v in versions if v['state']=='active'])==1
