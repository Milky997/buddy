import numpy as np
import threading
_vad=None
_vl=threading.Lock()
try:
 import webrtcvad
 _HW=True
except ImportError:
 _HW=False
def get_vad():
 global _vad
 if _vad:return _vad
 with _vl:
  if _vad is None and _HW:_vad=webrtcvad.Vad(2);print("[vad] WebRTC VAD")
  elif not _HW:print("[vad] No VAD, volume only")
 return _vad
class VAD:
 def __init__(self,sr=16000,stop=0.6,maxs=15):
  self.sr=sr;self.sf=int(stop*50);self.msf=int(maxs*50)
  self.spf=0;self.sif=0;self.tsf=0;self.isp=False
  self.buf=np.array([],dtype=np.float32);self._vad=get_vad();self._vb=b""
 def add(self,chunk):
  self.buf=np.concatenate([self.buf,chunk])
  a=self._detect(chunk)
  if a:
   self.spf+=1;self.tsf+=1;self.sif=0
   if not self.isp and self.spf>=3:self.isp=True;return("ss",self.buf.copy(),"")
   if self.isp and self.tsf>self.msf:
    self.isp=False;b=self.buf.copy();self.buf=np.array([],dtype=np.float32);self.spf=0;self.sif=0;self.tsf=0;self._vb=b"";return("se",b,"auto")
   return("sp",np.array([]),"")
  else:
   self.sif+=1
   if self.isp and self.sif>=self.sf:
    self.isp=False;b=self.buf.copy();self.buf=np.array([],dtype=np.float32);self.spf=0;self.sif=0;self.tsf=0;return("se",b,"vad")
   return("si",np.array([]),"")
 def flush(self):
  if len(self.buf)>0:
   self.isp=False;b=self.buf.copy();self.buf=np.array([],dtype=np.float32);self.spf=0;self.sif=0;self.tsf=0;self._vb=b"";return("se",b,"manual")
  return("si",np.array([]),"")
 def _detect(self,chunk):
  if self._vad and len(chunk)>=160:
   pcm=np.clip(chunk*32768,-32768,32767).astype(np.int16)
   self._vb+=pcm.tobytes()
   while len(self._vb)>=640:
    f=self._vb[:640];self._vb=self._vb[640:]
    if self._vad.is_speech(f,self.sr):return True
   return False
  return np.abs(chunk).mean()>0.012
 def reset(self):
  self.buf=np.array([],dtype=np.float32);self.isp=False;self.spf=0;self.sif=0;self.tsf=0;self._vb=b""
