FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ui ./ui
RUN cd ui && npm install && npm run build
COPY app ./app
COPY data ./data
COPY scripts ./scripts
COPY eval ./eval
COPY pipelines ./pipelines
ENV SAFESYNC_DB=/app/safesync.db
ENV SAFESYNC_USE_LLM=1
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
