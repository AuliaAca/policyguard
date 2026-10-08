"""Kontrak API (system_design.md bagian 1). Validasi input terjadi di sini,
SEBELUM ada kode lain yang berjalan. Input yang gagal di sini tidak pernah sampai ke LLM."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_DESCRIPTION_CHARS = 5000   # ADR-005: batas di kontrak, tanpa pemotongan diam-diam

CATEGORIES = (
    "Kesehatan", "Hewan", "Olahraga & Outdoor", "Fashion Pria", "Fashion Wanita",
    "Makanan & Minuman", "Kecantikan", "Hobi", "Jasa", "Voucher & Top Up", "Film & Musik",
    "Buku", "Perlengkapan Rumah", "Mainan & Hobi", "Elektronik", "Kerajinan",
)


class ListingIn(BaseModel):
    listing_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(default="", max_length=MAX_DESCRIPTION_CHARS)
    category: str
    price: int = Field(gt=0, description="Harga dalam Rupiah")

    @field_validator("category")
    @classmethod
    def _known_category(cls, v: str) -> str:
        if v not in CATEGORIES:
            raise ValueError(f"kategori tidak dikenal; pilihan: {', '.join(CATEGORIES)}")
        return v


class ViolationOut(BaseModel):
    policy_id: str
    evidence: str
    reason: str


class Versions(BaseModel):
    policy: str
    prompt: str
    model: str


class CheckOut(BaseModel):
    check_id: str
    listing_id: str
    decision: Literal["approve", "reject", "needs_review"]
    violations: list[ViolationOut]
    review_reason: str | None
    decided_by: Literal["rule", "llm", "fallback"]
    versions: Versions
    cached: bool
    latency_ms: int
    created_at: datetime


class CheckDetailOut(CheckOut):
    """Untuk moderator dan debugging: termasuk input dan jejak AI."""
    input: dict
    rule_hits: list[dict]
    retrieved_policy_ids: list[str]
    confidence: float | None
    verdict: str | None = None                                  # verdict AI yang lolos validasi
    ai_suggestions: list[ViolationOut] = Field(default_factory=list)  # dugaan AI saat confidence rendah
    llm_errors: list[str]
    reviewed: bool
    final_decision: str | None = None      # keputusan moderator, jika sudah direview


class ReviewIn(BaseModel):
    moderator_id: str = Field(min_length=1, max_length=64)
    final_decision: Literal["approve", "reject"]
    policy_ids: list[str] = Field(default_factory=list)
    note: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def _reject_needs_policy(self):
        # Sama seperti keputusan otomatis: penolakan harus bisa diaudit, jadi wajib menyebut pasal.
        if self.final_decision == "reject" and not self.policy_ids:
            raise ValueError("keputusan reject wajib menyebut minimal satu policy_id")
        return self


class ReviewOut(BaseModel):
    review_id: str
    check_id: str
    final_decision: str
    policy_ids: list[str]
    created_at: datetime


class BatchIn(BaseModel):
    listings: list[ListingIn] = Field(min_length=1, max_length=1000)


class BatchOut(BaseModel):
    batch_id: str
    status: Literal["processing", "completed"]
    total: int
    pending: int
    done: int
    failed: int
    decisions: dict[str, int]
