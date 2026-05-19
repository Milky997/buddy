from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn
import shutil
import time
import numpy as np
import soundfile as sf
import asyncio
import threading
import io
from contextlib import asynccontextmanager

from buddy_core_v1 import chat_stream, transcribe, PERSONAS, DEFAULT_PERSONA, get_vllm_model, get_tts
from memory.managerv import MemoryManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=get_vllm_model, daemon=True, name="warmup").start()
    print("🔄 vLLM 预热中（后台）...")
    yield


app = FastAPI(lifespan=lifespan)

memory_manager = MemoryManager(db_path="./buddy_memory.db")
sessions = {}


def get_session(session_id: str) -> dict:
    if session_id not in sessions:
        profile = memory_manager.load(session_id)
        sessions[session_id] = {
            "profile": profile,
            "histories": {
                key: memory_manager.get_recent_history(session_id, limit=5)
                for key in PERSONAS
            },
            "current_persona": DEFAULT_PERSONA,
        }
    return sessions[session_id]


@app.post("/set_persona")
async def set_persona(session_id: str = "default", persona_key: str = DEFAULT_PERSONA):
    if persona_key not in PERSONAS:
        return JSONResponse(
            status_code=400,
            content={"error": f"未知人格，可选：{list(PERSONAS.keys())}"}
        )
    session = get_session(session_id)
    session["current_persona"] = persona_key
    return {
        "ok": True,
        "persona": persona_key,
        "display_name": PERSONAS[persona_key]["display_name"],
    }


@app.post("/chat")
async def chat_endpoint(
    audio: UploadFile = File(...),
    session_id: str = "default"
):
    t0 = time.time()

    # 1. 保存音频
    input_path = f"input_{session_id}.wav"
    with open(input_path, "wb") as f:
        shutil.copyfileobj(audio.file, f)
    print(f"  ⏱ 音频保存：{time.time()-t0:.1f}s")

    # 2. ASR
    t1 = time.time()
    user_text = transcribe(input_path)
    print(f"  ⏱ ASR：{time.time()-t1:.1f}s")
    if not user_text:
        return JSONResponse(status_code=400, content={"error": "识别失败"})

    # 3. 取 session
    session = get_session(session_id)
    profile = session["profile"]
    persona_key = session["current_persona"]
    history = session["histories"][persona_key]
    voice = PERSONAS[persona_key]["voice"]

    # 4. 流式生成音频
    def audio_stream():
        t2 = time.time()
        first_sentence = True

        for tag, content in chat_stream(user_text, history, profile, persona_key=persona_key):

            if tag == "__FULL__":
                # 完整 reply 拿到，立刻在后台触发记忆更新
                # 此时 TTS 还没开始，记忆更新和 TTS 并行
                memory_manager.update_async(
                    user_id=session_id,
                    user_msg=user_text,
                    reply=content,
                    persona=persona_key,
                    profile=profile,
                )
                continue  # 不做 TTS，继续拿句子

            # tag == "__SENT__"，做 TTS
            t3 = time.time()
            tts = get_tts()
            audio = tts.generate(content, sid=voice, speed=1.0)
            samples = np.array(audio.samples)

            buf = io.BytesIO()
            sf.write(buf, samples, audio.sample_rate, format="WAV")
            buf.seek(0)
            chunk = buf.read()

            if first_sentence:
                print(f"  ⏱ LLM首句+TTS：{time.time()-t2:.1f}s  (总计：{time.time()-t0:.1f}s)")
                first_sentence = False
            print(f"  ⏱ 本句TTS：{time.time()-t3:.1f}s  [{content[:20]}...]")

            yield len(chunk).to_bytes(4, "big") + chunk

        print(f"  ⏱ 全部完成：{time.time()-t0:.1f}s")

    return StreamingResponse(audio_stream(), media_type="application/octet-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)