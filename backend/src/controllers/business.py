from src.services import batches,mappings,runs
from src.services.audit import log
def save_batch(data,user,item_id=None):
 row=batches.save(data,item_id);log(user.email,'batch.save',row['name']);return row
def save_mapping(data,user,item_id=None):
 row=mappings.save(data,user,item_id);log(user.email,'mapping.stage' if item_id else 'mapping.create',row['name']);return row
def start_run(data,user):
 row=runs.create(data);log(user.email,'run.queue',row['name']);return row
