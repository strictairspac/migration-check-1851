import sys,os
from fastapi.testclient import TestClient
from src.main import app
from src.config.database import Base,engine,Session
from src.models.batch import Batch
from src.models.mapping import Mapping,MappingVersion,DryRun,MappingActivation
from src.models.run import Run,TargetRow
import pytest

c=TestClient(app)
r=c.post('/auth/login',json={'email':'operator@migration.local','password':'Migrate2026!'})
tok=r.json()['token'];H={'Authorization':'Bearer '+tok}
admin=c.post('/auth/login',json={'email':'admin@migration.local','password':'Migrate2026!'}).json()['token']
AH={'Authorization':'Bearer '+admin}

def mapping(name):
    return next(m for m in c.get('/mappings',headers=H).json() if m['name']==name)

def test_full_flow():
    m=mapping('检验结果标准映射')
    base=m['active_version']
    assert base and base['state']=='active'
    data={'name':m['name'],'batch_id':m['batch_id'],'rules':m['rules'],'chunk_size':m['chunk_size'],'note':'candidate renames unit'}
    rules=[dict(x) for x in m['rules']]
    # change: unit source becomes 结果? no - change unit to required false and rename? Use chunk change
    data['chunk_size']=3
    r=c.put(f"/mappings/{m['id']}",json=data,headers=H);assert r.status_code==200,r.text
    m2=mapping(m['name'])
    assert m2['active_version']['id']==base['id']
    assert m2['pending_version'] and m2['pending_version']['id']!=base['id']
    dry=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H);assert dry.status_code==200,dry.text
    d=dry.json()
    assert d['result']['summary']['new_rejections']==0
    assert d['result']['summary']['checksum_changed'] is False
    assert d['result']['summary']['changed_rows']==0
    assert c.get(f"/runs",headers=H).json()==[]
    # confirm
    conf=c.post(f"/dry-runs/{d['id']}/confirm",headers=H);assert conf.status_code==200,conf.text
    body=conf.json();assert body['activated'] is True
    m3=mapping(m['name']);assert m3['active_version']['id']==d['candidate_version_id']
    # retry
    again=c.post(f"/dry-runs/{d['id']}/confirm",headers=H);assert again.status_code==200
    assert again.json()['already_applied'] is True and again.json()['activated'] is False
    assert len([v for v in c.get(f"/mappings/{m['id']}",headers=H).json()['versions'] if v['state']=='active'])==1

def test_stale_after_batch_edit():
    m=mapping('异常隔离复核映射')
    data={'name':m['name'],'batch_id':m['batch_id'],'rules':m['rules'],'chunk_size':2,'note':''}
    c.put(f"/mappings/{m['id']}",json=data,headers=H)
    d=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    b=c.get('/batches',headers=H).json();b=next(x for x in b if x['id']==m['batch_id'])
    bdata={k:b[k] for k in ('name','source_file','description','rows')}
    bdata['description']='改了交接说明'
    c.put(f"/batches/{b['id']}",json=bdata,headers=H)
    v=c.get(f"/dry-runs/{d['id']}",headers=H).json()
    assert v['valid'] is False and any('批次' in x for x in v['stale_reasons'])
    r=c.post(f"/dry-runs/{d['id']}/confirm",headers=H);assert r.status_code==409
    # reverting the content keeps the bumped revision, so the trial stays stale
    bdata['description']=b['description']
    c.put(f"/batches/{b['id']}",json=bdata,headers=H)
    v=c.get(f"/dry-runs/{d['id']}",headers=H).json();assert v['valid'] is False
    r=c.post(f"/dry-runs/{d['id']}/confirm",headers=H);assert r.status_code==409

def test_rule_edit_after_dry_run_invalidates():
    m=mapping('空批次映射')
    data={'name':m['name'],'batch_id':m['batch_id'],'rules':m['rules'],'chunk_size':7,'note':''}
    c.put(f"/mappings/{m['id']}",json=data,headers=H)
    d=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    data['chunk_size']=5
    c.put(f"/mappings/{m['id']}",json=data,headers=H)
    v=c.get(f"/dry-runs/{d['id']}",headers=H).json();assert not v['valid']
    r=c.post(f"/dry-runs/{d['id']}/confirm",headers=H);assert r.status_code==409
