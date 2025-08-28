FROM python:3.11-slim

# Çalışma dizinini ayarla
WORKDIR /app

# Gerekli sistem paketlerini yükle
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Requirements dosyasını kopyala ve bağımlılıkları yükle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama kodunu kopyala
COPY src/ ./src/
COPY config/ ./config/
COPY utils/ ./utils/
COPY scripts/ ./scripts/
COPY static/ ./static/
COPY tests/ ./tests/
COPY conftest.py .

# Statik dosyalar ve veritabanı için dizinler oluştur
RUN mkdir -p /app/static /app/data

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    API_HOST=0.0.0.0 \
    API_PORT=8010 \
    LIBRARY_DB_FILE=/app/data/library.db

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8010/health || exit 1

# Port 8010'u aç
EXPOSE 8010

# Uygulamayı başlat
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8010"]
