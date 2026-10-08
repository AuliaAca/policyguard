"""Metrik Prometheus. Dibaca dari endpoint GET /metrics.

Pertanyaan operasional yang dijawab metrik ini:
- Berapa banyak listing yang diputuskan otomatis vs dikirim ke moderator?   -> checks_total
- Apakah LLM sedang bermasalah?                                             -> fallback_total
- Seberapa lambat sistem?                                                   -> request_latency, llm_latency
- Berapa biaya yang sedang dikeluarkan?                                     -> llm_tokens_total
"""
from prometheus_client import Counter, Histogram

CHECKS = Counter("policyguard_checks_total", "Keputusan pemeriksaan",
                 ["decision", "decided_by", "cached"])
FALLBACKS = Counter("policyguard_fallback_total", "Listing ke needs_review karena komponen gagal",
                    ["reason"])
INVALID_LLM_OUTPUT = Counter("policyguard_llm_invalid_output_total",
                             "Output LLM yang gagal validasi (per percobaan)")
LLM_TOKENS = Counter("policyguard_llm_tokens_total", "Token LLM terpakai", ["type"])
REQUEST_LATENCY = Histogram("policyguard_request_latency_seconds", "Latency HTTP per endpoint",
                            ["path", "method", "status"],
                            buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 16, 32))
PIPELINE_LATENCY = Histogram("policyguard_pipeline_latency_seconds", "Latency pipeline (tanpa cache)",
                             buckets=(0.01, 0.1, 0.5, 1, 2, 4, 8, 16, 32))
