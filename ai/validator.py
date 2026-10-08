"""Validasi output LLM. Ini kode biasa (deterministik), bukan AI.

Tujuannya: output LLM tidak pernah dipercaya begitu saja. Setiap jawaban harus lolos
pemeriksaan di bawah sebelum boleh memengaruhi keputusan.
"""
import json
import re
from typing import Literal

from pydantic import BaseModel, ValidationError


class ViolationOut(BaseModel):
    policy_id: str
    evidence: str
    reason: str


class JudgeOutput(BaseModel):
    verdict: Literal["compliant", "violating", "insufficient_info"]
    violations: list[ViolationOut]
    confidence: float


_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", text).strip().lower()


def validate_output(raw: str, allowed_policy_ids: set[str], listing_text: str
                    ) -> tuple[JudgeOutput | None, list[str]]:
    """Mengembalikan (output, []) jika valid, atau (None, daftar_error) jika tidak."""
    # 1. Format JSON dan schema
    try:
        out = JudgeOutput.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as e:
        return None, [f"format output tidak valid: {str(e)[:300]}"]

    errors: list[str] = []
    # 2. Konsistensi verdict dan daftar pelanggaran
    if out.verdict == "violating" and not out.violations:
        errors.append("verdict 'violating' tetapi violations kosong")
    if out.verdict != "violating" and out.violations:
        errors.append(f"verdict '{out.verdict}' tetapi violations tidak kosong")
    # 3. Rentang confidence
    if not 0.0 <= out.confidence <= 1.0:
        errors.append(f"confidence di luar rentang 0-1: {out.confidence}")

    text = _norm(listing_text)
    for v in out.violations:
        # 4. Pasal harus berasal dari pasal yang diberikan ke LLM (anti pasal karangan)
        if v.policy_id not in allowed_policy_ids:
            errors.append(f"policy_id '{v.policy_id}' tidak termasuk pasal yang diberikan")
        # 5. Evidence harus benar-benar ada di listing (ADR-009, anti kutipan karangan)
        if not v.evidence.strip() or _norm(v.evidence) not in text:
            errors.append(f"evidence tidak ditemukan di listing: '{v.evidence}'")

    return (None, errors) if errors else (out, [])
