FROM python:3.11-slim
LABEL org.opencontainers.image.licenses="Apache-2.0"
ARG NIYAN_PLATFORM=vm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN printf 'PLATFORM = "vm"\n' > app/_build_platform.py
EXPOSE 8100
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
