# FILE: scripts/windows/builder/Dockerfile
FROM golang:1.26-bookworm

# Install the MinGW-w64 cross-compiler, git, make, unzip.
# The official golang image already provides the Go toolchain on PATH,
# so we do NOT install Debian's golang-go (which is Go 1.19 on bookworm).
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        make \
        unzip \
        gcc-mingw-w64-x86-64 \
        gcc-mingw-w64-i686 \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build