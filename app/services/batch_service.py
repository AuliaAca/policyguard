"""Batch: memeriksa banyak listing secara async lewat antrian Redis.

Alur:
  API  : simpan batch + item ke DB -> masukkan ID item ke antrian Redis -> balas 202
  Worker: ambil ID dari antrian -> jalankan CheckService.check -> tandai item done/failed

Antrian sengaja dibuat sederhana dengan Redis list (LPUSH / BRPOP) agar mekanismenya
terlihat jelas. Keterbatasan yang diketahui: item yang sudah diambil worker lalu worker
mati di tengah proses akan hilang dari antrian. Lihat STUDY_GUIDE (bagian keterbatasan).
"""
import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from ai.types import Listing
from app.db import repository as repo
from app.db.models import Batch, BatchItem
from app.services.check_service import CheckService, NotFound, ServiceUnavailable

log = logging.getLogger(__name__)
QUEUE_KEY = "policyguard:batch_items"
MAX_ATTEMPTS = 3


class BatchService:
    def __init__(self, session_factory: sessionmaker, redis_client):
        self._sessions = session_factory
        self._redis = redis_client

    def create(self, listings: list[dict]) -> str:
        try:
            with self._sessions() as s:
                batch = Batch(total=len(listings))
                s.add(batch)
                s.flush()
                items = [BatchItem(batch_id=batch.id, input=l) for l in listings]
                s.add_all(items)
                s.flush()
                try:
                    # Push ke antrian SEBELUM commit: jika Redis mati, batch tidak tersimpan setengah jadi.
                    self._redis.lpush(QUEUE_KEY, *[i.id for i in items])
                except Exception as e:
                    s.rollback()
                    raise ServiceUnavailable(f"antrian tidak tersedia: {e}") from e
                s.commit()
                return batch.id
        except SQLAlchemyError as e:
            raise ServiceUnavailable(str(e)) from e

    def status(self, batch_id: str) -> dict:
        try:
            with self._sessions() as s:
                batch = s.get(Batch, batch_id)
                if batch is None:
                    raise NotFound(batch_id)
                counts, decisions = repo.batch_counts(s, batch_id)
        except SQLAlchemyError as e:
            raise ServiceUnavailable(str(e)) from e
        pending = counts.get("pending", 0)
        return {"batch_id": batch_id, "status": "processing" if pending else "completed",
                "total": batch.total, "pending": pending, "done": counts.get("done", 0),
                "failed": counts.get("failed", 0), "decisions": decisions}


def process_one(item_id: str, session_factory: sessionmaker, check_service: CheckService,
                redis_client) -> str:
    """Memproses satu item. Dipanggil worker. Mengembalikan status akhir item."""
    with session_factory() as s:
        item = s.get(BatchItem, item_id)
        if item is None or item.status != "pending":
            return "skipped"          # item sudah diproses (misalnya ID masuk antrian dua kali)
        item.attempts += 1
        s.commit()
        listing = Listing(**item.input)

    try:
        check = check_service.check(listing)
        status, check_id, error = "done", check.id, None
    except ServiceUnavailable as e:
        # Database bermasalah: kembalikan ke antrian untuk dicoba lagi, sampai batas percobaan.
        if item.attempts < MAX_ATTEMPTS:
            redis_client.lpush(QUEUE_KEY, item_id)
            log.warning("item dikembalikan ke antrian", extra={"item_id": item_id, "error": str(e)})
            return "requeued"
        status, check_id, error = "failed", None, str(e)
    except Exception as e:  # bug tak terduga: tandai gagal, jangan hentikan worker
        log.exception("item gagal diproses", extra={"item_id": item_id})
        status, check_id, error = "failed", None, repr(e)

    with session_factory() as s:
        item = s.get(BatchItem, item_id)
        item.status, item.check_id, item.error = status, check_id, error
        s.commit()
    return status
