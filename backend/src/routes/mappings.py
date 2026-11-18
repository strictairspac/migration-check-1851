from fastapi import APIRouter,Depends
from pydantic import BaseModel
from src.middlewares.auth import current,writer
from src.schemas.business import MappingInput
from src.services import mappings,versioning
from src.services.audit import log
from src.controllers.business import save_mapping
router=APIRouter()
class DryRunInput(BaseModel):candidate_version_id:int|None=None
@router.get('/mappings')
def listing(u=Depends(current)):return mappings.list_items()
@router.get('/mappings/{item_id}')
def detail(item_id:int,u=Depends(current)):return mappings.detail(item_id)
@router.post('/mappings')
def create(data:MappingInput,u=Depends(writer)):return save_mapping(data,u)
@router.put('/mappings/{item_id}')
def update(item_id:int,data:MappingInput,u=Depends(writer)):return save_mapping(data,u,item_id)
@router.get('/mappings/{item_id}/dry-runs')
def dry_runs(item_id:int,u=Depends(current)):return versioning.list_dry_runs(item_id)
@router.post('/mappings/{item_id}/dry-runs')
def create_dry_run(item_id:int,data:DryRunInput|None=None,u=Depends(writer)):
 r=versioning.create_dry_run(item_id,data.candidate_version_id if data else None,u.email)
 log(u.email,'mapping.trial',f"{item_id}:{r['id']}")
 return r
