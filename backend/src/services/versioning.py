"""Rule-set versioning: staged candidates, frozen dry runs, one-shot activation.

Invariants
----------
* Editing a mapping never mutates rules that a queued or running migration
  already accepted; runs take a frozen snapshot at acceptance time.
* A dry run is evidence only. It writes no target rows, no backup and no queue
  job.
* A dry run is valid only while the batch revision and both rule-set digests
  it recorded are unchanged, the candidate it compared is still the only
  candidate, and its base is still the version in use. Editing and reverting,
  or staging another candidate, voids it.
* A failed activation leaves the in-use version untouched.
* Activation happens under a lock on the mapping row, in one transaction, and
  is recorded by a unique dry_run_id receipt so retries never enable twice.
"""
from datetime import datetime,timezone
from fastapi import HTTPException
from src.models.mapping import Mapping,MappingVersion,DryRun,MappingActivation
from src.models.batch import Batch
from src.services.migration import digest,rule_digest,migrate
from src.utils.serialization import record

def batch_digest(rows):return digest(rows or [])

def ensure_baseline(s,mapping):
 """Make sure a mapping predating versioning has an in-use baseline version."""
 if mapping.active_version_id:
  version=s.get(MappingVersion,mapping.active_version_id)
  if version:return version
 last=s.query(MappingVersion).filter_by(mapping_id=mapping.id).order_by(MappingVersion.version_no.desc()).first()
 version=MappingVersion(mapping_id=mapping.id,version_no=(last.version_no if last else 0)+1,rules=mapping.rules,chunk_size=mapping.chunk_size,note=mapping.note,rule_digest=rule_digest(mapping.rules,mapping.chunk_size),state='active',batch_revision=None,created_by='system')
 s.add(version);s.flush();mapping.active_version_id=version.id;s.flush();return version

def ensure_all_baselines():
 """Backfill baselines for mappings created before rule versioning existed."""
 from src.config.database import Session
 with Session() as s:
  for mapping in s.query(Mapping).filter(Mapping.active_version_id.is_(None)).all():ensure_baseline(s,mapping)
  s.commit()

def _walk(s,mapping,batch):
 """Read-only resolution: never stages or mutates a version row."""
 version=s.get(MappingVersion,mapping.active_version_id) if mapping.active_version_id else None
 if not version:version=s.query(MappingVersion).filter_by(mapping_id=mapping.id).order_by(MappingVersion.version_no).first()
 revision=getattr(batch,'revision',1) or 1
 seen=set()
 while version and version.id not in seen:
  seen.add(version.id)
  if version.batch_revision is None:return version
  if version.batch_revision==revision and (version.batch_id is None or version.batch_id==batch.id):return version
  version=s.get(MappingVersion,version.parent_version_id) if version.parent_version_id else None
 return s.query(MappingVersion).filter_by(mapping_id=mapping.id).order_by(MappingVersion.version_no).first()

def resolve_for_batch(s,mapping,batch):
 """Return the version that applies to this batch revision.

 A version activated for one batch revision does not leak to a later edit of
 the batch: resolution walks parents until one is either the baseline or was
 dry-run against the current batch revision.
 """
 ensure_baseline(s,mapping)
 return _walk(s,mapping,batch)

def _stale_reasons(s,dry,mapping,batch):
 reasons=[]
 if not mapping:return ['映射不存在']
 if mapping.batch_id!=dry.batch_id:reasons.append('映射已改绑批次')
 if batch:
  try:current=_walk(s,mapping,batch)
  except Exception:current=None
  if not current or current.id!=dry.base_version_id:reasons.append('该批次当前在用的旧版已不是试跑时的旧版')
 if not batch:reasons.append('批次已删除')
 elif batch.revision!=dry.batch_revision:reasons.append('批次在试跑后被编辑')
 elif batch_digest(batch.rows)!=dry.batch_digest:reasons.append('批次内容与试跑时不一致')
 base=s.get(MappingVersion,dry.base_version_id)
 cand=s.get(MappingVersion,dry.candidate_version_id)
 if not base or not cand:reasons.append('试跑引用的规则版本不存在')
 else:
  if base.rule_digest!=dry.base_rule_digest:reasons.append('旧版规则内容与试跑时不一致')
  if cand.rule_digest!=dry.candidate_rule_digest:reasons.append('候选规则内容与试跑时不一致')
  if cand.mapping_id!=mapping.id:reasons.append('候选不属于该映射')
  if cand.id==mapping.active_version_id:
   if cand.state!='active':reasons.append('候选状态异常')
  elif cand.state!='candidate':reasons.append('候选版本已不可用')
  else:
   # Editing then reverting stages a new candidate version; the earlier trial
   # compared a superseded candidate and must not be reused.
   newer=s.query(MappingVersion).filter(MappingVersion.mapping_id==mapping.id,MappingVersion.version_no>cand.version_no,MappingVersion.state.in_(('candidate','active'))).first()
   if newer:reasons.append('试跑后规则又产生过新版本')
 return reasons

def dry_run_detail(dry_id):
 from src.config.database import Session
 with Session() as s:
  dry=s.get(DryRun,dry_id)
  if not dry:raise HTTPException(404,'未找到试跑记录')
  mapping=s.get(Mapping,dry.mapping_id);batch=s.get(Batch,dry.batch_id)
  receipt=s.query(MappingActivation).filter_by(dry_run_id=dry.id).first()
  data=record(dry)
  reasons=_stale_reasons(s,dry,mapping,batch)
  # Once applied the trial is history, not a pending decision: report it as
  # applied instead of "stale", which would suggest it still needed action.
  data['applied']=bool(receipt)
  data['valid']=bool(receipt) or not reasons;data['stale_reasons']=[] if receipt else reasons
  data['activation']=record(receipt) if receipt else None
  return data

def list_dry_runs(mapping_id=None,limit=20):
 from src.config.database import Session
 with Session() as s:
  q=s.query(DryRun)
  if mapping_id:q=q.filter_by(mapping_id=mapping_id)
  items=[]
  for dry in q.order_by(DryRun.id.desc()).limit(limit).all():
   mapping=s.get(Mapping,dry.mapping_id);batch=s.get(Batch,dry.batch_id)
   data=record(dry);reasons=_stale_reasons(s,dry,mapping,batch)
   data['result']={'summary':dry.result.get('summary'),'batch':dry.result.get('batch'),'base':dry.result.get('base'),'candidate':dry.result.get('candidate')}
   receipt=s.query(MappingActivation).filter_by(dry_run_id=dry.id).first()
   data['applied']=bool(receipt)
   data['valid']=bool(receipt) or not reasons;data['stale_reasons']=[] if receipt else reasons
   data['activation']=record(receipt) if receipt else None
   items.append(data)
  return items

def _compare(base_result,candidate_result):
 base={o['row_number']:o for o in base_result['outcomes']}
 cand={o['row_number']:o for o in candidate_result['outcomes']}
 compared=[];new_rejections=[];resolved=[];changed=[];key_collisions=[];new_key_collisions=[];reason_changes=[]
 for row_number in sorted(base):
  b=base[row_number];c=cand.get(row_number)
  if not c:continue
  source=b.get('source',c.get('source'))
  entry={'row_number':row_number,'source':source,'base_status':b['status'],'candidate_status':c['status']}
  if b['status']=='accepted' and c['status']=='accepted':
   diff=[field for field in ('sample_code','test_name','result_value','unit','measured_at') if b.get('target',{}).get(field)!=c.get('target',{}).get(field)]
   entry['change']='changed' if diff else 'unchanged'
   if diff:
    entry['changed_fields']=diff;entry['base_target']=b.get('target');entry['candidate_target']=c.get('target');changed.append(entry)
  elif b['status']=='accepted' and c['status']=='rejected':
   entry['change']='new_rejection';entry['candidate_reason']=c.get('reason');entry['base_target']=b.get('target')
   if str(c.get('reason','')).startswith('duplicate_natural_key'):
    entry['key_collision']=True;new_key_collisions.append(entry)
   new_rejections.append(entry)
  elif b['status']=='rejected' and c['status']=='accepted':
   entry['change']='resolved';entry['base_reason']=b.get('reason');entry['candidate_target']=c.get('target');resolved.append(entry)
  else:
   entry['change']='both_rejected' if b.get('reason')==c.get('reason') else 'reason_changed'
   entry['base_reason']=b.get('reason');entry['candidate_reason']=c.get('reason')
   if entry['change']=='reason_changed':reason_changes.append(entry)
   if str(c.get('reason','')).startswith('duplicate_natural_key') and not str(b.get('reason','')).startswith('duplicate_natural_key'):
    entry['key_collision']=True;key_collisions.append(entry)
  if entry.get('key_collision'):key_collisions.append(entry)
  compared.append(entry)
 # De-duplicate collision evidence while keeping row order.
 unique=[];seen=set()
 for entry in key_collisions:
  if entry['row_number'] not in seen:seen.add(entry['row_number']);unique.append(entry)
 key_collisions=unique
 summary={'source_count':len(compared),'base_accepted':base_result['accepted_count'],'candidate_accepted':candidate_result['accepted_count'],'accepted_delta':candidate_result['accepted_count']-base_result['accepted_count'],'base_rejected':base_result['rejected_count'],'candidate_rejected':candidate_result['rejected_count'],'new_rejections':len(new_rejections),'resolved_rejections':len(resolved),'changed_rows':len(changed),'unchanged_rows':sum(1 for e in compared if e['change']=='unchanged'),'key_collisions':len(key_collisions),'new_key_collisions':len(new_key_collisions),'reason_changes':len(reason_changes),'checksum_changed':base_result['checksum']!=candidate_result['checksum']}
 return summary,compared,new_rejections,resolved,changed,key_collisions,reason_changes

def create_dry_run(mapping_id,candidate_version_id,actor):
 from src.config.database import Session
 with Session() as s:
  mapping=s.query(Mapping).filter_by(id=mapping_id).with_for_update().first()
  if not mapping:raise HTTPException(404,'未找到字段映射')
  batch=s.get(Batch,mapping.batch_id)
  if not batch:raise HTTPException(404,'未找到迁移批次')
  base=resolve_for_batch(s,mapping,batch)
  cand=s.get(MappingVersion,candidate_version_id) if candidate_version_id else s.query(MappingVersion).filter_by(mapping_id=mapping.id,state='candidate').order_by(MappingVersion.version_no.desc()).first()
  if not cand:raise HTTPException(409,'没有待确认的候选规则，请先编辑映射')
  if cand.mapping_id!=mapping.id:raise HTTPException(400,'候选版本不属于该映射')
  if cand.state!='candidate':raise HTTPException(409,'只有候选规则可以试跑')
  rows=batch.rows or []
  base_result=migrate(rows,base.rules,base.chunk_size,trace=True)
  cand_result=migrate(rows,cand.rules,cand.chunk_size,trace=True)
  summary,compared,new_rejections,resolved,changed,key_collisions,reason_changes=_compare(base_result,cand_result)
  result={'batch':{'id':batch.id,'name':batch.name,'revision':batch.revision,'digest':batch_digest(rows),'source_count':len(rows)},'base':{'version_id':base.id,'version_no':base.version_no,'rule_digest':base.rule_digest,'chunk_size':base.chunk_size,'checksum':base_result['checksum'],'accepted_count':base_result['accepted_count'],'rejected_count':base_result['rejected_count'],'rejected_rows':base_result['rejected_rows']},'candidate':{'version_id':cand.id,'version_no':cand.version_no,'rule_digest':cand.rule_digest,'chunk_size':cand.chunk_size,'checksum':cand_result['checksum'],'accepted_count':cand_result['accepted_count'],'rejected_count':cand_result['rejected_count'],'rejected_rows':cand_result['rejected_rows']},'summary':summary,'rows':compared,'new_rejections':new_rejections,'resolved':resolved,'changed':changed,'key_collisions':key_collisions,'reason_changes':reason_changes}
  dry=DryRun(mapping_id=mapping.id,batch_id=batch.id,base_version_id=base.id,candidate_version_id=cand.id,batch_revision=batch.revision,batch_digest=result['batch']['digest'],base_rule_digest=base.rule_digest,candidate_rule_digest=cand.rule_digest,result=result,created_by=actor)
  # Record the batch revision the resolver returned (it can differ from the
  # edit counter when the mapping was moved between batches).
  s.add(dry);s.commit();s.refresh(dry);return record(dry)

def confirm(dry_id,actor):
 from src.config.database import Session
 with Session() as s:
  dry=s.get(DryRun,dry_id)
  if not dry:raise HTTPException(404,'未找到试跑记录')
  mapping=s.query(Mapping).filter_by(id=dry.mapping_id).with_for_update().first()
  if not mapping:raise HTTPException(404,'未找到字段映射')
  receipt=s.query(MappingActivation).filter_by(dry_run_id=dry.id).first()
  if receipt:
   # Retry of an already applied confirmation: report it, never enable twice.
   return {'activated':False,'already_applied':True,'activation':record(receipt),'mapping_id':mapping.id,'active_version_id':mapping.active_version_id}
  cand0=s.get(MappingVersion,dry.candidate_version_id)
  if cand0 and cand0.state=='active' and mapping.active_version_id==cand0.id:
   # Already in use (the receipt row may be missing on legacy data); enabling
   # again would create a second activation for the same candidate.
   return {'activated':False,'already_applied':True,'activation':None,'mapping_id':mapping.id,'active_version_id':cand0.id}
  # Lock the batch row too: a concurrent batch edit blocks here instead of
  # slipping between the validity check and the pointer swap.
  batch=s.query(Batch).filter_by(id=dry.batch_id).with_for_update().first()
  reasons=_stale_reasons(s,dry,mapping,batch)
  if reasons:raise HTTPException(409,'试跑已失效：'+'；'.join(reasons)+'。请重新试跑后再确认')
  cand=s.get(MappingVersion,dry.candidate_version_id);base=s.get(MappingVersion,dry.base_version_id)
  if not cand or cand.state!='candidate':raise HTTPException(409,'候选版本已不可用，请重新试跑')
  now=datetime.now(timezone.utc)
  receipt=MappingActivation(mapping_id=mapping.id,dry_run_id=dry.id,from_version_id=base.id,to_version_id=cand.id,actor=actor)
  previous_pointer=mapping.active_version_id
  try:
   # Compare-and-swap on the in-use pointer. Two candidates confirmed at the
   # same time both pass the pre-check, but only the transaction whose pointer
   # update still sees the pointer it read may proceed.
   swapped=s.query(Mapping).filter(Mapping.id==mapping.id,Mapping.active_version_id==previous_pointer).update({'active_version_id':cand.id,'rules':cand.rules,'chunk_size':cand.chunk_size,'note':cand.note},synchronize_session=False)
   if swapped!=1:
    s.rollback()
    other=s.query(MappingActivation).filter_by(dry_run_id=dry.id).first()
    current=s.get(Mapping,mapping.id)
    if other:return {'activated':False,'already_applied':True,'activation':record(other),'mapping_id':mapping.id,'active_version_id':current.active_version_id}
    raise HTTPException(409,'另一份候选已生效，本次未切换；在用版本保持不变。请重新试跑')
   # Retire every in-use row first so the partial unique index on
   # (mapping_id) WHERE state='active' never sees two rows. A version bound to
   # an older batch revision can still be the pointer while this dry run's base
   # is the baseline; both must go before the candidate is activated.
   s.query(MappingVersion).filter(MappingVersion.mapping_id==mapping.id,MappingVersion.state=='active',MappingVersion.id!=cand.id).update({'state':'archived','activated_at':now},synchronize_session=False)
   s.flush()
   s.query(MappingVersion).filter(MappingVersion.id==cand.id).update({'state':'active','activated_at':now,'batch_id':dry.batch_id,'batch_revision':dry.batch_revision,'parent_version_id':base.id},synchronize_session=False)
   # Any other staged candidate is now older than the in-use version; retire
   # it so the mapping has one clear pending state (and its trials stay dead).
   s.query(MappingVersion).filter(MappingVersion.mapping_id==mapping.id,MappingVersion.state=='candidate',MappingVersion.id!=cand.id).update({'state':'superseded'},synchronize_session=False)
   s.flush()
   s.add(receipt);s.commit()
  except HTTPException:raise
  except Exception:
   s.rollback()
   existing=None
   with Session() as s2:
    existing=s2.query(MappingActivation).filter_by(dry_run_id=dry.id).first();current=s2.get(Mapping,mapping.id)
   if existing:return {'activated':False,'already_applied':True,'activation':record(existing),'mapping_id':mapping.id,'active_version_id':current.active_version_id if current else None}
   raise HTTPException(409,'切换失败，在用版本未改变，请重试')
  s.refresh(receipt)
  return {'activated':True,'already_applied':False,'activation':record(receipt),'mapping_id':mapping.id,'active_version_id':cand.id,'applies_to_batch_revision':cand.batch_revision}
