"""Mengirim beberapa request contoh ke API yang sedang berjalan dan menampilkan hasilnya.

Pemakaian:
    python scripts/smoke_test_api.py            # API key dibaca otomatis dari .env
    python scripts/smoke_test_api.py --batch    # uji juga batch (butuh Redis dan worker: mode Docker)

Dibuat supaya tidak perlu menulis curl (cara penulisan curl berbeda di Windows dan macOS/Linux).
"""
import argparse
import sys
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def key_from_env_file() -> str | None:
    env = ROOT / ".env"
    if not env.exists():
        return None
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("SERVICE_API_KEYS="):
            return line.split("=", 1)[1].split(",")[0].strip() or None
    return None

SAMPLES = [
    ("hard rule (harus reject, decided_by=rule)", "alpr4 1mg buat tidur nyenyak", "Kesehatan", 150000),
    ("produk biasa", "Kaos polos cotton combed 30s", "Fashion Pria", 45000),
    ("klaim kesehatan (mode llm: dinilai LLM)", "Kopi herbal, bisa sembuhkan diabetes", "Makanan & Minuman", 65000),
    ("jebakan keyword (pistol air mainan)", "Mainan pistol air untuk anak-anak", "Mainan & Hobi", 35000),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--key", default=None, help="default: key pertama SERVICE_API_KEYS di .env")
    ap.add_argument("--batch", action="store_true", help="uji juga endpoint batch (butuh Redis dan worker)")
    args = ap.parse_args()
    key = args.key or key_from_env_file()
    if not key:
        sys.exit("API key tidak ditemukan. Jalankan dulu: python scripts/make_env.py local")
    h = {"X-API-Key": key}
    run = uuid.uuid4().hex[:6]           # listing_id unik setiap kali dijalankan

    with httpx.Client(base_url=args.url, timeout=60) as c:
        try:
            health = c.get("/health")
        except httpx.ConnectError:
            sys.exit(f"Tidak bisa terhubung ke {args.url}. Apakah API sudah berjalan?")
        print(f"[health] HTTP {health.status_code}: {health.json()}\n")

        r = c.post("/v1/checks", json={"listing_id": "x", "title": "Tanpa key", "category": "Kesehatan", "price": 1})
        print(f"[tanpa API key] HTTP {r.status_code} (seharusnya 401)")
        r = c.post("/v1/checks", headers=h, json={"listing_id": "x", "title": "Deskripsi terlalu panjang",
                                                   "description": "x" * 5001, "category": "Kesehatan", "price": 1})
        print(f"[deskripsi 5001 karakter] HTTP {r.status_code} (seharusnya 422)\n")

        first_id = None
        for i, (label, title, cat, price) in enumerate(SAMPLES):
            body = {"listing_id": f"smoke-{run}-{i}", "title": title, "category": cat, "price": price}
            r = c.post("/v1/checks", headers=h, json=body)
            if r.status_code != 200:
                print(f"[{label}] HTTP {r.status_code}: {r.text}")
                continue
            d = r.json()
            first_id = first_id or d["check_id"]
            v = ", ".join(f"{x['policy_id']} ('{x['evidence']}')" for x in d["violations"]) or "-"
            print(f"[{label}]\n   {title}\n   -> {d['decision']} | decided_by={d['decided_by']} | "
                  f"review_reason={d['review_reason']} | pelanggaran={v} | {d['latency_ms']} ms")

        same = c.post("/v1/checks", headers=h, json={"listing_id": f"smoke-{run}-0", "title": SAMPLES[0][1],
                                                      "category": SAMPLES[0][2], "price": SAMPLES[0][3]}).json()
        ok = "YA, idempotensi bekerja" if same["check_id"] == first_id else "TIDAK, periksa idempotensi"
        print(f"\n[kirim ulang request pertama] check_id sama dengan sebelumnya? {ok}")

        if args.batch:
            listings = [{"listing_id": f"batch-{run}-{i}", "title": t, "category": cat, "price": p}
                        for i, (_, t, cat, p) in enumerate(SAMPLES)]
            b = c.post("/v1/batches", headers=h, json={"listings": listings})
            print(f"\n[batch] HTTP {b.status_code} (seharusnya 202): {b.json()}")
            if b.status_code == 503:
                print("   503 di sini wajar jika REDIS_URL dikosongkan (mode lokal tanpa Redis).")
            if b.status_code == 202:
                bid = b.json()["batch_id"]
                for _ in range(30):
                    s = c.get(f"/v1/batches/{bid}", headers=h).json()
                    if s["status"] == "completed":
                        break
                    time.sleep(2)
                print(f"[batch] status akhir: {s}")
                if s["status"] != "completed":
                    print("   Belum selesai. Apakah worker berjalan?")
    return 0


if __name__ == "__main__":
    sys.exit(main())
