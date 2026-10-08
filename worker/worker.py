"""Worker batch: mengambil item dari antrian Redis dan memeriksanya satu per satu.

Menjalankan:  python -m worker.worker
Untuk memproses lebih cepat, jalankan beberapa worker sekaligus (scale horizontal):
  docker compose up --scale worker=3
"""
import logging
import signal
import time

import redis

from ai.factory import build_pipeline
from ai.policies import compute_policy_version
from app.core.config import get_settings
from app.core.logging import request_id_var, setup_logging
from app.db.session import init_db, make_session_factory
from app.services.batch_service import QUEUE_KEY, process_one
from app.services.check_service import CheckService

log = logging.getLogger("worker")
_running = True


def _stop(*_):
    global _running
    _running = False   # selesaikan item yang sedang diproses, lalu berhenti


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    if not settings.redis_url:
        raise SystemExit("REDIS_URL kosong: worker batch membutuhkan Redis (jalankan lewat docker compose).")
    session_factory = make_session_factory(settings.database_url)
    init_db(session_factory)
    service = CheckService(session_factory, build_pipeline(settings), compute_policy_version(settings.policies_dir))
    r = redis.Redis.from_url(settings.redis_url)
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    log.info("worker siap", extra={"queue": QUEUE_KEY})

    while _running:
        try:
            popped = r.brpop(QUEUE_KEY, timeout=5)    # menunggu maksimal 5 detik, lalu cek _running
        except redis.RedisError as e:
            log.warning("redis tidak tersedia, coba lagi", extra={"error": repr(e)})
            time.sleep(2)
            continue
        if popped is None:
            continue
        item_id = popped[1].decode()
        request_id_var.set(f"batch-{item_id[:8]}")
        try:
            status = process_one(item_id, session_factory, service, r)
            log.info("item diproses", extra={"item_id": item_id, "status": status})
        except Exception:
            log.exception("gagal memproses item", extra={"item_id": item_id})
            time.sleep(1)
    log.info("worker berhenti")


if __name__ == "__main__":
    main()
