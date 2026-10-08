"""Endpoint pemeriksaan listing dan review moderator.

Handler ditulis sebagai 'def' biasa (bukan 'async def'). FastAPI menjalankannya di
thread pool, sehingga panggilan LLM yang lama tidak memblokir request lain.
"""
import json

from fastapi import APIRouter, Depends, Query, Request

from ai.types import Listing
from app.db.models import Check
from app.schemas.api import CheckDetailOut, CheckOut, ListingIn, ReviewIn, ReviewOut, Versions
from app.services.check_service import CheckService
from app.api.deps import get_check_service, require_api_key

router = APIRouter(prefix="/v1", tags=["checks"])


def to_out(c: Check) -> CheckOut:
    return CheckOut(check_id=c.id, listing_id=c.listing_id, decision=c.decision,
                    violations=c.violations, review_reason=c.review_reason, decided_by=c.decided_by,
                    versions=Versions(policy=c.policy_version, prompt=c.prompt_version, model=c.model),
                    cached=c.cached, latency_ms=c.latency_ms, created_at=c.created_at)


def ai_suggestions(c: Check) -> list[dict]:
    """Pelanggaran yang diduga AI tetapi tidak dipakai untuk reject otomatis (confidence di bawah threshold).

    Diambil dari output mentah LLM yang SUDAH lolos validator (ditandai dengan verdict terisi),
    sehingga pasal dan kutipannya dijamin ada. Ditampilkan ke moderator sebagai bahan pertimbangan.
    """
    if c.decision != "needs_review" or c.verdict != "violating" or not c.llm_raw_output:
        return []
    try:
        return json.loads(c.llm_raw_output).get("violations", [])
    except (ValueError, AttributeError):
        return []


def to_detail(c: Check, final_decision: str | None) -> CheckDetailOut:
    return CheckDetailOut(**to_out(c).model_dump(), input=c.input, rule_hits=c.rule_hits,
                          retrieved_policy_ids=c.retrieved_policy_ids, confidence=c.confidence,
                          verdict=c.verdict, ai_suggestions=ai_suggestions(c),
                          llm_errors=c.llm_errors, reviewed=final_decision is not None,
                          final_decision=final_decision)


@router.post("/checks", response_model=CheckOut)
def create_check(body: ListingIn, svc: CheckService = Depends(get_check_service)) -> CheckOut:
    return to_out(svc.check(Listing(**body.model_dump())))


@router.get("/checks", response_model=list[CheckDetailOut])
def list_checks(decision: str | None = Query(default=None, pattern="^(approve|reject|needs_review)$"),
                unreviewed: bool = False, limit: int = Query(default=50, ge=1, le=500),
                order: str = Query(default="oldest", pattern="^(oldest|newest)$"),
                svc: CheckService = Depends(get_check_service)) -> list[CheckDetailOut]:
    """oldest = antrian (yang paling lama menunggu di atas); newest = riwayat."""
    return [to_detail(c, final) for c, final in
            svc.list_checks(decision, unreviewed, limit, newest_first=(order == "newest"))]


@router.get("/checks/{check_id}", response_model=CheckDetailOut)
def get_check(check_id: str, svc: CheckService = Depends(get_check_service)) -> CheckDetailOut:
    c, final = svc.get(check_id)
    return to_detail(c, final)


@router.post("/checks/{check_id}/review", response_model=ReviewOut, status_code=201)
def review_check(check_id: str, body: ReviewIn, svc: CheckService = Depends(get_check_service)) -> ReviewOut:
    r = svc.review(check_id, body.moderator_id, body.final_decision, body.policy_ids, body.note)
    return ReviewOut(review_id=r.id, check_id=r.check_id, final_decision=r.final_decision,
                     policy_ids=r.policy_ids, created_at=r.created_at)


@router.get("/policies")
def list_policies(request: Request, _: str = Depends(require_api_key)) -> list[dict]:
    """Daftar pasal kebijakan (ID dan judul), dipakai dashboard saat moderator menolak listing."""
    return [{"policy_id": c.policy_id, "title": c.title} for c in request.app.state.policies]


@router.get("/stats")
def stats(svc: CheckService = Depends(get_check_service)) -> dict:
    return svc.stats()
