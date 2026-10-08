"""Rule prefilter: pencocokan istilah yang murah, cepat, dan deterministik.

- Istilah 'hard' hampir pasti melanggar -> listing langsung ditolak tanpa LLM.
- Istilah 'soft' berisiko tapi bisa sah -> hanya menjadi sinyal untuk decision router.

Normalisasi di sini hanya untuk pencocokan (ADR-010). LLM tetap menerima teks asli.
"""
import json
import re
import unicodedata
from pathlib import Path

from ai.types import Listing, RuleHit

# Huruf tunggal yang dipisah titik/strip/garis bawah/bintang: "x.a.n.a.x", "s-l-o-t", "k.w"
_SPACED_LETTERS = re.compile(r"\b(?:[a-z][.\-_*])+[a-z]\b")
_SEPARATORS = re.compile(r"[.\-_*]")
# Token angka + satuan pendek ("1mg", "30ml", "8kg", "200w") tidak boleh diubah.
_NUMBER_WITH_UNIT = re.compile(r"^\d+(?:[.,]\d+)?[a-z]{0,3}$")
_TOKEN = re.compile(r"[a-z0-9]+")
_LEET = str.maketrans({"4": "a", "1": "i", "0": "o", "3": "e", "5": "s", "7": "t"})


def _deleet(token: str) -> str:
    has_letter = any(c.isalpha() for c in token)
    has_digit = any(c.isdigit() for c in token)
    if has_letter and has_digit and not _NUMBER_WITH_UNIT.match(token):
        return token.translate(_LEET)
    return token


def normalize_for_rules(text: str) -> str:
    """'Alpr4 1mg' -> 'alpra 1mg', 'S-L-O-T gacor' -> 'slot gacor'."""
    t = unicodedata.normalize("NFKC", text).lower()
    t = _SPACED_LETTERS.sub(lambda m: _SEPARATORS.sub("", m.group()), t)
    return _TOKEN.sub(lambda m: _deleet(m.group()), t)


class RuleEngine:
    def __init__(self, hard: dict[str, str], soft: dict[str, str]):
        """hard/soft: {istilah: policy_id}. Istilah ditulis dalam bentuk ternormalisasi."""
        self._rules = [
            (term, pid, kind, re.compile(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"))
            for kind, table in (("hard", hard), ("soft", soft))
            for term, pid in table.items()
        ]

    @classmethod
    def from_file(cls, path: str | Path) -> "RuleEngine":
        # Sengaja tidak menangkap error: file rules rusak = service gagal start (system_design bagian 8).
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(hard=data["hard"], soft=data["soft"])

    def match(self, listing: Listing) -> list[RuleHit]:
        text = normalize_for_rules(listing.text)
        return [RuleHit(term, pid, kind) for term, pid, kind, rx in self._rules if rx.search(text)]
