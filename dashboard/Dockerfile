# Streamlit forecasting dashboard over the Postgres warehouse.
# Separate image from the dagster/api image: this one carries the heavier
# scientific stack (statsmodels, scikit-learn, scipy) and nothing else.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /opt/dashboard

# libgomp1: OpenMP runtime that scikit-learn wheels need on Debian slim.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3).read()==b'ok' else 1)"

CMD ["streamlit", "run", "📈_Forecast_Studio.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
