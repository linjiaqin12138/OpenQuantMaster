FROM mcr.microsoft.com/devcontainers/python:3.12-bookworm

ARG TA_LIB_VERSION=0.6.4

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl ca-certificates \
    && curl -fsSL "https://github.com/TA-Lib/ta-lib/releases/download/v${TA_LIB_VERSION}/ta-lib-${TA_LIB_VERSION}-src.tar.gz" -o /tmp/ta-lib.tar.gz \
    && tar -xzf /tmp/ta-lib.tar.gz -C /tmp \
    && cd "/tmp/ta-lib-${TA_LIB_VERSION}" \
    && ./configure --prefix=/usr \
    && make -j"$(nproc)" \
    && make install \
    && ldconfig \
    && rm -rf /tmp/ta-lib* /var/lib/apt/lists/*

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && chown -R vscode:vscode /opt/venv

ENV PATH="/opt/venv/bin:${PATH}"
