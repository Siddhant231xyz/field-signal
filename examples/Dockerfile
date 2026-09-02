FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        coreutils \
        curl \
        file \
        unzip \
        zip \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /packet /work /output
WORKDIR /work

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt

COPY ingest_agent.py /app/ingest_agent.py
COPY container_agent.py /app/container_agent.py

# The host starts this image as root intentionally. Root remains inside the
# container; the runner never enables privileged mode or mounts Docker itself.
ENTRYPOINT ["python", "/app/container_agent.py"]
