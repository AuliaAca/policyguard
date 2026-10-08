"""Menandai listing di sebuah split sebagai 'reviewed' di file master.

Jalankan HANYA setelah Anda benar-benar membaca setiap listing di split tersebut
(python scripts/show_listings.py data/eval/test.jsonl) dan memperbaiki label yang salah
langsung di data/eval/listings.jsonl.

Pemakaian:
    python scripts/mark_reviewed.py data/eval/listings.jsonl data/eval/test.jsonl
Lalu:
    python scripts/validate_dataset.py data/eval/listings.jsonl data/policies/listing_policy.md
    python scripts/split_dataset.py data/eval/listings.jsonl data/eval
"""
import json
import sys


def main(master_path: str, split_path: str) -> int:
    ids = {json.loads(l)["id"] for l in open(split_path, encoding="utf-8") if l.strip()}
    rows = [json.loads(l) for l in open(master_path, encoding="utf-8") if l.strip()]
    changed = 0
    for r in rows:
        if r["id"] in ids and r["label_status"] != "reviewed":
            r["label_status"] = "reviewed"
            changed += 1
    with open(master_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{changed} listing ditandai reviewed. Jalankan validate_dataset.py lalu split_dataset.py.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
