from fastapi.testclient import TestClient
from src.main import app
c=TestClient(app)
H={'Authorization':'Bearer '+c.post('/auth/login',json={'email':'operator@migration.local','password':'Migrate2026!'}).json()['token']}
AH={'Authorization':'Bearer '+c.post('/auth/login',json={'email':'admin@migration.local','password':'Migrate2026!'}).json()['token']}
def mp(name):return next(m for m in c.get('/mappings',headers=H).json() if m['name']==name)
def put(m,**kw):
 d={'name':m['name'],'batch_id':m['batch_id'],'rules':m['rules'],'chunk_size':m['chunk_size'],'note':m['note']};d.update(kw)
 return c.put(f"/mappings/{m['id']}",json=d,headers=H)

def test_key_collision_and_source_swap():
    m=mp('检验结果标准映射')
    rules=[dict(r) for r in m['rules']]
    rules[1]['source']='委托号'  # test_name now equals sample_code -> still unique per row
    put(m,rules=rules)
    d=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    s=d['result']['summary']
    assert s['changed_rows']==12
    # A constant natural key across rows: every later row collides.
    m=mp('检验结果标准映射')
    rules=[dict(r) for r in m['rules']]
    rules[0]['source']='单位'
    put(m,rules=rules)
    d=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    s=d['result']['summary']
    assert s['new_key_collisions']==11, s
    assert s['new_rejections']==11
    assert len(d['result']['key_collisions'])==11

def test_dry_run_writes_nothing():
    before_runs=len(c.get('/runs',headers=H).json())
    m=mp('空批次映射')
    put(m,chunk_size=8)
    m=mp('空批次映射')
    d=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    assert 'backup' not in d['result']
    assert len(c.get('/runs',headers=H).json())==before_runs

def test_restore_old_backup_after_switch():
    # simulate completed run + backup, then switch mapping; restore must work
    m=mp('检验结果标准映射')
    run=c.post('/runs',json={'name':'restore-run','mapping_id':m['id']},headers=H).json()
    # worker normally does this; emulate directly through service migrate
    from src.services.migration import migrate,make_backup,key_digest
    from src.config.database import Session
    from src.models.run import Run,TargetRow
    with Session() as s:
        r=s.get(Run,run['id']);res=migrate(r.snapshot['batch']['rows'],r.snapshot['mapping']['rules'],r.snapshot['mapping']['chunk_size'])
        res['backup']=make_backup(res,r.id,r.snapshot['batch']['name'])
        for i,row in enumerate(res['accepted_rows']):s.add(TargetRow(run_id=r.id,ordinal=i,key_digest=key_digest(row),payload=row))
        r.result=res;r.status='completed';s.commit()
    backup=c.get(f"/runs/{run['id']}/backup",headers=AH).json()
    put(m,chunk_size=10)
    m=mp('检验结果标准映射');d=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    assert c.post(f"/dry-runs/{d['id']}/confirm",headers=H).json()['activated']
    r=c.post(f"/runs/{run['id']}/restore",json={'backup':backup},headers=AH)
    assert r.status_code==200,r.text
    assert r.json()['verified']
