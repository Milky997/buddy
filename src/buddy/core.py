import threading, queue
_vllm_model = None
_tokenizer = None
_vllm_queue = queue.Queue()

class _MockTokenizer:
    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
        r = ""
        for m in messages: r += "<|im_start|>" + m["role"] + "\n" + m["content"] + "<|im_end|>\n"
        if add_generation_prompt: r += "<|im_start|>assistant\n"
        return r
    def __call__(self, *args, **kwargs): return self

def get_model():
    global _vllm_model, _tokenizer
    if _vllm_model is not None or _tokenizer is not None:
        return _vllm_model, _tokenizer
    from .config import load
    c = load()
    if c.mock:
        _tokenizer = _MockTokenizer()
        print("[core] MOCK mode ready")
        return None, _tokenizer
    from vllm import LLM
    from transformers import AutoTokenizer
    print("[core] loading vLLM...")
    _vllm_model = LLM(model=c.llm.model_path, gpu_memory_utilization=c.llm.gpu_memory_utilization)
    _tokenizer = AutoTokenizer.from_pretrained(c.llm.model_path)
    print("[core] vLLM loaded")
    return _vllm_model, _tokenizer

def _worker():
    while True:
        p, sp, f = _vllm_queue.get()
        try:
            llm, _ = get_model()
            o = llm.generate([p], sp)
            f["result"] = o[0].outputs[0].text.strip()
        except Exception as e:
            f["error"] = e
        finally:
            f["done"].set()
threading.Thread(target=_worker, daemon=True, name="vllm-worker").start()

def generate(prompt, sampling_params):
    from .config import load
    if load().mock:
        return "That is great! Tell me more! Do you enjoy playing sports or reading books?"
    future = {"result": None, "error": None, "done": threading.Event()}
    _vllm_queue.put((prompt, sampling_params, future))
    future["done"].wait()
    if future["error"]: raise future["error"]
    return future["result"]

def warmup():
    from .config import load
    if load().mock:
        print("[core] MOCK mode - skip warmup")
        return
    threading.Thread(target=get_model, daemon=True, name="vllm-warmup").start()
    print("[core] vLLM warming up...")
