"""Decision router: tabel keputusan dari system_design.md bagian 2 (baris 2-10).

Baris 1 (rule hard hit) ditangani lebih awal di pipeline supaya LLM tidak perlu dipanggil.
Semua logika di sini kode biasa: AI hanya memberi 'pendapat', kebijakan bisnis yang memutuskan.
"""
from dataclasses import dataclass

from ai.types import DecidedBy, DecisionType, ReviewReason, RuleHit, Violation
from ai.validator import JudgeOutput


@dataclass(frozen=True)
class Thresholds:
    reject: float    # T_REJECT
    approve: float   # T_APPROVE


@dataclass(frozen=True)
class RouteResult:
    decision: DecisionType
    decided_by: DecidedBy
    review_reason: ReviewReason | None
    violations: list[Violation]


def route(*, retrieval_ok: bool, llm_ok: bool, output: JudgeOutput | None,
          rule_hits: list[RuleHit], t: Thresholds) -> RouteResult:
    review = lambda reason, by="llm": RouteResult("needs_review", by, reason, [])

    if not retrieval_ok:                                   # baris 2
        return review("retrieval_unavailable", "fallback")
    if not llm_ok:                                         # baris 3
        return review("llm_unavailable", "fallback")
    if output is None:                                     # baris 4
        return review("invalid_llm_output", "fallback")
    if output.verdict == "insufficient_info":              # baris 5
        return review("insufficient_info")

    if output.verdict == "violating":
        if output.confidence >= t.reject:                  # baris 6
            violations = [Violation(v.policy_id, v.evidence, v.reason) for v in output.violations]
            return RouteResult("reject", "llm", None, violations)
        return review("low_confidence")                    # baris 7

    # verdict == "compliant"
    if any(h.kind == "soft" for h in rule_hits):           # baris 8
        return review("rule_llm_disagree")
    if output.confidence >= t.approve:                     # baris 9
        return RouteResult("approve", "llm", None, [])
    return review("low_confidence")                        # baris 10
