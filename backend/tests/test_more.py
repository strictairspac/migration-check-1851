import sys
from fastapi.testclient import TestClient
from src.main import app
from src.config.database import Session
from src.models.mapping import Mapping,MappingVersion
from src.models.batch import Batch
from src.services.migration import rule_digest
c=TestClient(app)
H={'Authorization':'Bearer '+c.post('/auth/login',json={'email':'operator@migration.local','password':'Migrate2026!'}).json()['token']}
def mp(name):return next(m for m in c.get('/mappings',headers=H).json() if m['name']==name)
def put(m,**kw):
 d={'name':m['name'],'batch_id':m['batch_id'],'rules':m['rules'],'chunk_size':m['chunk_size'],'note':m['note']};d.update(kw)
 return c.put(f"/mappings/{m['id']}",json=d,headers=H)

def test_bad_rules_detected():
    m=mp('异常隔离复核映射')
    # map 结果 from a nonexistent source -> rows missing column
    rules=[dict(r) for r in m['rules']]
    rules[4]['source']='采集时间'
    put(m,rules=rules)
    d=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    s=d['result']['summary']
    assert s['new_rejections']>0, s
    assert all(x['change']=='new_rejection' for x in d['result']['new_rejections'])
    assert d['result']['new_rejections'][0]['row_number']==1
    # key collision: make all sample_code same
    m=mp('异常隔离复核映射')
    rules=[dict(r) for r in m['rules']]
    print('status',c.get(f"/mappings/{m['id']}",headers=H).json().get('pending_version'))

def test_two_candidates_only_one_wins():
    m=mp('见山日班检验结果'.replace('见山日班检验结果','检验结果标准映射'))
    put(m,chunk_size=5)
    m=mp('检验结果标准映射');d1=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    put(m,chunk_size=6,note='second')
    m=mp('检验结果标准映射');d2=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    assert d1['candidate_version_id']!=d2['candidate_version_id']
    v1=c.get(f"/dry-runs/{d1['id']}",headers=H).json()
    # older dry run is invalid due to newer candidate
    assert v1['valid'] is False, v1['stale_reasons']
    r2=c.post(f"/dry-runs/{d2['id']}/confirm",headers=H);assert r2.json()['activated']
    # now first stale anyway
    r1=c.post(f"/dry-runs/{d1['id']}/confirm",headers=H);assert r1.status_code==409
    m=mp('检验结果标准映射');assert m['active_version']['id']==d2['candidate_version_id']

def test_queued_run_keeps_rules():
    m=mp('检验结果标准映射')
    active=m['active_version']
    r=c.post('/runs',json={'name':'queue-test-1','mapping_id':m['id']},headers=H)
    assert r.status_code==200,r.text
    run=r.json()
    assert run['mapping_version_id']==active['id']
    assert run['snapshot']['mapping']['chunk_size']==active['chunk_size']
    # change active version
    put(m,chunk_size=9)
    m=mp('检验结果标准映射');d=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    c.post(f"/dry-runs/{d['id']}/confirm",headers=H)
    run2=c.get(f"/runs/{run['id']}",headers=H).json()
    assert run2['snapshot']['mapping']['chunk_size']==active['chunk_size']
    assert run2['mapping_version_id']==active['id']

def test_batch_edit_keeps_old_for_new_revision():
    m=mp('空批次映射')
    base=m['active_version']
    b=next(x for x in c.get('/batches',headers=H).json() if x['id']==m['batch_id'])
    bdata={k:b[k] for k in ('name','source_file','description','rows')}
    bdata['rows']=[{'委托号':'A-1','检测项':'拉伸','结果':'1.5','单位':'MPa','时间':'2026-11-17T09:00:00+08:00'}]
    c.put(f"/batches/{b['id']}",json=bdata,headers=H)
    b2=next(x for x in c.get('/batches',headers=H).json() if x['id']==m['batch_id'])
    assert b2['revision']==b['revision']+1
    m=mp('空批次映射')
    put(m,chunk_size=3)
    m=mp('空批次映射');d=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    c.post(f"/dry-runs/{d['id']}/confirm",headers=H)
    run=c.post('/runs',json={'name':'rev-a','mapping_id':m['id']},headers=H).json()
    assert run['snapshot']['mapping']['chunk_size']==3
    # edit batch again -> switching version must not apply
    bdata['rows']=bdata['rows']+[{'委托号':'A-2','检测项':'拉伸','结果':'2.5','单位':'MPa','时间':'2026-11-17T09:00:00+08:00'}]
    c.put(f"/batches/{b['id']}",json=bdata,headers=H)
    run2=c.post('/runs',json={'name':'rev-b','mapping_id':m['id']},headers=H).json()
    assert run2['snapshot']['mapping']['chunk_size']==base['chunk_size'], run2['snapshot']['mapping']

def test_activation_supersedes_other_candidates():
    m=mp('检验结果标准映射')
    put(m,chunk_size=31);m=mp('检验结果标准映射');d1=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    put(m,chunk_size=32);m=mp('检验结果标准映射');d2=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    assert c.post(f"/dry-runs/{d2['id']}/confirm",headers=H).json()['activated']
    m=mp('检验结果标准映射')
    assert m['pending_version'] is None
    versions=c.get(f"/mappings/{m['id']}",headers=H).json()['versions']
    states={v['id']:v['state'] for v in versions}
    assert states[d2['candidate_version_id']]=='active'
    assert states[d1['candidate_version_id']]=='superseded'
    r=c.post(f"/dry-runs/{d1['id']}/confirm",headers=H);assert r.status_code==409
    # re-saving that older rule set stages a fresh candidate
    put(m,chunk_size=31)
    m=mp('检验结果标准映射')
    assert m['pending_version'] and m['pending_version']['chunk_size']==31
