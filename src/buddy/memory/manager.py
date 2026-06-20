import json,logging,threading
from .models import UserProfile
from .store import MemoryStore
logger=logging.getLogger(__name__)
class MemoryManager:
 def __init__(s,db="./buddy_memory.db"):s.store=MemoryStore(db);s._lk=threading.Lock()
 def load(s,uid):d=s.store.get_profile(uid);return UserProfile(user_id=uid) if d is None else UserProfile(**d)
 def save(s,p):
  with s._lk:s.store.upsert_profile(p.user_id,p.model_dump())
 def update_async(s,uid,um,rp,pe,pr):threading.Thread(target=s._uw,args=(uid,um,rp,pe,pr),daemon=True).start()
 def get_recent_history(s,uid,lm=5):
  eps=s.store.get_recent_episodes(uid,lm);h=[]
  for e in eps:h.append({"role":"user","content":e["user_msg"]});h.append({"role":"assistant","content":e["reply"]})
  return h
 def _uw(s,uid,um,rp,pe,pr):
  try:
   s.store.append_episode(uid,um,rp,pe)
   ex=s._ex(um,rp);ch=False
   nm=ex.get("user_name","")
   if nm and pr.name=="unknown":pr.name=nm;ch=True
   lv=ex.get("detected_level","unknown")
   if lv!="unknown" and lv!=pr.level:pr.level=lv;ch=True
   for t in ex.get("topics_mentioned",[]):
    if t and t not in pr.interests:pr.interests.append(t);ch=True
   pr.session_count+=1;s.save(pr)
  except Exception as e:print(f"[memory] Update failed: {e}")
 def _ex(s,um,rp):
  from ..core import generate,get_model
  from ..config import load
  c=load()
  if c.mock:return {}
  from vllm import SamplingParams
  _,tk=get_model()
  pr=json.dumps({"user_msg":um,"reply":rp})
  ms=[{"role":"system","content":"Extract user info. Return JSON with: detected_level, topics_mentioned, user_name."},{"role":"user","content":pr}]
  p=tk.apply_chat_template(ms,tokenize=False,add_generation_prompt=True)
  try:
   raw=generate(p,SamplingParams(temperature=0.1,max_tokens=150))
   if "```" in raw:raw=raw.split("```")[1]
   if raw.startswith("json"):raw=raw[4:]
   return json.loads(raw.strip())
  except:return {}
