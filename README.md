# English Buddy 🎙️

面向儿童的 AI 英语口语练习助手。孩子对着麦克风说英语，Buddy 实时回复并朗读出来，同时记住孩子的学习进度和兴趣。

## 项目架构

```
用户说话
  → ASR（Sherpa-ONNX Whisper）     语音转文字
  → LLM（vLLM + Qwen2.5-1.5B）    生成回复
  → TTS（Kokoro）                  文字转语音，流式播放
  → 记忆更新（后台，与TTS并行）    更新用户画像
```

### 文件结构

```
agent_buddy/
├── serve.py              # FastAPI 服务端，主入口
├── buddy_core_v1.py      # ASR / LLM / TTS 核心逻辑
├── memory/               # 记忆系统模块
│   ├── __init__.py
│   ├── models.py         # 数据结构 UserProfile / Episode
│   ├── store.py          # SQLite 读写（线程安全）
│   └── manager.py        # 记忆业务逻辑
├── .gitignore
└── README.md

# 本地（不在此仓库）
client.py                 # 本地客户端，录音 + 播放
```

### 记忆系统

用户画像和对话记录持久化在 `buddy_memory.db`（SQLite）：

- `profile` 表：姓名、英语水平、兴趣爱好、对话次数（慢变量）
- `episodes` 表：每轮对话记录，带时间戳（快变量）

记忆更新流程：LLM 生成完整回复后，立刻在后台线程触发记忆提取（也走 vLLM），与 TTS 播放并行，不阻塞响应。

### vLLM 串行队列

vLLM 不支持并发调用，`buddy_core_v1.py` 里用一个全局队列（`_vllm_queue`）串行化所有 generate 任务，对话生成和记忆提取都通过 `vllm_generate()` 提交，不会冲突。

### 多人格

支持三种人格，可随时切换：

| 人格 | 风格 |
|------|------|
| cheerful（默认） | 活泼，像游戏一样学英语 |
| calm | 温柔，慢慢来不催 |
| coach | 严格，指出错误推动进步 |

---

## 环境配置

### 服务器环境

- 服务器：4090 显卡
- conda 环境：`agent-dev`
- 模型路径（不在仓库，需手动准备）：

```
~/work/mia/models/tts_models/kokoro-multi-lang-v1_1/   # TTS 模型
~/work/mia/models/tts_models/sherpa-onnx-whisper-base/  # ASR 模型
~/.cache/huggingface/hub/models--Qwen--Qwen2.5-1.5B-Instruct/  # LLM
```

### 环境变量

项目根目录新建 `.env`：

```
DASHSCOPE_API_KEY=你的key
```

---

## 启动方法

### 服务端（服务器上）

```bash
conda activate agent-dev
cd ~/work/mia/agent_buddy
python serve.py
```

启动后 vLLM 会在后台预热，端口立刻开放，第一条请求会稍慢。

### SSH 隧道（本地执行）

```bash
ssh -L 8080:localhost:8000 mustc501@43.132.187.41 -p 6500 -N
```

### 客户端（本地）

```bash
python client.py
```

---

## 查看记忆数据

```bash
# 查看用户画像
sqlite3 -column -header buddy_memory.db "SELECT * FROM profile;"

# 查看最近对话
sqlite3 -column -header buddy_memory.db \
  "SELECT * FROM episodes ORDER BY created_at DESC LIMIT 10;"
```

---

## 下一步计划

- [ ] CosyVoice 替换 Kokoro TTS
- [ ] Safety Filter（安全内容过滤）
- [ ] 换 Qwen2.5-7B 模型
- [ ] 微调 + RLHF

---

## 已知问题 / 注意事项

- `buddy_memory.db` 不上传 git（用户数据）
- `models/` 不上传 git（15G）
- 服务重启后 session history 会从数据库恢复最近 5 轮，不会完全丢失