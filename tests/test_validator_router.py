import json

from ai.router import Thresholds, route
from ai.types import RuleHit
from ai.validator import JudgeOutput, validate_output
from conftest import judge_json

TEXT = "Kopi herbal, bisa sembuhkan diabetes"
ALLOWED = {"POL-HLT-01", "POL-HLT-02"}


def v(obj):
    return validate_output(json.dumps(obj) if not isinstance(obj, str) else obj, ALLOWED, TEXT)


# ---------- validator ----------
def test_valid_violation():
    out, errors = v(judge_json("violating", [("POL-HLT-01", "sembuhkan diabetes")]))
    assert errors == [] and out.verdict == "violating"


def test_rejects_invented_policy():
    _, errors = v(judge_json("violating", [("POL-WPN-01", "sembuhkan diabetes")]))
    assert any("tidak termasuk pasal" in e for e in errors)


def test_rejects_evidence_not_in_listing():
    _, errors = v(judge_json("violating", [("POL-HLT-01", "menyembuhkan kanker")]))
    assert any("evidence tidak ditemukan" in e for e in errors)


def test_evidence_check_ignores_case_and_spacing():
    out, errors = v(judge_json("violating", [("POL-HLT-01", "Sembuhkan   DIABETES")]))
    assert errors == []


def test_rejects_inconsistent_verdict():
    _, e1 = v(judge_json("violating", []))
    _, e2 = v(judge_json("compliant", [("POL-HLT-01", "sembuhkan diabetes")]))
    assert e1 and e2


def test_rejects_bad_json_and_confidence_range():
    assert v("ini bukan json")[1]
    assert v(judge_json(confidence=1.7))[1]


# ---------- router: satu test per baris tabel keputusan ----------
T = Thresholds(0.8, 0.8)
SOFT = [RuleHit("bir", "POL-ALC-01", "soft")]


def out(verdict, conf, violations=()):
    return JudgeOutput.model_validate(judge_json(verdict, violations, conf))


def r(**kw):
    base = dict(retrieval_ok=True, llm_ok=True, output=None, rule_hits=[], t=T)
    base.update(kw)
    return route(**base)


def test_row2_retrieval_failed():
    res = r(retrieval_ok=False)
    assert (res.decision, res.review_reason, res.decided_by) == ("needs_review", "retrieval_unavailable", "fallback")


def test_row3_llm_unavailable():
    assert r(llm_ok=False).review_reason == "llm_unavailable"


def test_row4_invalid_output():
    assert r(output=None).review_reason == "invalid_llm_output"


def test_row5_insufficient_info():
    assert r(output=out("insufficient_info", 0.9)).review_reason == "insufficient_info"


def test_row6_confident_violation_rejected():
    res = r(output=out("violating", 0.9, [("POL-HLT-01", "x")]))
    assert res.decision == "reject" and res.violations[0].policy_id == "POL-HLT-01"


def test_row7_unsure_violation_to_review():
    assert r(output=out("violating", 0.5, [("POL-HLT-01", "x")])).review_reason == "low_confidence"


def test_row8_soft_hit_disagreement():
    assert r(output=out("compliant", 0.99), rule_hits=SOFT).review_reason == "rule_llm_disagree"


def test_row9_confident_compliant_approved():
    assert r(output=out("compliant", 0.9)).decision == "approve"


def test_row10_unsure_compliant_to_review():
    assert r(output=out("compliant", 0.5)).review_reason == "low_confidence"
