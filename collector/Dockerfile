FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (build tools for mavlink if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY collector/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY collector/ /app/collector/
COPY .env.example /app/.env

ENV PYTHONPATH=/app

CMD ["python", "collector/main.py"]
