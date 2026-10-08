"""Menyalakan API dan dashboard sekaligus, tanpa Docker.

Pemakaian (setelah: python scripts/make_env.py local):
    python scripts/run_local.py               # browser terbuka otomatis ke dashboard
    python scripts/run_local.py --no-browser

Hasil:
    API        : http://localhost:8000      (dokumentasi interaktif: http://localhost:8000/docs)
    Dashboard  : http://localhost:8501
Tekan Ctrl+C untuk mematikan keduanya.
"""
import os
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def _stop(*_):
    raise KeyboardInterrupt


def main() -> int:
    # Pastikan Ctrl+C (SIGINT) dan perintah stop (SIGTERM) selalu mematikan API dan dashboard,
    # termasuk saat script dijalankan dari proses lain yang mengabaikan SIGINT.
    signal.signal(signal.SIGINT, _stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _stop)

    if not (ROOT / ".env").exists():
        sys.exit("File .env belum ada. Jalankan dulu: python scripts/make_env.py local")

    env = {**os.environ, "POLICYGUARD_API_URL": "http://localhost:8000"}
    api = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8000"], cwd=ROOT, env=env)

    try:
        for _ in range(60):
            if api.poll() is not None:
                sys.exit("API gagal start. Baca pesan error di atas.")
            try:
                if httpx.get("http://localhost:8000/health", timeout=2).status_code < 500:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        else:
            api.terminate()
            sys.exit("API tidak merespons setelah 30 detik.")
    except KeyboardInterrupt:
        api.terminate()
        return 0

    # Dashboard dijalankan dari folder dashboard/ supaya tema (.streamlit/config.toml) dan font (static/) terbaca.
    dashboard = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py", "--server.port", "8501"], cwd=ROOT / "dashboard", env=env)

    print("\n" + "=" * 60)
    print("  API       : http://localhost:8000/health")
    print("  Docs API  : http://localhost:8000/docs")
    print("  Dashboard : http://localhost:8501")
    print("  Isi data contoh (terminal lain): python scripts/seed_demo.py")
    print("  Tekan Ctrl+C untuk mematikan.")
    print("=" * 60 + "\n")

    try:
        if "--no-browser" not in sys.argv:
            time.sleep(3)
            webbrowser.open("http://localhost:8501")
        while api.poll() is None and dashboard.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in (dashboard, api):
            if p.poll() is None:
                p.terminate()
        for p in (dashboard, api):
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
    print("API dan dashboard dimatikan.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
