FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY sim/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY sim/ /app/sim/

ENV PYTHONPATH=/app

CMD ["python", "sim/drone_simulator.py"]
