# German economy macro dashboard: FastAPI (curated data API) + static D3 frontend.
# Light, single-purpose image — just FastAPI/uvicorn/psycopg and the static
# dashboard files; no dagster/dbt/scientific stack.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /opt/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8084

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8084/health', timeout=3).read()==b'{\"status\":\"ok\"}' else 1)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8084"]
