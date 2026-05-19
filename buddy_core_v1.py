import json
import os
import threading
import queue
from dotenv import load_dotenv
import re
import dashscope
from transformers import AutoTokenizer
import sherpa_onnx
import wave
import numpy as np
import soundfile as sf

# ─────────────────────────────────────────────────────────
# TTS
# ─────────────────────────────────────────────────────────

KOKORO_MODEL_DIR = "/home/mustc501/work/mia/models/tts_models/kokoro-multi-lang-v1_1"

_tts = None

def get_tts():
    global _tts
    if _tts is None:
        print("加载 Kokoro TTS...")
        _tts = sherpa_onnx.OfflineTts(
            sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                        model=f"{KOKORO_MODEL_DIR}/model.onnx",
                        voices=f"{KOKORO_MODEL_DIR}/voices.bin",
                        tokens=f"{KOKORO_MODEL_DIR}/tokens.txt",
                        data_dir=f"{KOKORO_MODEL_DIR}/espeak-ng-data",
                        dict_dir=f"{KOKORO_MODEL_DIR}/dict",
                        lexicon=f"{KOKORO_MODEL_DIR}/lexicon-us-en.txt,{KOKORO_MODEL_DIR}/lexicon-zh.txt",
                    )
                ),
            )
        )
        print("Kokoro TTS 加载完成")
    return _tts

# ─────────────────────────────────────────────────────────
# ASR
# ─────────────────────────────────────────────────────────

MODEL_DIR = "/home/mustc501/work/mia/models/tts_models/sherpa-onnx-whisper-base"

if not os.path.exists(MODEL_DIR):
    raise FileNotFoundError(f"找不到模型目录: {MODEL_DIR}")

print("🚀 正在唤醒 Sherpa-ONNX 耳朵...")
recognizer = sherpa_onnx.OfflineRecognizer.from_whisper(
    encoder=f"{MODEL_DIR}/base-encoder.int8.onnx",
    decoder=f"{MODEL_DIR}/base-decoder.int8.onnx",
    tokens=f"{MODEL_DIR}/base-tokens.txt",
    num_threads=4,
    language="en",
    task="transcribe"
)

# ─────────────────────────────────────────────────────────
# vLLM 单例 + 全局串行队列
# ─────────────────────────────────────────────────────────

_vllm_model = None
_tokenizer = None
_vllm_queue = queue.Queue()


def get_vllm_model():
    global _vllm_model, _tokenizer
    if _vllm_model is None:
        from vllm import LLM
        print("开始加载vLLM...")
        _vllm_model = LLM(
            model="/home/mustc501/.cache/huggingface/hub/models--Qwen--Qwen2.5-1.5B-Instruct/snapshots/989aa7980e4cf806f80c7fef2b1adb7bc71aa306",
            gpu_memory_utilization=0.4
        )
        print("vLLM加载完成")
        _tokenizer = AutoTokenizer.from_pretrained(
            "/home/mustc501/.cache/huggingface/hub/models--Qwen--Qwen2.5-1.5B-Instruct/snapshots/989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
        )
        print("tokenizer加载完成")
    return _vllm_model, _tokenizer


def _vllm_worker():
    """长驻后台线程，串行执行所有 vLLM generate() 任务"""
    while True:
        prompt, sampling_params, future = _vllm_queue.get()
        try:
            llm, _ = get_vllm_model()
            outputs = llm.generate([prompt], sampling_params)
            future["result"] = outputs[0].outputs[0].text.strip()
        except Exception as e:
            future["error"] = e
        finally:
            future["done"].set()


def vllm_generate(prompt: str, sampling_params) -> str:
    """提交 generate 任务并阻塞等待结果（线程安全）"""
    future = {"result": None, "error": None, "done": threading.Event()}
    _vllm_queue.put((prompt, sampling_params, future))
    future["done"].wait()
    if future["error"]:
        raise future["error"]
    return future["result"]


threading.Thread(target=_vllm_worker, daemon=True, name="vllm-worker").start()
print("✅ vLLM 串行队列已启动")

load_dotenv()
dashscope.api_key = os.environ.get("DASHSCOPE_API_KEY")

# ─────────────────────────────────────────────────────────
# 人格配置
# ─────────────────────────────────────────────────────────

PERSONAS = {
    "cheerful": {
        "display_name": "Buddy (活泼)",
        "description": "energetic, playful, loves games and fun challenges",
        "speaking_style": (
            "Use short punchy sentences. React with enthusiasm like 'Wow!', 'Nice one!', 'You got it!'. "
            "Make learning feel like a game."
        ),
        "voice": 23,
        "temperature": 0.9,
    },
    "calm": {
        "display_name": "Buddy (温柔)",
        "description": "calm, patient, like a gentle and encouraging tutor",
        "speaking_style": (
            "Speak slowly and clearly. Use simple encouraging phrases. "
            "Never rush the learner. Celebrate small wins warmly."
        ),
        "voice": 30,
        "temperature": 0.6,
    },
    "coach": {
        "display_name": "Coach (严格)",
        "description": "strict but fair, pushes the learner to improve",
        "speaking_style": (
            "Be direct and precise. Point out mistakes clearly. "
            "Set mini-challenges each turn. Praise only genuine improvement."
        ),
        "voice": 2,
        "temperature": 0.7,
    },
}

DEFAULT_PERSONA = "cheerful"

# ─────────────────────────────────────────────────────────
# Level 行为指引
# ─────────────────────────────────────────────────────────

LEVEL_GUIDES = {
    "beginner": """
## Speaking level: BEGINNER
- Use only simple A1-A2 vocabulary. Max 8 words per sentence.
- Never use idioms, slang, or phrasal verbs.
- Repeat key words naturally to reinforce them.
- If the user struggles, offer two simple answer choices.
""",
    "intermediate": """
## Speaking level: INTERMEDIATE
- Mix simple and complex sentences naturally.
- Introduce one idiom or phrasal verb per conversation, explained simply.
- Gently expand vocabulary with context clues.
""",
    "advanced": """
## Speaking level: ADVANCED
- Use natural, native-speaker expressions freely.
- Discuss abstract or nuanced topics.
- Challenge with precise vocabulary and complex grammar structures.
""",
    "unknown": """
## Speaking level: UNKNOWN
- Start simple, then adapt upward based on the user's responses.
- Watch for vocabulary range and sentence complexity as signals.
""",
}

# ─────────────────────────────────────────────────────────
# Skills
# ─────────────────────────────────────────────────────────

SKILLS = {
    "conversation": """
[SKILL: Conversation Partner]
- Keep the chat natural and flowing.
- End every reply with one engaging follow-up question.
- Match the user's energy and topic interest.
""",
    "grammar": """
[SKILL: Grammar Coach]
- Listen for genuine spoken grammar mistakes (wrong tense, wrong preposition, missing article, wrong word order etc.)
- If you spot ONE clear mistake, gently point it out after your reply.
- Format: ✏️ "what you said" → "correct version" + one-sentence explanation
- If there is no clear mistake, skip this entirely — do NOT mention grammar at all.
- Do NOT correct capitalization, punctuation, or symbols — these come from speech recognition, not the user.
""",
    "vocab": """
[SKILL: Vocabulary Builder]
- Introduce ONE new word that fits naturally into the conversation.
- Format: 💡 New word: **word** — short definition
- Keep it relevant to what the user is talking about.
""",
    "assessment": """
[SKILL: Level Assessment]
- Pay attention to vocabulary range, grammar, and sentence complexity.
- At the very end of your reply, add one line:
  📊 Level note: [brief observation about their current level]
""",
}


def pick_skills(memory) -> list[str]:
    level = memory.level if hasattr(memory, "level") else memory.get("level", "unknown")
    session_count = memory.session_count if hasattr(memory, "session_count") else memory.get("session_count", 0)
    active = ["conversation"]
    if level == "unknown":
        active.append("assessment")
    active.append("grammar")
    if session_count % 3 == 0:
        active.append("vocab")
    return active


def build_system_prompt(memory, active_skills: list[str], persona: dict) -> str:
    name      = memory.name      if hasattr(memory, "name")      else memory.get("name", "unknown")
    interests = memory.interests if hasattr(memory, "interests")  else memory.get("interests", [])
    level     = memory.level     if hasattr(memory, "level")      else memory.get("level", "unknown")

    profile_lines = []
    if name != "unknown":
        profile_lines.append(f"- User's name: {name}, use it naturally in conversation")
    if interests:
        profile_lines.append(f"- Interests: {', '.join(interests)}")
    profile_str = "\n".join(profile_lines) if profile_lines else "- (no profile yet)"

    skills_str = "\n".join(SKILLS[s] for s in active_skills)
    level_guide = LEVEL_GUIDES.get(level, LEVEL_GUIDES["unknown"])

    return f"""You are an enthusiastic English conversation partner called Buddy, designed for children.

## Your personality
You are {persona['description']}.
{persona['speaking_style']}

{level_guide}

## User profile
{profile_str}

## Active skills for this turn
{skills_str}

## General rules
- Always reply in English.
- Be warm, encouraging, and patient.
- Keep every reply under 3 sentences. Be concise.
- Never overwhelm the user — max one correction and one new word per turn.
- If the user writes in another language, gently reply in English and invite them to try in English too.
"""


# ─────────────────────────────────────────────────────────
# 主对话函数
# ─────────────────────────────────────────────────────────

def chat_stream(user_message: str, history: list, memory, persona_key: str = DEFAULT_PERSONA):
    """生成完整回复，yield 格式：
      ("__FULL__", full_reply)   ← 第一条，完整文本，serve 用来触发记忆更新
      ("__SENT__", sentence)     ← 后续每句，serve 用来做 TTS
    """
    persona = PERSONAS[persona_key]
    active_skills = pick_skills(memory)
    system = build_system_prompt(memory, active_skills, persona)

    history.append({"role": "user", "content": user_message})

    _, tokenizer = get_vllm_model()
    messages = [{"role": "system", "content": system}] + history
    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )

    from vllm import SamplingParams
    sampling_params = SamplingParams(temperature=persona["temperature"], max_tokens=512)

    # 通过队列，和记忆提取串行，不会冲突
    full_reply = vllm_generate(prompt, sampling_params)
    history.append({"role": "assistant", "content": full_reply})
    print(f"🤖 Buddy ({persona_key})：{full_reply}")

    # 先 yield 完整 reply，serve 拿到后立刻触发记忆更新（不等 TTS）
    yield "__FULL__", full_reply

    # 再逐句 yield 给 TTS
    for sent in split_sentences(clean_for_tts(full_reply)):
        if sent.strip():
            yield "__SENT__", sent


# ─────────────────────────────────────────────────────────
# ASR / TTS / 工具函数
# ─────────────────────────────────────────────────────────

def transcribe(filename="input.wav") -> str:
    if not os.path.exists(filename):
        print(f"❌ 错误：找不到音频文件 {filename}")
        return ""

    print("⏳ Sherpa-ONNX 识别中...")
    try:
        with wave.open(filename, "rb") as f:
            sample_rate = f.getframerate()
            samples = np.frombuffer(
                f.readframes(f.getnframes()), dtype=np.int16
            ).astype(np.float32) / 32768.0
            if f.getnchannels() > 1:
                samples = samples.reshape(-1, f.getnchannels()).mean(axis=1)

        stream = recognizer.create_stream()
        stream.accept_waveform(sample_rate, samples)
        recognizer.decode_stream(stream)
        text = stream.result.text.strip()
        print(f"📝 你说：{text}")
        return text

    except Exception as e:
        print(f"❌ ASR 识别发生错误: {e}")
        return ""


def clean_for_tts(text: str) -> str:
    text = re.sub(r'[^\x00-\x7F\u4e00-\u9fff\s.,!?;:\'\"-]', '', text)
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'#+\s', '', text)
    text = re.sub(r'\n{2,}', ' ', text)
    return text.strip()


def text_to_speech(text: str, filename="output.wav", speaker_id=0) -> str:
    print("🔊 TTS 合成中...")
    tts = get_tts()
    audio = tts.generate(text, sid=speaker_id, speed=1.0)
    sf.write(filename, np.array(audio.samples), audio.sample_rate)
    return filename


def split_sentences(text: str) -> list[str]:
    parts = re.split(r'(?<=[.!?。！？])\s+', text.strip())
    result, buf = [], ""
    for p in parts:
        buf = (buf + " " + p).strip()
        if len(buf) >= 10:
            result.append(buf)
            buf = ""
    if buf:
        result.append(buf)
    return result