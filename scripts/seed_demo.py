"""Mengirim sebagian listing dari dev set ke API yang sedang berjalan, supaya dashboard berisi data contoh.

Pemakaian:
    python scripts/seed_demo.py              # 40 listing pertama dari data/eval/dev.jsonl
    python scripts/seed_demo.py --n 101      # semua listing dev

Catatan: hanya memakai dev set. Test set tidak pernah dipakai untuk demo, supaya tetap "belum terlihat".
Pada mode AI, setiap listing memanggil API OpenAI (ada biayanya).
"""
import argparse
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def key_from_env_file() -> str | None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("SERVICE_API_KEYS="):
                return line.split("=", 1)[1].split(",")[0].strip() or None
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--key", default=None, help="default: key pertama SERVICE_API_KEYS di .env")
    ap.add_argument("--quiet", action="store_true", help="hanya cetak ringkasan")
    args = ap.parse_args()
    key = args.key or key_from_env_file()
    if not key:
        sys.exit("API key tidak ditemukan. Jalankan dulu: python scripts/make_env.py local")

    rows = [json.loads(l) for l in (ROOT / "data/eval/dev.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    counts: dict[str, int] = {}
    with httpx.Client(base_url=args.url, headers={"X-API-Key": key}, timeout=120) as c:
        try:
            c.get("/health")
        except httpx.ConnectError:
            sys.exit(f"Tidak bisa terhubung ke {args.url}. Jalankan dulu: python scripts/run_local.py")
        for r in rows[: args.n]:
            body = {"listing_id": f"demo-{r['id']}", "title": r["title"], "description": r["description"],
                    "category": r["category"], "price": r["price"]}
            resp = c.post("/v1/checks", json=body)
            if resp.status_code != 200:
                print(f"{r['id']}: HTTP {resp.status_code} {resp.text[:200]}")
                continue
            d = resp.json()["decision"]
            counts[d] = counts.get(d, 0) + 1
            if not args.quiet:
                print(f"{d:<13} {r['title']}")
    print(f"Selesai: {counts}. Muat ulang dashboard di browser.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
