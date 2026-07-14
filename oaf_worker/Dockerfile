FROM --platform=linux/amd64 python:3.8-slim-bullseye

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    unzip \
    ffmpeg \
    libsndfile1 \
    build-essential \
    libasound2-dev \
    libjack-jackd2-dev \
    portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /worker
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade "pip<24.1" setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

COPY worker.py checkpoint.py ./
EXPOSE 8011

CMD ["python", "worker.py"]
