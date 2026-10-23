FROM python:3.11-slim
LABEL org.opencontainers.image.licenses="Apache-2.0"
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY locustfile.py listener.py ./
# Idle container; niyan-api starts Locust via docker exec for each run.
CMD ["sleep", "infinity"]
