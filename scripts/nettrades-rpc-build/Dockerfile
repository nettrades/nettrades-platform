# File: scripts/nettrades-rpc-build/Dockerfile
#
# SPDX-License-Identifier: BUSL-1.1 OR LicenseRef-NETTRADES-Commercial
# Copyright (c) 2026 NETTRADES LIMITED (UK Company No. 08160657). Patent Pending. All rights reserved.
# Licensed under LICENSE.txt (BUSL-1.1 -> Open RAIL-S) and strictly conditioned
# upon compliance with ETHICAL-STATEMENT.md. See also LEGAL/IP-AND-PATENTS.md.
# THE FUTURE OF WORK is a registered trade mark in the United Kingdom (No. UK00004257743) of NETTRADES LIMITED.
# Distributed WITHOUT ANY WARRANTY.

FROM nvidia/cuda:12.4.1-devel-ubuntu22.04

# Install build dependencies. The CUDA base image is kept because it is
# already cached, but we do NOT compile CUDA into the master — see below.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git cmake build-essential libssl-dev curl ca-certificates libcurl4-openssl-dev && \
    rm -rf /var/lib/apt/lists/*

# Build llama-server with RPC and CPU backends, STATICALLY linked.
#
# Why static:
#   Modern llama.cpp loads backends dynamically at runtime via
#   ggml_backend_load_all(), which expects GGML_BACKEND_PATH to point at
#   specific .so files (not a directory). Getting the directory scanning
#   to work is brittle across versions, and we already burned a full
#   rebuild cycle discovering that GGML_BACKEND_PATH=/app/build/bin is
#   interpreted as a file (EISDIR error).
#
#   With BUILD_SHARED_LIBS=OFF, the RPC and CPU backend code is
#   compiled directly into libggml.a, and llama-server links that
#   statically. The backends are available at startup with zero
#   environment configuration. ggml_backend_load_all() iterates the
#   compiled-in registry and finds them.
#
# Why no CUDA:
#   The RPC master coordinates — it does not do local GPU inference.
#   All actual compute happens on the RPC workers (AMD in this demo).
#   The V100's GPUs are used for vLLM on port 8001 (Claim 3), which is a
#   separate code path. Adding CUDA to the master brings in a 600 MB
#   shared library, a 20-minute build, and the stub driver warning on
#   every start — all for a feature the master never uses.
#
#   If a future requirement needs local CUDA on the master, add
#   -DGGML_CUDA=ON and switch back to shared libs, but be prepared to
#   solve the GGML_BACKEND_PATH directory issue documented above.
RUN git clone --depth 1 https://github.com/ggml-org/llama.cpp /app && \
    cd /app && \
    cmake -B build \
        -DBUILD_SHARED_LIBS=OFF \
        -DGGML_RPC=ON \
        -DGGML_CUDA=OFF \
        -DLLAMA_CURL=OFF \
        -DCMAKE_BUILD_TYPE=Release && \
    cmake --build build --config Release -j$(nproc)

WORKDIR /app
ENTRYPOINT ["/app/build/bin/llama-server"]
