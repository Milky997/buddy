import re
class SentenceAggregator:
    # 同门的 FastSentenceAggregator，去掉 Pipecat 依赖，保留标点触发的核心逻辑
    def __init__(self):
        self._buf = ""
    def add(self, text: str) -> list:
        self._buf += text
        sentences = []
        while True:
            m = re.search(r'[.?!\u3002\uff1f\uff01\n]+[\'\"\u201d\u2019)]*\s*', self._buf)
            if not m:
                break
            idx = m.end()
            sentences.append(self._buf[:idx].strip())
            self._buf = self._buf[idx:]
        return sentences
    def flush(self) -> str:
        r = self._buf.strip()
        self._buf = ""
        return r
    def split_sentences(self, text: str) -> list:
        result, buf = [], ""
        for p in re.split(r'(?<=[.!?\u3002\uff01\uff1f])\s+', text.strip()):
            buf = (buf + " " + p).strip()
            if len(buf) >= 10:
                result.append(buf)
                buf = ""
        if buf:
            result.append(buf)
        return result
