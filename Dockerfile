FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BACKEND_URL=http://127.0.0.1:8000 \
    DASH_HOST=0.0.0.0 \
    DASH_PORT=8050

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY README.md .

EXPOSE 8000 8050

CMD ["bash", "-c", "set -e; uvicorn app.main:app --host 0.0.0.0 --port 8000 & backend_pid=$!; python -m app.ui & ui_pid=$!; trap 'kill $backend_pid $ui_pid 2>/dev/null || true' TERM INT EXIT; wait -n $backend_pid $ui_pid"]
