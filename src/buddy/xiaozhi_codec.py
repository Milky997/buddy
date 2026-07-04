"""Xiaozhi protocol: Opus codec + audio frame parser + hello/listen/tts state machine."""
from __future__ import annotations
import asyncio, io, json, logging, time, uuid
from dataclasses import dataclass, field
from typing import Any
import numpy as np
import opuslib_next

logger = logging.getLogger(__name__)

XIAOZHI_HEADER_SIZE = 16

@dataclass(frozen=True)
class AudioFrame:
    payload: bytes
    raw_size: int
    timestamp: int | None
    mode: str  # "raw_opus" or "xiaozhi_header"

def parse_frame(packet: bytes) -> AudioFrame:
    """Parse a binary packet from ESP32 into an AudioFrame."""
    if len(packet) >= XIAOZHI_HEADER_SIZE and packet[0] == 1:
        sl = int.from_bytes(packet[2:4], "big")
        ll = int.from_bytes(packet[12:16], "big")
        pl = len(packet) - XIAOZHI_HEADER_SIZE
        if sl == ll == pl:
            ts = int.from_bytes(packet[8:12], "big")
            return AudioFrame(payload=packet[XIAOZHI_HEADER_SIZE:], raw_size=len(packet), timestamp=ts, mode="xiaozhi_header")
    return AudioFrame(payload=packet, raw_size=len(packet), timestamp=None, mode="raw_opus")

def decode_opus_frames(frames: list[bytes], sr=16000, channels=1, frame_ms=60) -> np.ndarray:
    """Decode list of Opus frames to float32 PCM array."""
    if not frames:
        return np.array([], dtype=np.float32)
    dec = opuslib_next.Decoder(sr, channels)
    fs = int(sr * frame_ms / 1000)
    pcm = b""
    for f in frames:
        try:
            pcm += dec.decode(f, fs)
        except opuslib_next.OpusError:
            pass
    del dec
    if not pcm:
        return np.array([], dtype=np.float32)
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

def encode_pcm_to_opus(pcm: np.ndarray, sr=24000, channels=1, frame_ms=60) -> list[bytes]:
    """Encode float32 PCM array to list of Opus frames."""
    if len(pcm) == 0:
        return []
    enc = opuslib_next.Encoder(sr, channels, "audio")
    fs = int(sr * frame_ms / 1000)
    pcm16 = np.clip(pcm * 32768, -32768, 32767).astype(np.int16).tobytes()
    frames = []
    for i in range(0, len(pcm16), fs * 2):
        chunk = pcm16[i:i + fs * 2]
        if len(chunk) < fs * 2:
            break
        try:
            frames.append(enc.encode(chunk, fs))
        except opuslib_next.OpusError:
            pass
    del enc
    return frames

def make_header_frame(opus_frame: bytes, ts: int = 0, seq: int = 0) -> bytes:
    """Wrap a raw Opus frame in Xiaozhi v2 header."""
    hdr = bytearray(XIAOZHI_HEADER_SIZE)
    hdr[0] = 1
    hdr[2:4] = len(opus_frame).to_bytes(2, "big")
    hdr[4:8] = seq.to_bytes(4, "big")
    hdr[8:12] = ts.to_bytes(4, "big")
    hdr[12:16] = len(opus_frame).to_bytes(4, "big")
    return bytes(hdr) + opus_frame

DEFAULT_AUDIO_PARAMS = {"format": "opus", "sample_rate": 24000, "channels": 1, "frame_duration": 60}

def build_hello(session_id: str, client_hello: dict) -> dict:
    """Build server hello response."""
    ap = client_hello.get("audio_params", {})
    if not isinstance(ap, dict):
        ap = {}
    return {
        "type": "hello",
        "version": client_hello.get("version", 1),
        "transport": "websocket",
        "session_id": session_id,
        "audio_params": {
            "format": "opus",
            "sample_rate": 24000,
            "channels": 1,
            "frame_duration": 60,
        },
    }

def ota_response(ws_url: str) -> dict:
    """Build OTA response telling ESP32 where to connect."""
    return {
        "server_time": {"timestamp": int(time.time() * 1000), "timezone_offset": 480},
        "firmware": {"version": "0.0.0", "url": ""},
        "websocket": {"url": ws_url, "token": ""},
        "message": "Buddy Gateway running.",
    }

class Session:
    """Track a single ESP32 session state."""
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.opus_frames: list[bytes] = []
        self.listening = False
        self.hello_received = False
        self.last_listen_state: str | None = None
        self.client_sr = 16000
        self.device_id: str | None = None
        self.client_id: str | None = None

    def add_opus(self, frame: bytes):
        self.opus_frames.append(frame)

    def clear_opus(self):
        self.opus_frames = []

    def decode_audio(self) -> np.ndarray:
        return decode_opus_frames(self.opus_frames, sr=self.client_sr)

class SessionManager:
    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def get_or_create(self, sid: str) -> Session:
        if sid not in self._sessions:
            self._sessions[sid] = Session(sid)
        return self._sessions[sid]

    def remove(self, sid: str):
        self._sessions.pop(sid, None)

    def count(self) -> int:
        return len(self._sessions)

def new_session_id() -> str:
    return "xiaozhi-" + uuid.uuid4().hex[:12]

# ====== Background AI processing pipeline ======

async def process_audio(
    ws: Any, session: Session, asr_fn, llm_fn, tts_fn, persona_key: str,
) -> None:
    """Decode Opus -> ASR -> LLM -> TTS -> send Opus + tts state messages."""
    try:
        pcm = session.decode_audio()
        if len(pcm) == 0:
            return
        # ASR
        text = asr_fn(pcm)
        if not text:
            return
        await ws.send_text(json.dumps({"type": "stt", "text": text, "session_id": session.session_id}))
        # LLM (runs in executor to not block)
        full = await asyncio.get_event_loop().run_in_executor(None, llm_fn, text)
        # TTS
        from .tts.kokoro import get_tts as get_kokoro
        tts = get_kokoro()
        voice_id = 23  # cheerful default
        agg = sentence_agg.SentenceAggregator()
        sentences = agg.split_sentences(full)
        await ws.send_text(json.dumps({"type": "tts", "state": "start", "session_id": session.session_id}))
        seq = 0
        for sent in sentences:
            audio = tts.generate(sent, sid=voice_id, speed=1.0)
            samples = np.array(audio.samples)
            opus_frames = encode_pcm_to_opus(samples)
            for opf in opus_frames:
                hdr = make_header_frame(opf, ts=seq * 60, seq=seq)
                await ws.send_bytes(hdr)
                seq += 1
                await asyncio.sleep(0.01)
        await ws.send_text(json.dumps({"type": "tts", "state": "stop", "session_id": session.session_id}))
    except Exception as e:
        logger.error("[xiaozhi] process_audio error: %s", e)
    finally:
        session.clear_opus()

