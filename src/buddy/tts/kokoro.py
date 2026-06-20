import numpy as np
_tts=None
class _MockTTS:
 def generate(self,text,sid=0,speed=1.0):
  class MA:
   def __init__(s):s.samples=np.zeros(24000,dtype=np.float32);s.sample_rate=24000
  return MA()
 sample_rate=24000
def get_tts():
 global _tts
 if _tts:return _tts
 from ..config import load
 c=load()
 if c.mock:_tts=_MockTTS();print("[kokoro] MOCK");return _tts
 import sherpa_onnx, soundfile as sf
 d=c.tts.kokoro_model_dir
 print("[kokoro] loading...")
 _tts=sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(
  model=sherpa_onnx.OfflineTtsModelConfig(
   kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
    model=d+"/model.onnx",voices=d+"/voices.bin",tokens=d+"/tokens.txt",data_dir=d+"/espeak-ng-data",dict_dir=d+"/dict",lexicon=d+"/lexicon-us-en.txt,"+d+"/lexicon-zh.txt"))))
 print("[kokoro] loaded")
 return _tts
