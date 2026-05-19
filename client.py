import requests
import pyaudio
import wave
import threading
import pygame
import time
import queue

# ssh -L 8080:localhost:8000 mustc501@43.132.187.41 -p 6500 -N

SERVER_URL = "http://localhost:6006"
SESSION_ID = "user1"

PERSONAS = {
    "1": ("cheerful", "🌟 Buddy (活泼)"),
    "2": ("calm",     "🌙 Buddy (温柔)"),
    "3": ("coach",    "🏆 Coach (严格)"),
}


def select_persona() -> str:
    print("\n选择 Buddy 的人格：")
    for num, (key, name) in PERSONAS.items():
        print(f"  [{num}] {name}")

    while True:
        choice = input("输入数字 (直接回车 = 默认活泼): ").strip()
        if choice == "":
            return "cheerful"
        if choice in PERSONAS:
            return PERSONAS[choice][0]
        print("  请输入有效数字")


def set_persona(persona_key: str):
    response = requests.post(
        f"{SERVER_URL}/set_persona",
        params={"session_id": SESSION_ID, "persona_key": persona_key},
    )
    data = response.json()
    print(f"✅ 已选择：{data['display_name']}")


def record_audio(filename="input.wav") -> str:
    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=16000,
        input=True,
        frames_per_buffer=1024
    )
    frames = []
    recording = True

    def record_thread():
        while recording:
            frames.append(stream.read(1024, exception_on_overflow=False))

    t = threading.Thread(target=record_thread, daemon=True)
    t.start()
    print("🎤 录音中... 按 Enter 结束")
    input()
    recording = False
    t.join()
    stream.stop_stream()
    stream.close()
    pa.terminate()

    with wave.open(filename, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(pa.get_sample_size(pyaudio.paInt16))
        wf.setframerate(16000)
        wf.writeframes(b"".join(frames))
    return filename


def receive_and_play(response):
    """接收流式音频块，边收边播"""
    audio_queue = queue.Queue()

    def receiver():
        buf = b""
        for chunk in response.iter_content(chunk_size=None):
            buf += chunk
            while len(buf) >= 4:
                length = int.from_bytes(buf[:4], "big")
                if len(buf) < 4 + length:
                    break
                wav_bytes = buf[4:4 + length]
                buf = buf[4 + length:]
                audio_queue.put(wav_bytes)
        audio_queue.put(None)  # 结束信号

    def player():
        pygame.mixer.init()
        chunk_index = 0
        while True:
            wav_bytes = audio_queue.get()
            if wav_bytes is None:
                break
            # 每块用不同文件名，避免文件锁冲突
            filename = f"tmp_chunk_{chunk_index}.wav"
            chunk_index += 1
            with open(filename, "wb") as f:
                f.write(wav_bytes)
            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
            pygame.mixer.music.unload()  # 显式释放文件锁
        pygame.mixer.quit()

    t_recv = threading.Thread(target=receiver, daemon=True)
    t_play = threading.Thread(target=player, daemon=True)
    t_recv.start()
    t_play.start()
    t_recv.join()
    t_play.join()


def main():
    print("=" * 40)
    print("  English Buddy 客户端")
    print("  对话中输入 /switch 可切换人格")
    print("=" * 40)

    persona_key = select_persona()
    set_persona(persona_key)

    while True:
        try:
            cmd = input("\n按 Enter 开始录音，或输入 /switch 切换人格... ").strip()

            if cmd.lower() == "/switch":
                persona_key = select_persona()
                set_persona(persona_key)
                continue

            # 录音
            audio_file = record_audio()

            # 发给服务器
            print("⏳ 发送中...")
            t0 = time.time()
            with open(audio_file, "rb") as f:
                response = requests.post(
                    f"{SERVER_URL}/chat",
                    files={"audio": ("input.wav", f, "audio/wav")},
                    params={"session_id": SESSION_ID},
                    timeout=120,
                    stream=True  # ← 流式接收
                )
            print(f"  ⏱ 首包到达：{time.time()-t0:.1f}s")

            receive_and_play(response)

        except KeyboardInterrupt:
            print("\nBye!")
            break


if __name__ == "__main__":
    main()