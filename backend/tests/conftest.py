import os,sys,tempfile
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['JWT_SECRET']='test-secret'
os.environ['REDIS_URL']='redis://localhost:6399/0'
db=tempfile.mktemp(suffix='.db')
os.environ['DATABASE_URL']='sqlite:///'+db
import src.services.runs as _runs
class _Q:
 def __init__(self):self.items=[]
 def rpush(self,k,v):self.items.append((k,v))
 def blpop(self,*a,**k):return None
_q=_Q();_runs.queue=_q
import pytest
@pytest.fixture(autouse=True)
def fresh():
 from src.config.database import Base,engine
 Base.metadata.drop_all(engine)
 _q.items.clear()
 from scripts.seed_demo import seed
 seed()
 yield
from scripts.seed_demo import seed as _seed
_seed()
