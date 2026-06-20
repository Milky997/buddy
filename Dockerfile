FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime
RUN pip install fastapi uvicorn python-dotenv sherpa-onnx soundfile numpy transformers vllm pydantic webrtcvad
COPY src/ /app/src/
COPY static/ /app/static/
COPY requirements.txt /app/
WORKDIR /app
CMD ["uvicorn", "src.buddy.server:app", "--host", "0.0.0.0", "--port", "8000"]
