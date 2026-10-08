"""LLM Judge: satu-satunya tempat sistem memanggil model bahasa.

Kode ini hanya mengirim prompt dan mengembalikan teks mentah + jumlah token.
Memeriksa apakah jawabannya benar BUKAN tugas file ini (lihat validator.py).
"""
import time
from dataclasses import dataclass
from typing import Protocol

# Schema output yang dipaksakan ke model lewat "structured outputs".
# strict=True mewajibkan semua field 'required' dan additionalProperties=false.
JUDGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "violations", "confidence"],
    "properties": {
        "verdict": {"type": "string", "enum": ["compliant", "violating", "insufficient_info"]},
        "violations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["policy_id", "evidence", "reason"],
                "properties": {
                    "policy_id": {"type": "string"},
                    "evidence": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
        "confidence": {"type": "number"},
    },
}


class LLMUnavailable(Exception):
    """LLM tidak bisa dipakai: timeout, rate limit, server error, atau koneksi gagal."""


@dataclass
class JudgeResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int


class Judge(Protocol):
    model: str

    def complete(self, messages: list[dict]) -> JudgeResponse: ...


class OpenAIJudge:
    def __init__(self, client, model: str, temperature: float | None = 0.0):
        self._client = client
        self.model = model
        self._temperature = temperature

    def complete(self, messages: list[dict]) -> JudgeResponse:
        import openai  # import lokal: modul ini tetap bisa di-import tanpa paket openai (test)

        kwargs = {
            "model": self.model,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "policy_judgement", "strict": True, "schema": JUDGE_SCHEMA},
            },
        }
        if self._temperature is not None:   # beberapa model tidak menerima parameter temperature
            kwargs["temperature"] = self._temperature

        start = time.perf_counter()
        try:
            # Timeout dan retry dengan backoff untuk 429/5xx/timeout ditangani SDK
            # (diatur saat membuat client: timeout=..., max_retries=...).
            resp = self._client.chat.completions.create(**kwargs)
        except openai.APIError as e:
            # Termasuk timeout, 429, 5xx (setelah retry SDK habis), dan juga 401/400.
            # 401/400 biasanya salah konfigurasi (API key, nama model). Tetap fail-safe ke
            # needs_review, tapi nama error-nya dicatat agar terlihat di log dan metrik.
            raise LLMUnavailable(f"{type(e).__name__}: {e}") from e
        latency_ms = int((time.perf_counter() - start) * 1000)

        choice = resp.choices[0]
        if getattr(choice.message, "refusal", None):
            # Model menolak menjawab: diperlakukan sebagai output tidak valid, bukan LLM mati.
            text = ""
        else:
            text = choice.message.content or ""
        usage = resp.usage
        return JudgeResponse(
            text=text,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            latency_ms=latency_ms,
        )
