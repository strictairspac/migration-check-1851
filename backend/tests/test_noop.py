import sys
from fastapi.testclient import TestClient
from src.main import app
c=TestClient(app)
H={'Authorization':'Bearer '+c.post('/auth/login',json={'email':'operator@migration.local','password':'Migrate2026!'}).json()['token']}
def mp(n):return next(m for m in c.get('/mappings',headers=H).json() if m['name']==n)
def test_noop_batch_save_keeps_trial():
    m=mp('检验结果标准映射')
    c.put(f"/mappings/{m['id']}",json={'name':m['name'],'batch_id':m['batch_id'],'rules':m['rules'],'chunk_size':19,'note':''},headers=H)
    m=mp('检验结果标准映射');d=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    b=next(x for x in c.get('/batches',headers=H).json() if x['id']==m['batch_id'])
    same={k:b[k] for k in ('name','source_file','description','rows')}
    c.put(f"/batches/{b['id']}",json=same,headers=H)
    v=c.get(f"/dry-runs/{d['id']}",headers=H).json();assert v['valid'],v['stale_reasons']
def test_noop_mapping_save_keeps_trial():
    m=mp('空批次映射')
    d0={'name':m['name'],'batch_id':m['batch_id'],'rules':m['rules'],'chunk_size':23,'note':''}
    c.put(f"/mappings/{m['id']}",json=d0,headers=H)
    m=mp('空批次映射');d=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    c.put(f"/mappings/{m['id']}",json=d0,headers=H)
    v=c.get(f"/dry-runs/{d['id']}",headers=H).json();assert v['valid'],v['stale_reasons']
