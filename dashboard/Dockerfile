# Image terpisah untuk dashboard, agar image API tidak ikut membawa Streamlit (ukurannya besar).
# Di-build dari root project: lihat docker-compose.yml (context: ., dockerfile: dashboard/Dockerfile).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /dashboard

COPY requirements-dashboard.txt .
RUN pip install --no-cache-dir -r requirements-dashboard.txt

COPY dashboard/ .

RUN useradd --create-home appuser
USER appuser

EXPOSE 8501
# Tema, font, dan mode headless dibaca dari .streamlit/config.toml yang ikut tersalin.
CMD ["streamlit", "run", "app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
