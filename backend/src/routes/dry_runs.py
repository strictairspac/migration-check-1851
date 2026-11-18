from fastapi import APIRouter,Depends
from src.middlewares.auth import current,writer
from src.services import versioning
from src.services.audit import log
router=APIRouter()
@router.get('/dry-runs/{item_id}')
def detail(item_id:int,u=Depends(current)):return versioning.dry_run_detail(item_id)
@router.post('/dry-runs/{item_id}/confirm')
def confirm(item_id:int,u=Depends(writer)):
 r=versioning.confirm(item_id,u.email);log(u.email,'mapping.confirm',f'{item_id}:{"applied" if r["activated"] else "already"}');return r
