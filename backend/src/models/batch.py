from sqlalchemy import Column,Integer,String,JSON
from src.config.database import Base
class Batch(Base):
 __tablename__='batches'
 id=Column(Integer,primary_key=True)
 name=Column(String(120),unique=True,nullable=False)
 source_file=Column(String(160),nullable=False)
 description=Column(String(500),nullable=False,default='')
 rows=Column(JSON,nullable=False)
 # Monotonic edit counter. Any save increments it, including a save that
 # restores the previous content, so an earlier dry run can never be revived.
 revision=Column(Integer,nullable=False,default=1,server_default='1')
