FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ELAN_HOME=/root/.elan \
    PATH="/root/.elan/bin:${PATH}"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSf https://elan.lean-lang.org/elan-init.sh | sh -s -- -y

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY lean_workspace/lean-toolchain /app/lean_workspace/lean-toolchain
COPY lean_workspace/lakefile.toml /app/lean_workspace/lakefile.toml
COPY lean_workspace/lake-manifest.json /app/lean_workspace/lake-manifest.json
RUN cd /app/lean_workspace \
    && elan toolchain install "$(cat lean-toolchain)" \
    && elan override set "$(cat lean-toolchain)" \
    && lake update

COPY lean_workspace /app/lean_workspace
RUN cd /app/lean_workspace \
    && elan override set "$(cat lean-toolchain)" \
    && lake build LeanEcon

COPY . .

CMD ["sh", "-c", "uvicorn src.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
