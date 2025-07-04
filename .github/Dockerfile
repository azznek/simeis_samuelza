FROM debian:bookworm-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY target/release/simeis-server-*.deb /tmp/simeis.deb

RUN apt-get update && apt-get install -y /tmp/simeis.deb || apt-get -f install -y && \
    rm -rf /var/lib/apt/lists/*

CMD ["simeis-server"]
