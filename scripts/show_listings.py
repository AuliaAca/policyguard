"""Menampilkan listing beserta labelnya dalam format yang mudah dibaca, untuk review manual.

Pemakaian:
    python scripts/show_listings.py data/eval/test.jsonl
    python scripts/show_listings.py data/eval/test.jsonl --from 21 --to 40
"""
import argparse
import json


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--from", dest="start", type=int, default=1)
    ap.add_argument("--to", dest="end", type=int, default=None)
    args = ap.parse_args()
    rows = [json.loads(l) for l in open(args.path, encoding="utf-8") if l.strip()]
    end = args.end or len(rows)
    for n, r in enumerate(rows[args.start - 1:end], start=args.start):
        print(f"--- {n}/{len(rows)}  {r['id']}  [{r['label_status']}]")
        print(f"Judul    : {r['title']}")
        if r["description"]:
            print(f"Deskripsi: {r['description']}")
        print(f"Kategori : {r['category']}  |  Harga: Rp{r['price']:,}")
        viol = "; ".join(f"{v['policy_id']} <- '{v['evidence']}'" for v in r["violations"]) or "-"
        flag = "  (insufficient_info)" if r["insufficient_info"] else ""
        print(f"LABEL    : {r['label']}{flag}  |  {viol}")
        print(f"Catatan  : {r['note']}\n")


if __name__ == "__main__":
    main()
