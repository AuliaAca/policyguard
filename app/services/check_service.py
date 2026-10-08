"""CheckService: membungkus pipeline AI dengan kebutuhan production.

Urutan untuk setiap listing:
  1. Idempotensi  : request yang sama dari listing yang sama -> kembalikan check yang sudah ada
  2. Cache        : isi + versi sama dari listing lain -> pakai ulang hasilnya (bukan fallback)
  3. Pipeline     : rules -> retrieval -> LLM -> validasi -> router
  4. Simpan       : gagal simpan -> ServiceUnavailable (API mengubahnya jadi 503, ADR-007)
  5. Metrik
"""
import hashlib
import logging
import re
import time
from dataclasses import asdict

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from ai.pipeline import CheckPipeline
from ai.prompts.judge_v1 import PROMPT_VERSION
from ai.types import Listing
from app.core import metrics
from app.db import repository as repo
from app.db.models import Check, Review

log = logging.getLogger(__name__)
_WS = re.compile(r"\s+")


class ServiceUnavailable(Exception):
    """Database tidak bisa diakses; keputusan tidak bisa disimpan."""


class NotFound(Exception):
    pass


def _norm(text: str) -> str:
    return _WS.sub(" ", text).strip().lower()


def content_hash(listing: Listing) -> str:
    # price ikut di-hash karena harga memengaruhi penilaian (contoh: tas bermerek harga janggal).
    raw = "|".join([_norm(listing.title), _norm(listing.description), listing.category, str(listing.price)])
    return hashlib.sha256(raw.encode()).hexdigest()


def cache_key(c_hash: str, policy_version: str, prompt_version: str, model: str) -> str:
    # Versi kebijakan, prompt, dan model ikut di kunci: salah satu berubah -> cache tidak terpakai.
    return hashlib.sha256(f"{c_hash}|{policy_version}|{prompt_version}|{model}".encode()).hexdigest()


class CheckService:
    def __init__(self, session_factory: sessionmaker, pipeline: CheckPipeline, policy_version: str):
        self._sessions = session_factory
        self.pipeline = pipeline
        self.policy_version = policy_version
        self.prompt_version = PROMPT_VERSION if pipeline.config.mode == "llm" else "rules-only"

    def check(self, listing: Listing) -> Check:
        c_hash = content_hash(listing)
        key = cache_key(c_hash, self.policy_version, self.prompt_version, self.pipeline.model_name)
        try:
            with self._sessions() as s:
                existing = repo.find_by_idempotency_key(s, listing.listing_id, c_hash)
                if existing:
                    log.info("idempotent hit", extra={"check_id": existing.id})
                    return existing
                cached = repo.find_cached(s, key)
        except SQLAlchemyError as e:
            raise ServiceUnavailable(str(e)) from e

        start = time.perf_counter()
        if cached:
            record = self._copy_from_cache(cached, listing, c_hash)
        else:
            decision = self.pipeline.run(listing)
            metrics.PIPELINE_LATENCY.observe(time.perf_counter() - start)
            record = Check(
                listing_id=listing.listing_id, content_hash=c_hash, cache_key=key,
                input=asdict(listing), decision=decision.decision, decided_by=decision.decided_by,
                review_reason=decision.review_reason,
                violations=[asdict(v) for v in decision.violations],
                rule_hits=[asdict(h) for h in decision.rule_hits],
                retrieved_policy_ids=decision.retrieved_policy_ids,
                verdict=decision.verdict, confidence=decision.confidence,
                llm_raw_output=decision.llm_raw_output, llm_errors=decision.llm_errors,
                policy_version=self.policy_version, prompt_version=self.prompt_version,
                model=self.pipeline.model_name, prompt_tokens=decision.prompt_tokens,
                completion_tokens=decision.completion_tokens,
            )
            self._record_ai_metrics(decision)
        record.latency_ms = int((time.perf_counter() - start) * 1000)

        saved = self._save(record, listing.listing_id, c_hash)
        metrics.CHECKS.labels(saved.decision, saved.decided_by, str(saved.cached).lower()).inc()
        log.info("check selesai", extra={"check_id": saved.id, "listing_id": saved.listing_id,
                                         "decision": saved.decision, "decided_by": saved.decided_by,
                                         "review_reason": saved.review_reason, "cached": saved.cached,
                                         "latency_ms": saved.latency_ms})
        return saved

    def _copy_from_cache(self, src: Check, listing: Listing, c_hash: str) -> Check:
        fields = ("cache_key", "decision", "decided_by", "review_reason", "violations", "rule_hits",
                  "retrieved_policy_ids", "verdict", "confidence", "llm_raw_output", "llm_errors",
                  "policy_version", "prompt_version", "model")
        rec = Check(listing_id=listing.listing_id, content_hash=c_hash, input=asdict(listing),
                    cached=True, prompt_tokens=0, completion_tokens=0,   # cache tidak memakai token
                    **{f: getattr(src, f) for f in fields})
        return rec

    def _save(self, record: Check, listing_id: str, c_hash: str) -> Check:
        try:
            with self._sessions() as s:
                s.add(record)
                try:
                    s.commit()
                except IntegrityError:
                    # Dua request identik datang bersamaan: yang kalah memakai hasil yang menang.
                    s.rollback()
                    winner = repo.find_by_idempotency_key(s, listing_id, c_hash)
                    if winner is None:
                        raise
                    return winner
                return record
        except SQLAlchemyError as e:
            log.error("gagal menyimpan check", extra={"error": repr(e)})
            raise ServiceUnavailable(str(e)) from e

    @staticmethod
    def _record_ai_metrics(decision) -> None:
        if decision.decided_by == "fallback":
            metrics.FALLBACKS.labels(decision.review_reason or "unknown").inc()
        attempts_invalid = decision.llm_calls - (1 if decision.verdict else 0)
        if attempts_invalid > 0:
            metrics.INVALID_LLM_OUTPUT.inc(attempts_invalid)
        metrics.LLM_TOKENS.labels("prompt").inc(decision.prompt_tokens)
        metrics.LLM_TOKENS.labels("completion").inc(decision.completion_tokens)

    # ---- moderator ----
    def get(self, check_id: str) -> tuple[Check, str | None]:
        """Mengembalikan (check, keputusan moderator atau None jika belum direview)."""
        try:
            with self._sessions() as s:
                c = repo.get_check(s, check_id)
                if c is None:
                    raise NotFound(check_id)
                return c, repo.final_decisions(s, [check_id]).get(check_id)
        except SQLAlchemyError as e:
            raise ServiceUnavailable(str(e)) from e

    def list_checks(self, decision: str | None, unreviewed: bool, limit: int,
                    newest_first: bool = False) -> list[tuple[Check, str | None]]:
        try:
            with self._sessions() as s:
                checks = repo.list_checks(s, decision, unreviewed, limit, newest_first)
                finals = {} if unreviewed else repo.final_decisions(s, [c.id for c in checks])
                return [(c, finals.get(c.id)) for c in checks]
        except SQLAlchemyError as e:
            raise ServiceUnavailable(str(e)) from e

    def review(self, check_id: str, moderator_id: str, final_decision: str, policy_ids: list[str],
               note: str) -> Review:
        try:
            with self._sessions() as s:
                if repo.get_check(s, check_id) is None:
                    raise NotFound(check_id)
                r = Review(check_id=check_id, moderator_id=moderator_id, final_decision=final_decision,
                           policy_ids=policy_ids, note=note)
                s.add(r)
                s.commit()
                return r
        except SQLAlchemyError as e:
            raise ServiceUnavailable(str(e)) from e

    def stats(self) -> dict:
        try:
            with self._sessions() as s:
                return repo.stats(s)
        except SQLAlchemyError as e:
            raise ServiceUnavailable(str(e)) from e
