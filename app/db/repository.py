"""Semua query database ada di sini, supaya service layer tidak penuh SQL."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Batch, BatchItem, Check, Review


def find_by_idempotency_key(s: Session, listing_id: str, content_hash: str) -> Check | None:
    return s.scalar(select(Check).where(Check.listing_id == listing_id,
                                        Check.content_hash == content_hash))


def find_cached(s: Session, cache_key: str) -> Check | None:
    """Hasil terbaru untuk cache_key yang sama. Hasil fallback tidak pernah dipakai ulang."""
    return s.scalar(select(Check)
                    .where(Check.cache_key == cache_key, Check.decided_by != "fallback")
                    .order_by(Check.created_at.desc()).limit(1))


def get_check(s: Session, check_id: str) -> Check | None:
    return s.get(Check, check_id)


def list_checks(s: Session, decision: str | None, unreviewed: bool, limit: int,
                newest_first: bool = False) -> list[Check]:
    # Antrian review: yang paling lama menunggu di atas (FIFO). Riwayat: yang terbaru di atas.
    order = Check.created_at.desc() if newest_first else Check.created_at.asc()
    q = select(Check).order_by(order).limit(limit)
    if decision:
        q = q.where(Check.decision == decision)
    if unreviewed:
        q = q.where(~select(Review.id).where(Review.check_id == Check.id).exists())
    return list(s.scalars(q))


def final_decisions(s: Session, check_ids: list[str]) -> dict[str, str]:
    """Keputusan moderator terbaru per check, dalam SATU query (bukan satu query per baris)."""
    if not check_ids:
        return {}
    rows = s.execute(select(Review.check_id, Review.final_decision)
                     .where(Review.check_id.in_(check_ids)).order_by(Review.created_at.asc())).all()
    return {cid: dec for cid, dec in rows}       # baris terakhir (terbaru) menimpa yang lama


def stats(s: Session) -> dict:
    def group(col):
        return {k or "-": v for k, v in s.execute(select(col, func.count()).group_by(col)).all()}
    totals = s.execute(select(func.count(), func.avg(Check.latency_ms),
                              func.sum(Check.prompt_tokens), func.sum(Check.completion_tokens))).one()
    return {
        "total_checks": totals[0],
        "avg_latency_ms": round(totals[1] or 0),
        "prompt_tokens": totals[2] or 0,
        "completion_tokens": totals[3] or 0,
        "by_decision": group(Check.decision),
        "by_decided_by": group(Check.decided_by),
        "by_review_reason": group(Check.review_reason),
        "reviews": s.scalar(select(func.count()).select_from(Review)),
    }


def batch_counts(s: Session, batch_id: str) -> tuple[dict[str, int], dict[str, int]]:
    status = dict(s.execute(select(BatchItem.status, func.count())
                            .where(BatchItem.batch_id == batch_id).group_by(BatchItem.status)).all())
    decisions = dict(s.execute(select(Check.decision, func.count())
                               .join(BatchItem, BatchItem.check_id == Check.id)
                               .where(BatchItem.batch_id == batch_id).group_by(Check.decision)).all())
    return status, decisions


__all__ = ["Batch", "BatchItem", "Check", "Review"]
