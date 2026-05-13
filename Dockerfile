FROM python:3.11-slim

# Variables de entorno para Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/home/appuser/.cache/huggingface

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias de Python
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar codigo fuente
COPY src/ ./src/

# Crear usuario no root y ajustar permisos
RUN useradd -m appuser && \
    mkdir -p /home/appuser/.cache/huggingface && \
    chown -R appuser:appuser /app /home/appuser

USER appuser

EXPOSE 8080

CMD ["sh", "-c", "cd src && uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]