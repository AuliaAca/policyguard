"""Membagi dataset master menjadi dev dan test.

Pemakaian:
    python scripts/split_dataset.py data/eval/listings.jsonl data/eval

Aturan pembagian:
1. Listing dengan 'PERLU KLARIFIKASI' di note dikeluarkan ke excluded.jsonl (pedoman aturan 11).
2. Pembagian per GROUP, bukan per listing. Listing yang mirip (group sama) selalu
   berada di split yang sama, supaya prompt yang diperbaiki dengan dev set tidak
   "sudah pernah melihat" soal di test set.
3. Stratified: setiap strata (pasal utama, atau tipe listing patuh) dibagi dengan
   rasio yang sama, sehingga setiap pasal punya contoh di dev dan test.
4. Deterministik: urutan ditentukan oleh hash, bukan random. Menjalankan ulang
   script menghasilkan split yang sama persis.
"""
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

DEV_RATIO = 0.4
SEED = "policyguard-split-v1"


def stratum_of(rows: list[dict]) -> str:
    """Strata sebuah group: pasal pertama dari listing melanggar, atau tipe listing patuh."""
    for r in rows:
        if r["violations"]:
            return r["violations"][0]["policy_id"]
    return "compliant:" + rows[0]["test_tag"]


def stable_key(group: str) -> str:
    return hashlib.sha256(f"{SEED}:{group}".encode()).hexdigest()


def split(rows: list[dict]) -> tuple[list, list, list]:
    excluded = [r for r in rows if "PERLU KLARIFIKASI" in r["note"]]
    usable = [r for r in rows if "PERLU KLARIFIKASI" not in r["note"]]

    groups: dict[str, list] = defaultdict(list)
    for r in usable:
        groups[r["group"]].append(r)

    by_stratum: dict[str, list[str]] = defaultdict(list)
    for g, members in groups.items():
        by_stratum[stratum_of(members)].append(g)

    dev_groups = set()
    for gs in by_stratum.values():
        gs.sort(key=stable_key)
        dev_groups.update(gs[: round(len(gs) * DEV_RATIO)])

    dev = [r for r in usable if r["group"] in dev_groups]
    test = [r for r in usable if r["group"] not in dev_groups]
    return dev, test, excluded


def summarize(name: str, rows: list[dict]) -> None:
    per_policy = Counter(v["policy_id"] for r in rows for v in r["violations"])
    print(f"{name}: {len(rows)} listing, label={dict(Counter(r['label'] for r in rows))}, "
          f"insufficient_info={sum(r['insufficient_info'] for r in rows)}")
    print("   per pasal: " + ", ".join(f"{p.split('-',1)[1]}={c}" for p, c in sorted(per_policy.items())))


def main(master: str, out_dir: str) -> int:
    rows = [json.loads(l) for l in open(master, encoding="utf-8") if l.strip()]
    dev, test, excluded = split(rows)

    # Pengaman: tidak boleh ada listing atau group di dua split sekaligus.
    assert not {r["id"] for r in dev} & {r["id"] for r in test}, "ID bocor antar split"
    assert not {r["group"] for r in dev} & {r["group"] for r in test}, "group bocor antar split"
    assert len(dev) + len(test) + len(excluded) == len(rows), "ada listing yang hilang"

    out = Path(out_dir)
    for name, part in (("dev", dev), ("test", test), ("excluded", excluded)):
        with open(out / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for r in part:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    summarize("dev ", dev)
    summarize("test", test)
    print(f"excluded: {[r['id'] for r in excluded]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
