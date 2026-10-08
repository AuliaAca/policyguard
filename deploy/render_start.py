"""Titik masuk container untuk deploy satu service (misalnya Render free tier).

Di dalam satu container:
  - API (FastAPI)  berjalan di 127.0.0.1:8000  -> hanya bisa diakses dari dalam container
  - Dashboard      berjalan di 0.0.0.0:$PORT   -> satu-satunya port yang terbuka ke internet

Kenapa satu container: free tier memberi satu instance kecil per service, dan dengan cara ini
API tidak terbuka ke publik sama sekali (lihat ADR-019). Filesystem free tier bersifat sementara,
sehingga database SQLite kosong setiap kali server bangun; jika SEED_DEMO=true, listing contoh
dari dev set dikirim ulang otomatis.

Environment variable yang dibaca:
  PORT                 port publik (diisi oleh platform; default 10000)
  SERVICE_API_KEYS     wajib; key pertama dipakai dashboard untuk memanggil API
  DASHBOARD_PASSWORD   wajib untuk deploy publik; mengunci dashboard dengan password
  SEED_DEMO            "true" untuk mengisi listing contoh saat start
  SEED_DEMO_N          jumlah listing contoh (default 40)
"""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
API_URL = "http://127.0.0.1:8000"


def log(msg: str) -> None:
    print(f"[start] {msg}", flush=True)


def main() -> int:
    keys = [k.strip() for k in os.environ.get("SERVICE_API_KEYS", "").split(",") if k.strip()]
    if not keys:
        sys.exit("[start] SERVICE_API_KEYS kosong. Isi di pengaturan environment platform.")
    if not os.environ.get("DASHBOARD_PASSWORD"):
        log("PERINGATAN: DASHBOARD_PASSWORD kosong, dashboard bisa dibuka siapa pun yang tahu alamatnya.")

    port = os.environ.get("PORT", "10000")
    env = {**os.environ, "POLICYGUARD_API_URL": API_URL, "POLICYGUARD_API_KEY": keys[0]}

    api = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                            "--port", "8000"], cwd=ROOT, env=env)
    for _ in range(120):
        if api.poll() is not None:
            sys.exit("[start] API gagal start. Lihat log di atas.")
        try:
            if httpx.get(f"{API_URL}/health", timeout=2).status_code < 500:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    else:
        api.kill()
        sys.exit("[start] API tidak merespons dalam 60 detik.")
    log("API siap di 127.0.0.1:8000")

    if os.environ.get("SEED_DEMO", "").lower() == "true":
        n = os.environ.get("SEED_DEMO_N", "40")
        log(f"mengisi {n} listing contoh dari dev set")
        subprocess.run([sys.executable, "scripts/seed_demo.py", "--url", API_URL, "--key", keys[0], "--n", n,
                        "--quiet"], cwd=ROOT, env=env, check=False)

    dashboard = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py", "--server.port", port, "--server.address", "0.0.0.0"],
        cwd=ROOT / "dashboard", env=env)
    log(f"dashboard berjalan di port {port}")

    def stop(*_):
        for p in (dashboard, api):
            if p.poll() is None:
                p.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    # Jika salah satu proses mati, matikan yang lain supaya platform me-restart container.
    while api.poll() is None and dashboard.poll() is None:
        time.sleep(1)
    stop()
    for p in (dashboard, api):
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
    return 1


if __name__ == "__main__":
    sys.exit(main())
