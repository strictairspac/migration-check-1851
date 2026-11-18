import sys
from fastapi.testclient import TestClient
from src.main import app
from src.config.database import Session
from src.models.run import Run,TargetRow
from src.services.migration import migrate,make_backup,key_digest
c=TestClient(app)
H={'Authorization':'Bearer '+c.post('/auth/login',json={'email':'operator@migration.local','password':'Migrate2026!'}).json()['token']}
AH={'Authorization':'Bearer '+c.post('/auth/login',json={'email':'admin@migration.local','password':'Migrate2026!'}).json()['token']}
def mp(n):return next(m for m in c.get('/mappings',headers=H).json() if m['name']==n)
def complete(run):
    with Session() as s:
        r=s.get(Run,run['id']);res=migrate(r.snapshot['batch']['rows'],r.snapshot['mapping']['rules'],r.snapshot['mapping']['chunk_size'])
        res['backup']=make_backup(res,r.id,r.snapshot['batch']['name'])
        for i,row in enumerate(res['accepted_rows']):s.add(TargetRow(run_id=r.id,ordinal=i,key_digest=key_digest(row),payload=row))
        r.result=res;r.status='completed';s.commit()
def test_old_backup_restores_after_switch_and_batch_edit():
    m=mp('检验结果标准映射')
    run=c.post('/runs',json={'name':'bk-run','mapping_id':m['id']},headers=H).json();complete(run)
    backup=c.get(f"/runs/{run['id']}/backup",headers=AH).json()
    # switch rules and edit the batch
    d={'name':m['name'],'batch_id':m['batch_id'],'rules':m['rules'],'chunk_size':33,'note':''}
    c.put(f"/mappings/{m['id']}",json=d,headers=H);m=mp(m['name'])
    dry=c.post(f"/mappings/{m['id']}/dry-runs",json={},headers=H).json()
    assert c.post(f"/dry-runs/{dry['id']}/confirm",headers=H).json()['activated']
    b=next(x for x in c.get('/batches',headers=H).json() if x['id']==m['batch_id'])
    bd={k:b[k] for k in ('name','source_file','description','rows')};bd['rows']=bd['rows'][:5]
    c.put(f"/batches/{b['id']}",json=bd,headers=H)
    r=c.post(f"/runs/{run['id']}/restore",json={'backup':backup},headers=AH)
    assert r.status_code==200,r.text
    assert r.json()['verified'] and r.json()['restored_count']==12
    # tampered backup is still refused
    bad={**backup,'rows':backup['rows'][:10]}
    r2=c.post(f"/runs/{run['id']}/restore",json={'backup':bad},headers=AH)
    assert r2.status_code==422
