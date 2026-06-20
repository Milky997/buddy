# English Buddy

AI 英语口语陪练助手。支持实时语音对话，浏览器端和硬件端（ESP32）都能接。

## 架构

```
麦克风/ESP32 -> WebSocket -> VAD -> ASR (Whisper) -> LLM (Qwen2.5-7B) -> TTS (Kokoro) -> 扬声器播放
```

## 快速开始

### 本地 Mock 测试（无需 GPU）

```bash
cd D:\english-buddy
set BUDDY_MOCK=1
python -m uvicorn src.buddy.server:app --host 127.0.0.1 --port 8080
```

浏览器打开 `http://localhost:8080`

### 服务器部署（GPU 环境）

```bash
conda activate agent-dev
cd /root/autodl-tmp/english-buddy
pip install -r requirements.txt

export BUDDY_LLM_PATH="/root/autodl-tmp/llm_models/qwen/Qwen2.5-7B-Instruct"
export BUDDY_ASR_DIR="/root/autodl-tmp/tts-models/sherpa-onnx-whisper-base"
export BUDDY_KOKORO_DIR="/root/autodl-tmp/tts-models/kokoro-multi-lang-v1_1"
python -m uvicorn src.buddy.server:app --host 0.0.0.0 --port 6006
```

### SSH 隧道（本地访问）

```bash
ssh -p 37406 -L 8080:localhost:6006 root@connect.nmb1.seetacloud.com
```

浏览器打开 `http://localhost:8080`

## 使用方法

1. 打开页面，选择人格（Cheerful / Calm / Coach）
2. 点击 **Start**，授权麦克风
3. 说话，说完停一下，Buddy 自动回复
4. 如果没说停，点 **Send** 按钮手动发送
5. 超过 15 秒自动强制发送

## 项目结构

```
english-buddy/
├── src/buddy/           # 核心包
│   ├── server.py        # FastAPI + WebSocket 服务
│   ├── core.py          # vLLM 串行队列
│   ├── asr.py           # 语音识别 (Sherpa-ONNX Whisper)
│   ├── prompt.py        # Persona x Level x Skills
│   ├── vad.py           # 语音活动检测
│   ├── memory/          # SQLite 记忆系统
│   └── tts/             # TTS 引擎
├── static/index.html    # 浏览器前端
├── client.py            # 本地 Python 客户端
├── Dockerfile           # 容器部署
└── requirements.txt     # 依赖清单
```

## 配置项（环境变量）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `BUDDY_MOCK=1` | Mock 模式，无需 GPU | - |
| `BUDDY_LLM_PATH` | LLM 模型路径 | (见 config.py) |
| `BUDDY_ASR_DIR` | ASR 模型目录 | (见 config.py) |
| `BUDDY_KOKORO_DIR` | TTS 模型目录 | (见 config.py) |

## WebSocket 协议

**客户端 -> 服务器:**
- 二进制: 16-bit PCM 音频（16000Hz）
- JSON: `{"type": "set_persona", "value": "cheerful"}`
- JSON: `{"type": "force_process"}`（手动发送）

**服务器 -> 客户端:**
- JSON: `{"type": "transcript", "text": "..."}`（语音识别结果）
- JSON: `{"type": "reply", "text": "...", "latency_ms": 123}`（AI 回复）
- 二进制: 16-bit PCM 音频（24000Hz，TTS 语音）

## 参考

- [Milky997/buddy](https://github.com/Milky997/buddy)
- [abc4034/AI-Buddy](https://github.com/abc4034/AI-Buddy)
