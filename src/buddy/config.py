"""集中配置。从环境变量 /.env 读，提供合理默认值。"""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class TTSConfig:
    engine: str = "kokoro"              # "kokoro" | "qwen3"
    kokoro_model_dir: str = "/home/mustc501/work/mia/models/tts_models/kokoro-multi-lang-v1_1"
    qwen3_model_path: str = "/mnt/data/TTS_MODELS/models--Qwen--Qwen3-TTS-12Hz-0.6B-CustomVoice/snapshots/85e237c12c027371202489a0ec509ded67b5e4b5"
    tts_sample_rate: int = 24000
    tts_speed: float = 1.0


@dataclass
class ASRConfig:
    model_dir: str = "/home/mustc501/work/mia/models/tts_models/sherpa-onnx-whisper-base"
    num_threads: int = 4
    language: str = "en"
    sample_rate: int = 16000


@dataclass
class LLMConfig:
    model_path: str = "/home/mustc501/.cache/huggingface/hub/models--Qwen--Qwen2.5-1.5B-Instruct/snapshots/989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
    gpu_memory_utilization: float = 0.4
    max_tokens: int = 512


@dataclass
class VADConfig:
    enabled: bool = True
    stop_secs: float = 0.6


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    ping_interval: float = 10.0
    ping_timeout: float = 30.0
    max_audio_buffer_secs: int = 30


@dataclass
class AppConfig:
    tts: TTSConfig = field(default_factory=TTSConfig)
    asr: ASRConfig = field(default_factory=ASRConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    vad: VADConfig = field(default_factory=VADConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    memory_db_path: str = "./buddy_memory.db"
    dashscope_api_key: str = ""
    mock: bool = False


def load() -> AppConfig:
    cfg = AppConfig()
    cfg.dashscope_api_key = os.getenv("DASHSCOPE_API_KEY", "")
    cfg.mock = os.getenv("BUDDY_MOCK", "0") == "1"
    if p := os.getenv("BUDDY_KOKORO_DIR"):
        cfg.tts.kokoro_model_dir = p
    if p := os.getenv("BUDDY_ASR_DIR"):
        cfg.asr.model_dir = p
    if p := os.getenv("BUDDY_LLM_PATH"):
        cfg.llm.model_path = p
    if p := os.getenv("BUDDY_DB_PATH"):
        cfg.memory_db_path = p
    if e := os.getenv("BUDDY_TTS_ENGINE"):
        cfg.tts.engine = e
    return cfg
