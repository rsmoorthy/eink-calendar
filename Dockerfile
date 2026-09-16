FROM python:3.11-slim-bookworm

# Install minimal system dependencies for fonts, complex text shaping (Raqm/HarfBuzz), and network
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    fonts-dejavu-core \
    libraqm0 \
    libfribidi0 \
    libharfbuzz0b \
    sqlite3 \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Set timezone to Asia/Kolkata (IST)
ENV TZ=Asia/Kolkata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY server /app/server

EXPOSE 8080

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8080"]
