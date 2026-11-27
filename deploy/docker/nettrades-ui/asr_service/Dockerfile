# =============================================================================
# FILE: deploy/docker/nettrades-ui/asr_service/Dockerfile
# =============================================================================
# Thin proxy that forwards audio to an existing llama-server running the
# Audar-ASR-V1-Flash model. Includes ffmpeg so the proxy can transcode the
# browser's webm/opus output to 16 kHz mono PCM WAV, which is what
# llama.cpp's mtmd audio decoder accepts.
# =============================================================================
FROM python:3.12-slim

# Install system dependencies, including Docker CLI so the web admin
# can manage containers via the mounted /var/run/docker.sock
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    curl \
    git \
    docker.io \
    docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=5s \
  CMD curl -f http://localhost:9000/health || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000"]