# =============================================================================
# FILE: scripts/builds/llama-rpc/Dockerfile
# =============================================================================
# PURPOSE:
#   Builds the RPC master container. Coordinator only, no GPU compute.
#   Static linking (BUILD_SHARED_LIBS=OFF) is mandatory because
#   GGML_BACKEND_PATH directory scanning is brittle across llama.cpp
#   versions. See the previous version's comments for context — they
#   still apply.
# =============================================================================
FROM nvidia/cuda:12.4.1-devel-ubuntu22.04

ARG LLAMA_CPP_TAG=master
ARG CUDA_ARCH=70

RUN apt-get update && apt-get install -y --no-install-recommends \
    git cmake build-essential libssl-dev curl ca-certificates libcurl4-openssl-dev && \
    rm -rf /var/lib/apt/lists/*

# Pin to a specific tag. Never --depth 1 on master — that is the whole
# reason install-spoke.sh was non-deterministic. If LLAMA_CPP_TAG is
# "master", a warning is printed below.
RUN echo "Building llama.cpp @ ${LLAMA_CPP_TAG}" && \
    git clone https://github.com/ggml-org/llama.cpp /app && \
    cd /app && \
    if [ "${LLAMA_CPP_TAG}" != "master" ]; then \
        git checkout "${LLAMA_CPP_TAG}"; \
    else \
        echo "WARNING: LLAMA_CPP_TAG not pinned; building master"; \
    fi && \
    cmake -B build \
        -DBUILD_SHARED_LIBS=OFF \
        -DGGML_RPC=ON \
        -DGGML_CUDA=OFF \
        -DLLAMA_CURL=OFF \
        -DCMAKE_BUILD_TYPE=Release && \
    cmake --build build --config Release -j$(nproc)

WORKDIR /app
ENTRYPOINT ["/app/build/bin/llama-server"]