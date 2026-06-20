import os, wave, numpy as np
_recognizer = None
def _get():
    global _recognizer
    if _recognizer is not None: return _recognizer
    from .config import load
    c = load()
    if c.mock: return None
    import sherpa_onnx
    if not os.path.exists(c.asr.model_dir):
        raise FileNotFoundError('ASR model not found: ' + c.asr.model_dir)
    _recognizer = sherpa_onnx.OfflineRecognizer.from_whisper(
        encoder=c.asr.model_dir+'/base-encoder.int8.onnx',
        decoder=c.asr.model_dir+'/base-decoder.int8.onnx',
        tokens=c.asr.model_dir+'/base-tokens.txt',
        num_threads=c.asr.num_threads, language=c.asr.language, task='transcribe')
    return _recognizer
def transcribe_file(path):
    from .config import load
    if load().mock: return 'Hello buddy, how are you today?'
    if not os.path.exists(path): return ''
    with wave.open(path, 'rb') as f:
        sr = f.getframerate()
        s = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        if f.getnchannels() > 1: s = s.reshape(-1, f.getnchannels()).mean(axis=1)
    return _run(s, sr)
def transcribe_pcm(samples, sr=16000):
    from .config import load
    if load().mock: return 'I like playing basketball and reading books.'
    return _run(samples, sr)
def _run(samples, sr):
    rec = _get()
    if rec is None: return ''
    stream = rec.create_stream()
    stream.accept_waveform(sr, samples)
    rec.decode_stream(stream)
    text = stream.result.text.strip()
    if text: print('[asr]', text)
    return text
