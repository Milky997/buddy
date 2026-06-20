import asyncio,io,json,logging,os as _os,time as _time
import numpy as np
from contextlib import asynccontextmanager
from fastapi import FastAPI,WebSocket,WebSocketDisconnect,UploadFile,File
from fastapi.responses import JSONResponse,StreamingResponse,HTMLResponse
from . import config as cfgmod,core,asr,prompt,sentence_agg
from .memory import MemoryManager
from .vad import VAD
logging.basicConfig(level=logging.INFO,format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
_cfg=cfgmod.load()
_mem=MemoryManager(db_path=_cfg.memory_db_path)
_SESSIONS={}
LOG=logging.getLogger("buddy")
@asynccontextmanager
async def lifespan(app):core.warmup();yield
app=FastAPI(lifespan=lifespan)
def _ses(sid):
 if sid not in _SESSIONS:
  p=_mem.load(sid)
  _SESSIONS[sid]={"profile":p,"persona":prompt.DEFAULT_PERSONA,"history":_mem.get_recent_history(sid,limit=5)}
 return _SESSIONS[sid]
@app.post("/set_persona")
async def set_persona(session_id="default",persona_key=None):
 if persona_key is None:persona_key=prompt.DEFAULT_PERSONA
 if persona_key not in prompt.PERSONAS:return JSONResponse(400,content={"error":"unknown persona"})
 s=_ses(session_id);s["persona"]=persona_key;s["history"]=_mem.get_recent_history(session_id,limit=5)
 LOG.info("Persona: %s -> %s",session_id,persona_key);return {"ok":True,"persona":persona_key}
async def _proc_audio(text,s,pk,sid,ws):
 t0=_time.time()
 await ws.send_text(json.dumps({"type":"transcript","text":text}))
 LOG.info("[%s] ASR: %s",sid,text)
 full=_do_llm(text,s,pk,sid)
 LOG.info("[%s] LLM: %s",sid,full[:60])
 await ws.send_text(json.dumps({"type":"reply","text":full,"latency_ms":int((_time.time()-t0)*1000)}))
 from .tts.kokoro import get_tts as get_kokoro
 tts=get_kokoro();voice_id=prompt.PERSONAS[pk]["voice"];agg=sentence_agg.SentenceAggregator()
 for sent in agg.split_sentences(full):
  audio=tts.generate(sent,sid=voice_id,speed=1.0)
  pcm=np.clip(np.array(audio.samples)*32768,-32768,32767).astype(np.int16).tobytes()
  await ws.send_bytes(pcm)
def _do_llm(text,s,pk,sid):
 profile=s["profile"];history=s["history"]
 pd={"name":profile.name,"level":profile.level,"interests":profile.interests,"session_count":profile.session_count}
 skills=prompt.pick_skills(pd);sp=prompt.build_system(pd,skills,pk)
 history.append({"role":"user","content":text})
 _,tokenizer=core.get_model()
 from vllm import SamplingParams
 msgs=[{"role":"system","content":sp}]+history
 p=tokenizer.apply_chat_template(msgs,tokenize=False,add_generation_prompt=True)
 full=core.generate(p,SamplingParams(temperature=prompt.PERSONAS[pk]["temperature"],max_tokens=_cfg.llm.max_tokens))
 history.append({"role":"assistant","content":full})
 _mem.update_async(sid,text,full,pk,profile);s["history"]=history;return full
@app.websocket("/ws")
async def ws_endpoint(ws:WebSocket,session_id="default"):
 await ws.accept();s=_ses(session_id);vad=VAD() if _cfg.vad.enabled else None
 LOG.info("WS connected: %s",session_id)
 try:
  while True:
   raw=await ws.receive()
   if raw.get("type")=="websocket.disconnect":break
   msg=raw.get("text") or raw.get("bytes")
   if isinstance(msg,str):
    try:
     cmd=json.loads(msg)
     t=cmd.get("type")
     if t=="set_persona":await set_persona(session_id,cmd.get("value"));s=_ses(session_id);await ws.send_text(json.dumps({"type":"persona_set","value":s["persona"]}))
     if t=="force_process" and vad:
      event,buf,src=vad.flush()
      if event=="se":
       text=asr.transcribe_pcm(buf)
       if text:await _proc_audio(text,s,s["persona"],session_id,ws)
    except:pass
   elif isinstance(msg,bytes) and vad:
    chunk=np.frombuffer(msg,dtype=np.int16).astype(np.float32)/32768.0
    event,buf,src=vad.add(chunk)
    if event=="se":
     text=asr.transcribe_pcm(buf)
     if text:await _proc_audio(text,s,s["persona"],session_id,ws)
 except WebSocketDisconnect:LOG.info("[%s] WS disconnected",session_id)
 except Exception as e:LOG.error("[%s] WS error: %s",session_id,e)
 finally:
  if vad:vad.reset()
@app.post("/chat")
async def chat_endpoint(audio:UploadFile=File(...),session_id="default"):
 import shutil
 path="input_"+session_id+".wav"
 with open(path,"wb") as f:shutil.copyfileobj(audio.file,f)
 text=asr.transcribe_file(path)
 if not text:return JSONResponse(400,content={"error":"asr failed"})
 s=_ses(session_id);pk=s["persona"];full=_do_llm(text,s,pk,session_id);voice_id=prompt.PERSONAS[pk]["voice"]
 def stream():
  from .tts.kokoro import get_tts as get_kokoro
  tts=get_kokoro();import soundfile as sf;agg=sentence_agg.SentenceAggregator()
  for sent in agg.split_sentences(full):
   audio=tts.generate(sent,sid=voice_id,speed=1.0);samples=np.array(audio.samples);buf=io.BytesIO()
   sf.write(buf,samples,audio.sample_rate,format="WAV");buf.seek(0);chunk=buf.read()
   yield len(chunk).to_bytes(4,"big")+chunk
 return StreamingResponse(stream(),media_type="application/octet-stream")
@app.get("/health")
async def health():return {"status":"ok","sessions":len(_SESSIONS)}
@app.get("/")
async def root():
 hp=_os.path.join(_os.path.dirname(__file__),"..","..","static","index.html")
 if _os.path.exists(hp):return HTMLResponse(open(hp,"r").read())
 return {"msg":"Buddy running"}
def create_app():return app
