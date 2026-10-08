import shutil

from ai.evaluation.metrics import Result, compute, threshold_sweep
from ai.policies import compute_policy_version, load_policy_chunks
from conftest import ROOT


def res(id, gold, decision, policies=(), pred=(), verdict=None, conf=None, tag="t", insuf=False):
    return Result(id=id, gold_label=gold, gold_policies=list(policies), insufficient_info=insuf, test_tag=tag,
                  decision=decision, decided_by="llm", review_reason=None, pred_policies=list(pred),
                  retrieved_policies=list(policies), verdict=verdict, confidence=conf, soft_hit=False,
                  latency_ms=10, prompt_tokens=1000, completion_tokens=100)


def test_metrics_definitions():
    rows = [
        res("v1", "violating", "reject", ["P1"], ["P1"]),
        res("v2", "violating", "needs_review", ["P1"]),     # tertangkap: tidak lolos
        res("v3", "violating", "approve", ["P2"]),          # lolos
        res("c1", "compliant", "approve"),
        res("c2", "compliant", "reject", pred=["P1"]),      # salah tolak
    ]
    m = compute(rows, price_in_per_1m=1.0, price_out_per_1m=2.0)
    assert m["violation_recall"] == round(2 / 3, 3)
    assert m["reject_precision"] == 0.5
    assert m["automation_rate"] == 0.8
    assert m["missed_violations"] == ["v3"] and m["false_rejects"] == ["c2"]
    assert m["per_policy_recall"]["P2"] == {"n": 1, "recall": 0.0}
    # biaya per listing = 1000/1e6*1 + 100/1e6*2 = 0.0012 USD -> per 1000 listing = 1.2
    assert m["cost_per_1000_listings"] == 1.2


def test_threshold_sweep_trades_automation_for_precision():
    rows = [res("v", "violating", "reject", ["P1"], ["P1"], "violating", 0.9),
            res("c", "compliant", "reject", [], ["P1"], "violating", 0.7)]
    low, high = threshold_sweep(rows, [0.6, 0.8])
    assert low["reject_precision"] == 0.5 and high["reject_precision"] == 1.0
    assert high["automation_rate"] < low["automation_rate"]


def test_policy_chunks_and_version(tmp_path):
    chunks = load_policy_chunks(ROOT / "data/policies")
    assert len(chunks) == 15 and all(c.text.startswith("## POL-") for c in chunks)
    assert "Tidak termasuk" in chunks[0].text      # pengecualian ikut dalam chunk yang sama

    copy = tmp_path / "policies"
    shutil.copytree(ROOT / "data/policies", copy)
    before = compute_policy_version(copy)
    f = copy / "listing_policy.md"
    f.write_text(f.read_text() + "\n", encoding="utf-8")
    assert compute_policy_version(copy) != before    # satu karakter berubah -> versi baru
