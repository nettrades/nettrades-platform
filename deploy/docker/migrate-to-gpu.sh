#!/bin/bash
# =============================================================================
# NETTRADES.AI – CPU → GPU Migration Script
# =============================================================================
# Detects NVIDIA GPU, installs container toolkit, adds vLLM service,
# updates LangGraph environment, and stops the llama.cpp container.
# =============================================================================
set -euo pipefail
source /usr/local/bin/nettrades-ai-detect

if ! detect_gpu; then
    echo "No NVIDIA GPU detected. Nothing to migrate."
    exit 0
fi

install_nvidia_docker

cd /home/ubuntu/marketplace-platform

echo "Stopping llama.cpp container..."
docker compose stop llama-cpp
docker compose rm -f llama-cpp

# Add vLLM service to docker-compose.yml if not already present
if ! grep -q "vllm:" docker-compose.yml; then
    cat >> docker-compose.yml << 'EOF'

  vllm:
    image: vllm/vllm-openai:v0.6.3.post1
    runtime: nvidia
    container_name: vllm
    restart: unless-stopped
    networks: [internal]
    volumes: [~/.cache/huggingface:/root/.cache/huggingface]
    command: >
      --model deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B
      --api-key ${VLLM_API_KEY}
      --tensor-parallel-size 1
      --max-model-len 4096
    environment: [NVIDIA_VISIBLE_DEVICES=all]
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
EOF
fi

# Regenerate .env if VLLM_API_KEY is missing
if ! grep -q "VLLM_API_KEY" .env; then
    echo "VLLM_API_KEY=$(openssl rand -base64 32)" >> .env
fi

source .env
docker compose up -d vllm langgraph

echo "Migration complete. Inference now uses vLLM on GPU."