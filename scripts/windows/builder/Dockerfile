# FILE: scripts/windows/builder/Dockerfile
FROM debian:bookworm-slim

# Install the MinGW-w64 cross-compiler, git, make, and unzip.
# These are the tools required to build a Windows DLL from source on Linux.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        make \
        unzip \
        gcc-mingw-w64-x86-64 \
        gcc-mingw-w64-i686 \
        gcc-mingw-w64-aarch64 \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build