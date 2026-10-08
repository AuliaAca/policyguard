"""Struktur data yang dipakai bersama oleh seluruh pipeline AI.

Sengaja berupa dataclass sederhana tanpa ketergantungan ke FastAPI atau database,
supaya pipeline bisa dipakai dari API, worker, maupun script evaluasi.
"""
from dataclasses import dataclass, field
from typing import Literal

DecisionType = Literal["approve", "reject", "needs_review"]
DecidedBy = Literal["rule", "llm", "fallback"]
ReviewReason = Literal[
    "low_confidence",
    "insufficient_info",
    "rule_llm_disagree",
    "rule_soft_hit",          # hanya dipakai mode rules_only (baseline)
    "llm_unavailable",
    "invalid_llm_output",
    "retrieval_unavailable",
]


@dataclass(frozen=True)
class Listing:
    listing_id: str
    title: str
    description: str
    category: str
    price: int

    @property
    def text(self) -> str:
        """Teks yang dinilai: judul + deskripsi."""
        return f"{self.title}\n{self.description}".strip()


@dataclass(frozen=True)
class RuleHit:
    term: str
    policy_id: str
    kind: Literal["hard", "soft"]


@dataclass(frozen=True)
class PolicyChunk:
    policy_id: str
    title: str
    text: str


@dataclass(frozen=True)
class Violation:
    policy_id: str
    evidence: str
    reason: str


@dataclass
class Decision:
    decision: DecisionType
    decided_by: DecidedBy
    review_reason: ReviewReason | None = None
    violations: list[Violation] = field(default_factory=list)
    rule_hits: list[RuleHit] = field(default_factory=list)
    retrieved_policy_ids: list[str] = field(default_factory=list)
    verdict: str | None = None              # verdict LLM yang lolos validasi
    confidence: float | None = None
    llm_raw_output: str | None = None
    llm_errors: list[str] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_calls: int = 0
