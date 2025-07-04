FROM debian:bookworm-slim


RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        build-essential \
        gcc \
        libssl-dev \
        pkg-config \
        git \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain 1.85.0

ENV PATH="/root/.cargo/bin:${PATH}"

RUN cargo build --release
    cargo run --release 