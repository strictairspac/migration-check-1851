from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from src.config.database import Session
from src.models.mapping import Mapping,MappingVersion
from src.models.batch import Batch
from src.services.migration import rule_digest
from src.services.versioning import ensure_baseline,resolve_for_batch
from src.utils.serialization import record

def list_items():
 with Session() as s:
  items=[]
  for r in s.query(Mapping).order_by(Mapping.id.desc()).all():
   data=record(r);active=s.get(MappingVersion,r.active_version_id) if r.active_version_id else None
   pending=s.query(MappingVersion).filter_by(mapping_id=r.id,state='candidate').order_by(MappingVersion.version_no.desc()).first()
   data['active_version']=record(active) if active else None
   data['pending_version']=record(pending) if pending else None
   items.append(data)
  return items

def detail(item_id):
 with Session() as s:
  r=s.get(Mapping,item_id)
  if not r:raise HTTPException(404,'未找到记录')
  versions=s.query(MappingVersion).filter_by(mapping_id=item_id).order_by(MappingVersion.version_no.desc()).all()
  data=record(r);data['versions']=[record(v) for v in versions]
  return data

def _next_no(s,mapping_id):
 last=s.query(MappingVersion).filter_by(mapping_id=mapping_id).order_by(MappingVersion.version_no.desc()).first()
 return (last.version_no if last else 0)+1

def save(data,user,item_id=None):
 """Create a mapping (v1 active) or stage a candidate version (never activate)."""
 with Session() as s:
  if not s.get(Batch,data.batch_id):raise HTTPException(404,'未找到迁移批次')
  if item_id:
   row=s.query(Mapping).filter_by(id=item_id).with_for_update().first()
   if not row:raise HTTPException(404,'未找到记录')
   if any(v.name==data.name and v.id!=row.id for v in s.query(Mapping).filter_by(name=data.name)):raise HTTPException(409,'名称已存在')
   digest_value=rule_digest(data.rules,data.chunk_size)
   # Legacy mappings may predate versioning; give them an in-use baseline
   # before numbering the candidate so version numbers stay unique.
   ensure_baseline(s,row)
   # "In use" is judged for the batch revision being edited: a rule set that
   # is active for an older revision can still be staged for the current one.
   active=resolve_for_batch(s,row,s.get(Batch,data.batch_id))
   pending=s.query(MappingVersion).filter_by(mapping_id=row.id,state='candidate').order_by(MappingVersion.version_no.desc()).first()
   if pending and pending.rule_digest==digest_value:
    # Saving the identical candidate must not invalidate its dry run.
    row.name=data.name;row.batch_id=data.batch_id;row.note=data.note
    s.commit();s.refresh(row);return record(row)
   if active and active.rule_digest==digest_value:
    # Editing back to the in-use rules cancels the staged candidate: withdraw
    # it so no dry run taken against it can ever be confirmed.
    row.name=data.name;row.batch_id=data.batch_id;row.note=data.note
    if pending:
     for older in s.query(MappingVersion).filter_by(mapping_id=row.id,state='candidate').all():older.state='withdrawn'
    s.commit();s.refresh(row);return record(row)
   version=MappingVersion(mapping_id=row.id,version_no=_next_no(s,row.id),rules=data.rules,chunk_size=data.chunk_size,note=data.note,rule_digest=digest_value,state='candidate',created_by=user.email,parent_version_id=row.active_version_id)
   row.name=data.name;row.batch_id=data.batch_id;row.note=data.note
   s.add(version)
   try:s.commit()
   except IntegrityError:raise HTTPException(409,'名称已存在或并发编辑冲突，请刷新后重试')
   s.refresh(row);return record(row)
  if s.query(Mapping).filter_by(name=data.name).first():raise HTTPException(409,'名称已存在')
  row=Mapping(name=data.name,batch_id=data.batch_id,rules=data.rules,chunk_size=data.chunk_size,note=data.note)
  s.add(row);s.flush()
  digest_value=rule_digest(data.rules,data.chunk_size)
  version=MappingVersion(mapping_id=row.id,version_no=1,rules=data.rules,chunk_size=data.chunk_size,note=data.note,rule_digest=digest_value,state='active',created_by=user.email)
  s.add(version);s.flush();row.active_version_id=version.id
  s.commit();s.refresh(row);return record(row)
