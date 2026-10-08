"""Validasi dataset evaluasi terhadap dokumen kebijakan dan pedoman pelabelan.

Pemakaian:
    python scripts/validate_dataset.py data/eval/listings.jsonl data/policies/listing_policy.md

Yang dicek (deterministik, tanpa AI):
- format field dan nilai label
- aturan 1: setiap violating merujuk pasal yang ada di dokumen kebijakan
- aturan 6: insufficient_info hanya boleh pada label compliant
- aturan 8: evidence harus muncul persis di judul atau deskripsi
- ID unik dan judul unik (judul kembar membuat evaluasi bocor antar-split)
- label_status hanya 'draft' atau 'reviewed'
"""
import json
import re
import sys
from collections import Counter

VALID_LABELS = {"compliant", "violating"}
VALID_STATUS = {"draft", "reviewed"}
REQUIRED = ["id", "title", "description", "category", "price", "label",
            "violations", "insufficient_info", "test_tag", "note", "group", "label_status"]


def load_policy_ids(policy_path: str) -> set[str]:
    text = open(policy_path, encoding="utf-8").read()
    return set(re.findall(r"^## (POL-[A-Z]+-\d+)", text, re.M))


def check_row(r: dict, policy_ids: set[str]) -> list[str]:
    errors = []
    missing = [k for k in REQUIRED if k not in r]
    if missing:
        return [f"field hilang: {missing}"]

    if r["label"] not in VALID_LABELS:
        errors.append(f"label tidak valid: {r['label']!r}")
    if r["label_status"] not in VALID_STATUS:
        errors.append(f"label_status tidak valid: {r['label_status']!r}")
    if not isinstance(r["price"], int) or r["price"] <= 0:
        errors.append("price harus integer > 0")

    if r["label"] == "violating" and not r["violations"]:
        errors.append("violating tanpa violations")
    if r["label"] == "compliant" and r["violations"]:
        errors.append("compliant tetapi punya violations")
    if r["insufficient_info"] and r["label"] != "compliant":
        errors.append("insufficient_info hanya untuk label compliant (aturan 6)")

    text = (r["title"] + " " + r["description"]).lower()
    for v in r["violations"]:
        if v["policy_id"] not in policy_ids:
            errors.append(f"pasal tidak ada di kebijakan: {v['policy_id']}")
        if not v.get("evidence") or v["evidence"].lower() not in text:
            errors.append(f"evidence tidak ditemukan di listing: {v.get('evidence')!r}")
    return errors


def main(dataset_path: str, policy_path: str) -> int:
    policy_ids = load_policy_ids(policy_path)
    rows = [json.loads(line) for line in open(dataset_path, encoding="utf-8") if line.strip()]

    problems = []
    for field in ("id", "title"):
        dup = [v for v, c in Counter(r[field].lower() if field == "title" else r[field]
                                     for r in rows).items() if c > 1]
        if dup:
            problems.append(("-", f"{field} duplikat: {dup}"))
    for r in rows:
        for e in check_row(r, policy_ids):
            problems.append((r.get("id", "?"), e))

    per_policy = Counter(v["policy_id"] for r in rows for v in r["violations"])
    print(f"listing           : {len(rows)}")
    print(f"label             : {dict(Counter(r['label'] for r in rows))}")
    print(f"insufficient_info : {sum(r['insufficient_info'] for r in rows)}")
    print(f"label_status      : {dict(Counter(r['label_status'] for r in rows))}")
    print(f"test_tag          : {dict(Counter(r['test_tag'] for r in rows))}")
    print("pelanggaran/pasal :")
    for pid in sorted(policy_ids):
        print(f"  {pid:<11} {per_policy.get(pid, 0)}")
    print(f"perlu klarifikasi : {[r['id'] for r in rows if 'PERLU KLARIFIKASI' in r['note']] or '-'}")
    if problems:
        print("\nMASALAH:")
        for rid, msg in problems:
            print(f"  {rid}: {msg}")
        return 1
    print("\nOK: tidak ada masalah")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
