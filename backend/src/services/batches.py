from fastapi import HTTPException
from src.config.database import Session
from src.models.batch import Batch
from src.utils.serialization import record

def list_items():
 with Session() as s:return [record(r) for r in s.query(Batch).order_by(Batch.id.desc()).all()]
def save(data,item_id=None):
 with Session() as s:
  row=s.get(Batch,item_id) if item_id else Batch()
  if not row:raise HTTPException(404,'未找到记录')
  values=data.model_dump()
  # Any real edit bumps the revision; a no-op save keeps an existing dry run
  # usable. An edit followed by reverting still bumps, so the old trial stays
  # invalid.
  changed=item_id is not None and any(getattr(row,k)!=v for k,v in values.items())
  for k,v in values.items():setattr(row,k,v)
  if changed:row.revision=(row.revision or 1)+1
  s.add(row);s.commit();s.refresh(row);return record(row)
