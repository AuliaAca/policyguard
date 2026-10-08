"""Latihan debugging: memasukkan SATU bug ke kode, lalu Anda mencari dan memperbaikinya.

Persiapan (sekali saja):
    git init && git add . && git commit -m "baseline"

Pemakaian:
    python exercises/break.py 1        # masukkan bug nomor 1
    python -m pytest -q                # lihat gejalanya
    ...cari penyebabnya, perbaiki...
    git diff                           # bandingkan perbaikan Anda dengan kode asli
    git checkout -- .                  # kembalikan ke kode asli sebelum latihan berikutnya

Jangan buka file ini sebelum mencoba: isinya memberi tahu lokasi bug.
Petunjuk bertahap ada di exercises/README.md.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BUGS = {
    1: ("ai/router.py",
        '    if any(h.kind == "soft" for h in rule_hits):           # baris 8',
        '    if any(h.kind == "hard" for h in rule_hits):           # baris 8'),
    2: ("app/services/check_service.py",
        'f"{c_hash}|{policy_version}|{prompt_version}|{model}"',
        'f"{c_hash}|{prompt_version}|{model}"'),
    3: ("ai/validator.py",
        "if not v.evidence.strip() or _norm(v.evidence) not in text:",
        "if not v.evidence.strip() or v.evidence not in text:"),
    4: ("ai/rules.py",
        'rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"',
        'rf"{re.escape(term)}"'),
    5: ("app/db/repository.py",
        '.where(Check.cache_key == cache_key, Check.decided_by != "fallback")',
        '.where(Check.cache_key == cache_key)'),
}


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].isdigit() or int(sys.argv[1]) not in BUGS:
        print(__doc__)
        return 1
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True)
    if dirty.returncode != 0:
        sys.exit("Bukan repository git. Jalankan dulu: git init && git add . && git commit -m baseline")
    if dirty.stdout.strip():
        sys.exit("Ada perubahan yang belum di-commit. Jalankan 'git checkout -- .' atau commit dulu.")

    path, original, broken = BUGS[int(sys.argv[1])]
    f = ROOT / path
    text = f.read_text(encoding="utf-8")
    if original not in text:
        sys.exit(f"Kode di {path} sudah berubah dari versi yang diharapkan; latihan ini tidak bisa dipasang.")
    f.write_text(text.replace(original, broken, 1), encoding="utf-8")
    print(f"Bug nomor {sys.argv[1]} sudah dipasang. Jalankan: python -m pytest -q")
    return 0


if __name__ == "__main__":
    sys.exit(main())
