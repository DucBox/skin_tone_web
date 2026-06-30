ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive
ARG http_proxy
ARG https_proxy
ARG PIP_INDEX_URL
ARG PIP_EXTRA_INDEX_URL
ARG PIP_TRUSTED_HOST

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/mplconfig \
    APP_TEST_MODE=0 \
    PORT=8080 \
    http_proxy=${http_proxy} \
    https_proxy=${https_proxy} \
    HTTP_PROXY=${http_proxy} \
    HTTPS_PROXY=${https_proxy}

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgomp1 \
    libgl1 \
    libx11-6 \
    libxcb1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN if [ -n "${PIP_INDEX_URL}" ]; then python -m pip config set global.index-url "${PIP_INDEX_URL}"; fi \
    && if [ -n "${PIP_EXTRA_INDEX_URL}" ]; then python -m pip config set global.extra-index-url "${PIP_EXTRA_INDEX_URL}"; fi \
    && if [ -n "${PIP_TRUSTED_HOST}" ]; then python -m pip config set global.trusted-host "${PIP_TRUSTED_HOST}"; fi \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY start.sh ./start.sh

EXPOSE 8080

CMD ["sh", "./start.sh"]
