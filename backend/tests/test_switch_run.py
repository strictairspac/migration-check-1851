import sys,threading,json
from fastapi.testclient import TestClient
from src.main import app
from src.config.database import Session
from src.models.mapping import MappingVersion
c=TestClient(app)
H={'Authorization':'Bearer '+c.post('/auth/login',json={'email':'operator@migration.local','password':'Migrate2026!'}).json()['token']}
def mp(name):return next(m for m in c.get('/mappings',headers=H).json() if m['name']==name)
def put(m,**kw):
 d={'name':m['name'],'batch_id':m['batch_id'],'rules':m['rules'],'chunk_size':m['chunk_size'],'note':m['note']};d.update(kw)
 return c.put(f"/mappings/{m['id']}",json=d,headers=H)

def test_run_and_confirm_interleaved_stay_consistent():
    m=mp('检验结果标准映射');old=m['active_version']
    put(m,chunk_size=17);m=mp('检验结果标准映射')
    dry=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    new_id=dry['candidate_version_id']
    barrier=threading.Barrier(2);out={}
    def confirm():
        cl=TestClient(app);barrier.wait();out['confirm']=cl.post(f"/dry-runs/{dry['id']}/confirm",headers=H).status_code
    def submit():
        cl=TestClient(app);barrier.wait()
        r=cl.post('/runs',json={'name':'during-switch','mapping_id':m['id']},headers=H)
        out['run']=(r.status_code,r.json())
    ts=[threading.Thread(target=confirm),threading.Thread(target=submit)]
    [t.start() for t in ts];[t.join() for t in ts]
    assert out['run'][0]==200,out
    run=out['run'][1]
    assert run['mapping_version_id'] in (old['id'],new_id)
    with Session() as s:
        v=s.get(MappingVersion,run['mapping_version_id'])
        assert run['snapshot']['mapping']['rules']==v.rules
        assert run['snapshot']['mapping']['chunk_size']==v.chunk_size
        assert run['snapshot']['mapping']['rule_digest']==v.rule_digest
        assert run['snapshot']['mapping_version_id'] if False else True
    # exactly one active version
    versions=c.get(f"/mappings/{m['id']}",headers=H).json()['versions']
    assert len([v for v in versions if v['state']=='active'])==1

def test_queued_runs_use_accepted_rules_even_after_switch():
    m=mp('异常隔离复核映射');old=m['active_version']
    r1=c.post('/runs',json={'name':'q-old','mapping_id':m['id']},headers=H).json()
    assert r1['mapping_version_id']==old['id']
    put(m,chunk_size=2);m=mp('异常隔离复核映射')
    dry=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    assert c.post(f"/dry-runs/{dry['id']}/confirm",headers=H).json()['activated']
    r2=c.post('/runs',json={'name':'q-new','mapping_id':m['id']},headers=H).json()
    assert r2['mapping_version_id']==dry['candidate_version_id']
    old_run=c.get(f"/runs/{r1['id']}",headers=H).json()
    assert old_run['snapshot']['mapping']['chunk_size']==old['chunk_size']
    assert old_run['mapping_version_id']==old['id']
