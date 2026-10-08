"""Menjalankan evaluasi pipeline terhadap dataset berlabel.

Contoh:
  python -m ai.evaluation.run_eval --split dev --mode rules_only
  python -m ai.evaluation.run_eval --split dev --mode llm_all  --price-in 0.15 --price-out 0.60
  python -m ai.evaluation.run_eval --split dev --mode llm_rag  --price-in 0.15 --price-out 0.60
  python -m ai.evaluation.run_eval --split test --mode llm_rag --final

Mode:
  rules_only : baseline keyword (tanpa AI)
  llm_all    : LLM menerima SEMUA pasal (tanpa retrieval)
  llm_rag    : LLM menerima top-k pasal hasil retrieval

Harga token (--price-in / --price-out, USD per 1 juta token) sengaja tidak ditulis di kode:
harga berubah, jadi isi sesuai halaman harga resmi saat Anda menjalankan evaluasi.

Evaluasi tidak memakai database maupun cache: setiap listing benar-benar diproses pipeline.
"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from ai.evaluation.metrics import Result, compute, threshold_sweep
from ai.factory import build_pipeline
from ai.types import Listing
from app.core.config import get_settings

MODES = {"rules_only": ("rules_only", None), "llm_all": ("llm", "all"), "llm_rag": ("llm", "topk")}
SWEEP = [0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95]


def load_split(split: str, data_dir: Path, final: bool) -> list[dict]:
    rows = [json.loads(l) for l in (data_dir / f"{split}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    if split == "test":
        if not final:
            sys.exit("Test set hanya untuk angka akhir. Tambahkan --final jika memang itu tujuannya.\n"
                     "Untuk memperbaiki prompt atau threshold, pakai --split dev.")
        draft = [r["id"] for r in rows if r.get("label_status") != "reviewed"]
        if draft:
            sys.exit(f"{len(draft)} listing test masih berstatus draft (contoh: {draft[:5]}).\n"
                     "Tinjau label secara manual dan ubah label_status menjadi 'reviewed' di listings.jsonl, "
                     "lalu jalankan ulang scripts/split_dataset.py.")
    return rows


def run_one(pipeline, row: dict) -> Result:
    listing = Listing(row["id"], row["title"], row["description"], row["category"], row["price"])
    start = time.perf_counter()
    d = pipeline.run(listing)
    return Result(
        id=row["id"], gold_label=row["label"], gold_policies=[v["policy_id"] for v in row["violations"]],
        insufficient_info=row["insufficient_info"], test_tag=row["test_tag"],
        decision=d.decision, decided_by=d.decided_by, review_reason=d.review_reason,
        pred_policies=[v.policy_id for v in d.violations], retrieved_policies=d.retrieved_policy_ids,
        verdict=d.verdict, confidence=d.confidence, soft_hit=any(h.kind == "soft" for h in d.rule_hits),
        latency_ms=int((time.perf_counter() - start) * 1000),
        prompt_tokens=d.prompt_tokens, completion_tokens=d.completion_tokens,
    )


def to_markdown(name: str, m: dict, sweep: list[dict] | None) -> str:
    lines = [f"# Evaluasi: {name}", "",
             f"Listing: {m['n']} ({m['n_violating']} melanggar, {m['n_compliant']} patuh)", "",
             "| Metrik | Nilai |", "|---|---|"]
    for k in ("violation_recall", "reject_precision", "automation_rate", "policy_match_on_correct_rejects",
              "retrieval_recall", "insufficient_info_handled", "latency_ms_p50", "latency_ms_p95",
              "cost_per_1000_listings"):
        lines.append(f"| {k} | {m[k]} |")
    lines += ["", f"Keputusan: {m['decisions']}", f"Alasan review: {m['review_reasons']}",
              f"Pelanggaran lolos (approve): {m['missed_violations']}",
              f"Salah tolak: {m['false_rejects']}", "", "## Recall per pasal", "", "| Pasal | n | Recall |", "|---|---|---|"]
    lines += [f"| {p} | {v['n']} | {v['recall']} |" for p, v in m["per_policy_recall"].items()]
    lines += ["", "## Benar per jenis kasus", "", "| test_tag | n | Benar |", "|---|---|---|"]
    lines += [f"| {t} | {v['n']} | {v['correct']} |" for t, v in m["correct_rate_by_tag"].items()]
    if sweep:
        lines += ["", "## Simulasi threshold (T_REJECT = T_APPROVE = t)", "",
                  "| t | Recall | Precision reject | Automation | Salah tolak | Lolos |", "|---|---|---|---|---|---|"]
        lines += [f"| {r['threshold']} | {r['violation_recall']} | {r['reject_precision']} | {r['automation_rate']} "
                  f"| {r['false_rejects']} | {r['missed']} |" for r in sweep]
    lines += ["", "Catatan: angka per pasal berasal dari sedikit contoh; selisih satu listing menggeser recall "
              "per pasal cukup besar."]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"], default="dev")
    ap.add_argument("--mode", choices=list(MODES), default="llm_rag")
    ap.add_argument("--final", action="store_true", help="wajib untuk --split test")
    ap.add_argument("--data-dir", default="data/eval")
    ap.add_argument("--out-dir", default="reports")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=4, help="panggilan paralel (perhatikan rate limit API)")
    ap.add_argument("--price-in", type=float, default=None, help="USD per 1 juta token input")
    ap.add_argument("--price-out", type=float, default=None, help="USD per 1 juta token output")
    args = ap.parse_args()

    rows = load_split(args.split, Path(args.data_dir), args.final)[: args.limit]
    pipeline_mode, retrieval_mode = MODES[args.mode]
    pipeline = build_pipeline(get_settings(), mode=pipeline_mode, retrieval_mode=retrieval_mode)

    print(f"Mengevaluasi {len(rows)} listing ({args.split}, {args.mode}, model={pipeline.model_name})...")
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        results = list(ex.map(lambda r: run_one(pipeline, r), rows))

    m = compute(results, args.price_in, args.price_out)
    sweep = threshold_sweep(results, SWEEP) if pipeline_mode == "llm" else None
    name = f"{args.split}_{args.mode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{name}.json").write_text(json.dumps(
        {"split": args.split, "mode": args.mode, "model": pipeline.model_name, "metrics": m, "sweep": sweep,
         "results": [r.__dict__ for r in results]}, ensure_ascii=False, indent=2), encoding="utf-8")
    md = to_markdown(name, m, sweep)
    (out / f"{name}.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"Laporan: {out / name}.md dan .json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
