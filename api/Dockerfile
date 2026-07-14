FROM python:3.10-bookworm

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    pkg-config \
    ffmpeg \
    libsndfile1 \
    libsndfile1-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

# Demucs 4 has older transitive packaging metadata. Keeping pip below 24.1
# avoids modern pip rejecting those legacy dependency versions.
RUN python -m pip install --upgrade "pip<24.1" setuptools wheel \
    && python -m pip install -r requirements.txt

COPY . .
RUN mkdir -p /app/data/jobs

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
