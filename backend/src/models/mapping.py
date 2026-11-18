from sqlalchemy import Column,Integer,String,JSON,ForeignKey,UniqueConstraint,DateTime,func,Index,text
from src.config.database import Base
class Mapping(Base):
 __tablename__='mappings'
 id=Column(Integer,primary_key=True)
 name=Column(String(120),unique=True,nullable=False)
 batch_id=Column(Integer,ForeignKey('batches.id'),nullable=False)
 # Mirror of the active version, kept for compatibility with older snapshots.
 rules=Column(JSON,nullable=False)
 chunk_size=Column(Integer,nullable=False,default=50)
 note=Column(String(500),nullable=False,default='')
 # App-managed pointer to the version currently in use. Not a FK to avoid a
 # circular dependency between mappings and mapping_versions.
 active_version_id=Column(Integer,nullable=True)

class MappingVersion(Base):
 """Immutable rule-set revision.

 Editing a mapping never mutates rules already in use; it appends a candidate
 version. A candidate becomes active only by confirming a still-valid
 old-vs-new dry run.
 """
 __tablename__='mapping_versions'
 # At most one in-use row per mapping, enforced by the database as a final
 # guard behind the compare-and-swap activation.
 __table_args__=(UniqueConstraint('mapping_id','version_no'),Index('ux_mapping_versions_active','mapping_id',unique=True,postgresql_where=text("state='active'"),sqlite_where=text("state='active'")))
 id=Column(Integer,primary_key=True)
 mapping_id=Column(Integer,ForeignKey('mappings.id'),nullable=False,index=True)
 version_no=Column(Integer,nullable=False)
 rules=Column(JSON,nullable=False)
 chunk_size=Column(Integer,nullable=False,default=50)
 note=Column(String(500),nullable=False,default='')
 rule_digest=Column(String(64),nullable=False)
 state=Column(String(20),nullable=False,default='candidate')
 # Batch and revision this version was dry-run and confirmed against. NULL
 # batch_revision means the baseline, which applies to every batch revision.
 batch_id=Column(Integer,nullable=True)
 batch_revision=Column(Integer,nullable=True)
 parent_version_id=Column(Integer,nullable=True)
 created_by=Column(String(120),nullable=False,default='system')
 created_at=Column(DateTime,server_default=func.now())
 activated_at=Column(DateTime,nullable=True)

class DryRun(Base):
 """Frozen old-vs-new comparison for one batch revision and one rule edit.

 It only records evidence; it never writes target rows, backups or queue jobs.
 """
 __tablename__='dry_runs'
 id=Column(Integer,primary_key=True)
 mapping_id=Column(Integer,ForeignKey('mappings.id'),nullable=False,index=True)
 batch_id=Column(Integer,ForeignKey('batches.id'),nullable=False)
 base_version_id=Column(Integer,nullable=False)
 candidate_version_id=Column(Integer,nullable=False)
 batch_revision=Column(Integer,nullable=False)
 batch_digest=Column(String(64),nullable=False)
 base_rule_digest=Column(String(64),nullable=False)
 candidate_rule_digest=Column(String(64),nullable=False)
 result=Column(JSON,nullable=False)
 created_by=Column(String(120),nullable=False,default='system')
 created_at=Column(DateTime,server_default=func.now())

class MappingActivation(Base):
 """One-shot activation receipt; the unique dry_run_id makes retries idempotent."""
 __tablename__='mapping_activations'
 __table_args__=(UniqueConstraint('dry_run_id'),)
 id=Column(Integer,primary_key=True)
 mapping_id=Column(Integer,ForeignKey('mappings.id'),nullable=False)
 dry_run_id=Column(Integer,ForeignKey('dry_runs.id'),nullable=False)
 from_version_id=Column(Integer,nullable=False)
 to_version_id=Column(Integer,nullable=False)
 actor=Column(String(120),nullable=False,default='system')
 created_at=Column(DateTime,server_default=func.now())
