# Satu image untuk API dan worker; perintah yang dijalankan ditentukan di docker-compose.yml.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependensi di-install dulu, terpisah dari kode: jika hanya kode yang berubah,
# layer dependensi diambil dari cache dan build jauh lebih cepat.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ai ./ai
COPY app ./app
COPY worker ./worker
COPY data ./data

# Jangan menjalankan aplikasi sebagai root.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
