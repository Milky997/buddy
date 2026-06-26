# English Buddy — 硬件接入协议文档

## 项目概况

English Buddy 是一个 AI 英语口语陪练，目前已跑通全链路：

```
硬件端（待开发）           服务器（已完成）
     │                         │
     ├─ PCM音频(16000Hz) ─────→ WebSocket → VAD → ASR(Whisper)
     │                                                     │
     │                                                     ↓
     │                                                    LLM(Qwen2.5)
     │                                                     │
     │                                                     ↓
     │                                                    TTS(Kokoro)
     │                                                     │
     └── PCM音频(24000Hz) ←──── WebSocket ────────────────┘
```

## 分工

| 谁 | 负责 | 状态 |
|----|------|------|
| 服务器端（我方） | FastAPI 服务 / ASR / LLM / TTS / WebSocket 端点 | ✅ 已完成，线上运行 |
| 硬件端 | ESP32 采集音频 → WebSocket 发送 → 接收播放 | ❌ 待开发 |

## 服务器信息

| 项目 | 值 |
|------|-----|
| 服务器地址 | connect.nmb1.seetacloud.com |
| 端口 | 6006 |
| WebSocket URL | `ws://connect.nmb1.seetacloud.com:37406/ws` |
| 健康检查 | `http://connect.nmb1.seetacloud.com:37406/health` |

> 注意：实际端口是 37406（SSH 映射），WebSocket 路径为 `/ws`。

## WebSocket 协议

### 连接

建立 WebSocket 连接到 `ws://connect.nmb1.seetacloud.com:37406/ws`。

### 数据格式

| 方向 | 类型 | 格式 | 说明 |
|------|------|------|------|
| ESP32 → 服务器 | 二进制 | 16-bit PCM, mono, **16000Hz** | 麦克风采集的音频 |
| 服务器 → ESP32 | 二进制 | 16-bit PCM, mono, **24000Hz** | TTS 合成的语音 |
| ESP32 → 服务器 | 文本 | JSON 格式控制消息 | 见下表 |
| 服务器 → ESP32 | 文本 | JSON 格式状态消息 | 见下表 |

### 音频格式细节

**上行（ESP32 → 服务器）：**
- 编码：PCM 16-bit signed little-endian
- 声道：单声道 (mono)
- 采样率：**16000 Hz**
- 分片大小：每次 WebSocket send 约 4096 采样点（8192 字节）
- 服务器内有 VAD 检测，发送静音也不影响，持续发就行

**下行（服务器 → ESP32）：**
- 编码：PCM 16-bit signed little-endian
- 声道：单声道 (mono)
- 采样率：**24000 Hz**
- 每次收到一块音频直接送入 DAC 播放即可

### JSON 控制消息

**ESP32 → 服务器：**

```json
// 切换人格（连接后可发一次，默认 cheerful）
{"type": "set_persona", "value": "cheerful"}

// 可选人格：cheerful / calm / coach
```

**服务器 → ESP32：**

```json
// 语音识别结果（用户说了什么）
{"type": "transcript", "text": "hello buddy how are you"}

// AI 回复文字（可选，用于屏幕显示）
{"type": "reply", "text": "I am doing great!", "latency_ms": 850}

// 人格切换确认
{"type": "persona_set", "value": "cheerful"}
```

### 完整对话流程

```
1. ESP32 连接 ws://...:37406/ws
2. ESP32 发送 set_persona（可选）
3. ESP32 持续发送麦克风 PCM 音频流（16000Hz）
4. 服务器 VAD 检测到人说完话 →
   发送 {"type": "transcript", "text": "..."}
   发送 {"type": "reply", "text": "...", "latency_ms": 123}
   开始发送 TTS 音频块（24000Hz PCM）
5. ESP32 收到 transcript → 可在屏幕上显示文字（可选）
   ESP32 收到 reply → 可在屏幕上显示 Buddy 回复（可选）
   ESP32 收到音频数据 → 立即送入喇叭播放
6. 回到步骤 3，循环
```

## ESP32 需要实现的功能清单

硬件端（ESP32）需完成以下功能：

- [ ] WiFi 连接，支持配置 SSID/密码
- [ ] WebSocket 客户端连接服务器
- [ ] I2S 麦克风采集音频（16000Hz, 16-bit, mono）
- [ ] 实时发送音频数据到 WebSocket
- [ ] 接收 WebSocket 音频数据 → I2S 喇叭播放（24000Hz）
- [ ] 接收并解析 JSON 消息（可选，用于屏幕交互）
- [ ] 发送 JSON 切换人格（可选）
- [ ] 重连机制（断线自动重连）
- [ ] 心跳保活

## 伪代码示例

```cpp
// ESP32 端核心逻辑（伪代码，实际用 Arduino / ESP-IDF）

void setup() {
    WiFi.begin(ssid, password);
    connectWebSocket();
    initI2SMic(16000);   // 配置 I2S 麦克风 16000Hz
    initI2SSpeaker(24000); // 配置 I2S 喇叭 24000Hz
}

void loop() {
    // 1. 采集麦克风音频
    int16_t mic_buffer[4096];
    i2s_read(mic_buffer, sizeof(mic_buffer));
    
    // 2. 发送到服务器
    if (ws.connected()) {
        ws.sendBinary((uint8_t*)mic_buffer, sizeof(mic_buffer));
    }
    
    // 3. 接收服务器数据
    while (ws.available()) {
        auto msg = ws.read();
        if (msg.isBinary()) {
            // 音频数据 → 喇叭播放
            i2s_write((int16_t*)msg.data(), msg.length() / 2);
        }
        else if (msg.isText()) {
            // JSON 消息 → 处理 / 显示
            parseAndDisplay(msg.text());
        }
    }
}
```

## 参考

- 项目 GitHub：https://github.com/Milky997/buddy/tree/integrated-v1
- 服务器 README 有完整配置说明
- 有疑问请联系我方
