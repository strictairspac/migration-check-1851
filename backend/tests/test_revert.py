import sys
from fastapi.testclient import TestClient
from src.main import app
c=TestClient(app)
H={'Authorization':'Bearer '+c.post('/auth/login',json={'email':'operator@migration.local','password':'Migrate2026!'}).json()['token']}
def mp(name):return next(m for m in c.get('/mappings',headers=H).json() if m['name']==name)
def put(m,**kw):
 d={'name':m['name'],'batch_id':m['batch_id'],'rules':m['rules'],'chunk_size':m['chunk_size'],'note':m['note']};d.update(kw)
 return c.put(f"/mappings/{m['id']}",json=d,headers=H)

def test_edit_then_revert_invalidates():
    m=mp('检验结果标准映射')
    original=m['active_version']['chunk_size']
    put(m,chunk_size=original+1);m=mp('检验结果标准映射')
    d=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    # revert to the in-use rules exactly
    put(m,chunk_size=original)
    v=c.get(f"/dry-runs/{d['id']}",headers=H).json()
    assert v['valid'] is False, v
    r=c.post(f"/dry-runs/{d['id']}/confirm",headers=H);assert r.status_code==409
    m2=mp('检验结果标准映射')
    assert m2['active_version']['id']==m['active_version']['id']
    assert m2['pending_version'] is None

def test_batch_edit_invalidates_before_any_confirm():
    m=mp('检验结果标准映射')
    put(m,chunk_size=15);m=mp('检验结果标准映射')
    d=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    b=next(x for x in c.get('/batches',headers=H).json() if x['id']==m['batch_id'])
    rows=[r for r in b['rows']];rows[0]=dict(rows[0]);rows[0]['结果']='999.9'
    c.put(f"/batches/{b['id']}",json={k:b[k] for k in ('name','source_file','description')}|{'rows':rows},headers=H)
    r=c.post(f"/dry-runs/{d['id']}/confirm",headers=H);assert r.status_code==409
    m2=mp('检验结果标准映射');assert m2['active_version']['id']==m['active_version']['id']

def test_switch_applies_only_to_trialed_batch_revision():
    # A switch made for revision N stays for revision N; editing the batch
    # afterwards must fall back to the baseline, not inherit the switch.
    m=mp('检验结果标准映射')
    base=m['active_version']
    b=next(x for x in c.get('/batches',headers=H).json() if x['id']==m['batch_id'])
    bd={k:b[k] for k in ('name','source_file','description','rows')}
    bd['rows']=bd['rows'][:3]
    c.put(f"/batches/{b['id']}",json=bd,headers=H)
    m=mp('检验结果标准映射')
    put(m,chunk_size=41);m=mp('检验结果标准映射')
    d=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    assert c.post(f"/dry-runs/{d['id']}/confirm",headers=H).json()['activated']
    run_now=c.post('/runs',json={'name':'rev-same','mapping_id':m['id']},headers=H).json()
    assert run_now['snapshot']['mapping']['chunk_size']==41
    # edit batch: new revision must use the old baseline rules
    bd['rows']=bd['rows']+[{'委托号':'Z-1','检测项':'拉伸','结果':'1.0','单位':'MPa','时间':'2026-11-17T09:00:00+08:00'}]
    c.put(f"/batches/{b['id']}",json=bd,headers=H)
    run_next=c.post('/runs',json={'name':'rev-new','mapping_id':m['id']},headers=H).json()
    assert run_next['snapshot']['mapping']['chunk_size']==base['chunk_size']
    # and the switch can be re-trialed and confirmed for the new revision
    put(m,chunk_size=41);m=mp('检验结果标准映射')
    d2=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H)
    assert d2.status_code==200,d2.text
    assert c.post(f"/dry-runs/{d2.json()['id']}/confirm",headers=H).json()['activated']
    run_again=c.post('/runs',json={'name':'rev-new-2','mapping_id':m['id']},headers=H).json()
    assert run_again['snapshot']['mapping']['chunk_size']==41

def test_switching_version_can_be_superseded_by_new_trial():
    # After a switch, editing again must stage a candidate relative to the
    # version actually in use for that batch revision, then switch again.
    m=mp('空批次映射')
    put(m,chunk_size=51);m=mp('空批次映射')
    d1=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    assert c.post(f"/dry-runs/{d1['id']}/confirm",headers=H).json()['activated']
    put(m,chunk_size=52);m=mp('空批次映射')
    d2=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    assert d2['base_version_id']==d1['candidate_version_id'],d2['result']['base']
    assert c.post(f"/dry-runs/{d2['id']}/confirm",headers=H).json()['activated']
    run=c.post('/runs',json={'name':'chain-run','mapping_id':m['id']},headers=H).json()
    assert run['snapshot']['mapping']['chunk_size']==52
    versions=c.get(f"/mappings/{m['id']}",headers=H).json()['versions']
    assert len([v for v in versions if v['state']=='active'])==1
