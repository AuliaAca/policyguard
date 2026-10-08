"""Perhitungan metrik evaluasi. Fungsi murni: input daftar hasil, output angka.

Definisi (sama dengan docs/problem_statement.md):
- Recall pelanggaran : dari listing melanggar, berapa yang TIDAK lolos (reject atau needs_review)
- Precision reject   : dari listing yang di-reject otomatis, berapa yang memang melanggar
- Automation rate    : berapa persen listing diputuskan tanpa moderator
- Salah tolak        : dari listing patuh, berapa yang di-reject otomatis
- Pasal tepat        : dari reject yang benar, berapa yang mengutip minimal satu pasal yang benar
- Retrieval recall   : dari listing melanggar, berapa yang semua pasal benarnya ikut terambil
"""
from collections import Counter, defaultdict
from dataclasses import dataclass


@dataclass
class Result:
    id: str
    gold_label: str                  # compliant / violating
    gold_policies: list[str]
    insufficient_info: bool
    test_tag: str
    decision: str                    # approve / reject / needs_review
    decided_by: str
    review_reason: str | None
    pred_policies: list[str]
    retrieved_policies: list[str]
    verdict: str | None
    confidence: float | None
    soft_hit: bool
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def _percentile(values: list[int], p: float) -> int | None:
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p * (len(s) - 1))))]


def compute(results: list[Result], price_in_per_1m: float | None = None,
            price_out_per_1m: float | None = None) -> dict:
    violating = [r for r in results if r.gold_label == "violating"]
    compliant = [r for r in results if r.gold_label == "compliant"]
    rejects = [r for r in results if r.decision == "reject"]
    caught = [r for r in violating if r.decision in ("reject", "needs_review")]
    correct_rejects = [r for r in rejects if r.gold_label == "violating"]

    per_policy = {}
    totals, hits = Counter(), Counter()
    for r in violating:
        for p in set(r.gold_policies):
            totals[p] += 1
            hits[p] += r.decision in ("reject", "needs_review")
    for p in sorted(totals):
        per_policy[p] = {"n": totals[p], "recall": _ratio(hits[p], totals[p])}

    retrieval_scope = [r for r in violating if r.retrieved_policies]
    retrieval_ok = [r for r in retrieval_scope if set(r.gold_policies) <= set(r.retrieved_policies)]

    insuf = [r for r in results if r.insufficient_info]
    by_tag = defaultdict(lambda: [0, 0])
    for r in results:
        ok = (r.decision in ("reject", "needs_review")) if r.gold_label == "violating" else (r.decision != "reject")
        by_tag[r.test_tag][0] += ok
        by_tag[r.test_tag][1] += 1

    total_in = sum(r.prompt_tokens for r in results)
    total_out = sum(r.completion_tokens for r in results)
    cost_per_1k = None
    if price_in_per_1m is not None and price_out_per_1m is not None and results:
        cost = total_in / 1e6 * price_in_per_1m + total_out / 1e6 * price_out_per_1m
        cost_per_1k = round(cost / len(results) * 1000, 4)

    latencies = [r.latency_ms for r in results]
    return {
        "n": len(results),
        "n_violating": len(violating),
        "n_compliant": len(compliant),
        "violation_recall": _ratio(len(caught), len(violating)),
        "missed_violations": [r.id for r in violating if r.decision == "approve"],
        "reject_precision": _ratio(len(correct_rejects), len(rejects)),
        "false_rejects": [r.id for r in compliant if r.decision == "reject"],
        "automation_rate": _ratio(sum(r.decision != "needs_review" for r in results), len(results)),
        "decisions": dict(Counter(r.decision for r in results)),
        "review_reasons": dict(Counter(r.review_reason for r in results if r.review_reason)),
        "policy_match_on_correct_rejects": _ratio(
            sum(bool(set(r.pred_policies) & set(r.gold_policies)) for r in correct_rejects), len(correct_rejects)),
        "retrieval_recall": _ratio(len(retrieval_ok), len(retrieval_scope)),
        "insufficient_info_handled": _ratio(sum(r.decision != "reject" for r in insuf), len(insuf)),
        "per_policy_recall": per_policy,
        "correct_rate_by_tag": {t: {"n": n, "correct": _ratio(ok, n)} for t, (ok, n) in sorted(by_tag.items())},
        "latency_ms_p50": _percentile(latencies, 0.5),
        "latency_ms_p95": _percentile(latencies, 0.95),
        "tokens_prompt_total": total_in,
        "tokens_completion_total": total_out,
        "cost_per_1000_listings": cost_per_1k,
    }


def threshold_sweep(results: list[Result], thresholds: list[float]) -> list[dict]:
    """Simulasi ulang keputusan router untuk berbagai threshold, TANPA memanggil LLM lagi.

    Hanya berlaku untuk listing yang keputusannya ditentukan oleh confidence LLM.
    Listing hard-rule dan fallback tidak berubah karena tidak bergantung pada threshold.
    """
    from ai.router import Thresholds, route
    from ai.types import RuleHit
    from ai.validator import JudgeOutput, ViolationOut

    rows = []
    for t in thresholds:
        sim = []
        for r in results:
            if r.verdict is None:          # rule atau fallback: keputusan tetap
                sim.append(r)
                continue
            out = JudgeOutput(verdict=r.verdict, confidence=r.confidence,
                              violations=[ViolationOut(policy_id=p, evidence="-", reason="-") for p in r.pred_policies]
                              if r.verdict == "violating" else [])
            hits = [RuleHit("-", "-", "soft")] if r.soft_hit else []
            routed = route(retrieval_ok=True, llm_ok=True, output=out, rule_hits=hits, t=Thresholds(t, t))
            sim.append(Result(**{**r.__dict__, "decision": routed.decision}))
        m = compute(sim)
        rows.append({"threshold": t, "violation_recall": m["violation_recall"],
                     "reject_precision": m["reject_precision"], "automation_rate": m["automation_rate"],
                     "false_rejects": len(m["false_rejects"]), "missed": len(m["missed_violations"])})
    return rows
