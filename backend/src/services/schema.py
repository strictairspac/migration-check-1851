"""Idempotent metadata upgrades for volumes created before rule versioning."""
from sqlalchemy import inspect,text
from src.config.database import Base,engine
from src.models.mapping import Mapping
from src.services.versioning import ensure_all_baselines

COLUMNS=(('batches','revision','INTEGER NOT NULL DEFAULT 1'),('mappings','active_version_id','INTEGER'),('runs','mapping_version_id','INTEGER'))

def ensure_schema():
 Base.metadata.create_all(engine)
 inspector=inspect(engine)
 with engine.begin() as conn:
  for table,column,ddl in COLUMNS:
   if not inspector.has_table(table):continue
   existing={c['name'] for c in inspector.get_columns(table)}
   if column not in existing:conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}'))
 ensure_all_baselines()
