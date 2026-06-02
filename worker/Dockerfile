# Stage 1: Build
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    pandoc \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    lmodern \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Предзагрузка модели Whisper
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3', device='cpu', compute_type='int8')"

# Stage 2: Runtime
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /usr/local/lib/python3.11/site-packages/faster_whisper /usr/local/lib/python3.11/site-packages/faster_whisper
COPY --from=builder /usr/share/texlive /usr/share/texlive
COPY --from=builder /usr/share/fonts /usr/share/fonts

COPY . worker/

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "-m", "worker"]
