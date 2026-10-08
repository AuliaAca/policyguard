"""Memuat dokumen kebijakan menjadi potongan (chunk) per pasal, dan menghitung versinya.

Satu pasal = satu chunk. Dengan begitu, saat retrieval mengambil sebuah pasal, bagian
'Tidak termasuk' ikut terbawa bersama larangannya.
"""
import hashlib
import re
from pathlib import Path

from ai.types import PolicyChunk

_HEADING = re.compile(r"^## (POL-[A-Z]+-\d+):\s*(.+)$", re.M)


def _policy_files(policies_dir: str | Path) -> list[Path]:
    files = sorted(Path(policies_dir).glob("*.md"))
    if not files:
        raise FileNotFoundError(f"Tidak ada file kebijakan (.md) di {policies_dir}")
    return files


def load_policy_chunks(policies_dir: str | Path) -> list[PolicyChunk]:
    chunks: list[PolicyChunk] = []
    for path in _policy_files(policies_dir):
        text = path.read_text(encoding="utf-8")
        matches = list(_HEADING.finditer(text))
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            chunks.append(PolicyChunk(policy_id=m.group(1), title=m.group(2).strip(),
                                      text=text[m.start():end].strip()))
    ids = [c.policy_id for c in chunks]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"ID pasal duplikat: {sorted(duplicates)}")
    return chunks


def compute_policy_version(policies_dir: str | Path) -> str:
    """Hash isi semua file kebijakan (ADR-011). Mengubah satu karakter = versi baru."""
    h = hashlib.sha256()
    for path in _policy_files(policies_dir):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return "sha256:" + h.hexdigest()[:16]
