"""Komponen palsu (fake) untuk test. Dengan ini, logika sistem bisa diuji tanpa
API OpenAI, tanpa biaya, dan dengan hasil yang selalu sama."""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("SERVICE_API_KEYS", "test-key")

from ai.pipeline import CheckPipeline, PipelineConfig  # noqa: E402
from ai.policies import load_policy_chunks  # noqa: E402
from ai.llm import JudgeResponse, LLMUnavailable  # noqa: E402
from ai.router import Thresholds  # noqa: E402
from ai.rules import RuleEngine  # noqa: E402
from ai.types import Listing  # noqa: E402

CHUNKS = load_policy_chunks(ROOT / "data/policies")


class FakeRetriever:
    def __init__(self, policy_ids=("POL-HLT-01", "POL-HLT-02", "POL-DRG-01"), fail=False):
        self.chunks = [c for c in CHUNKS if c.policy_id in policy_ids]
        self.fail = fail
        self.ready = True

    def ensure_index(self):
        if self.fail:
            raise ConnectionError("embedding API mati")

    def retrieve(self, listing):
        self.ensure_index()
        return [(c, 0.9) for c in self.chunks]


class FakeJudge:
    """Mengembalikan jawaban yang sudah disiapkan secara berurutan. Exception = LLM gagal."""
    model = "fake-model"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, messages):
        self.calls.append(messages)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        text = r if isinstance(r, str) else json.dumps(r)
        return JudgeResponse(text=text, prompt_tokens=100, completion_tokens=20, latency_ms=5)


def judge_json(verdict="compliant", violations=(), confidence=0.95):
    return {"verdict": verdict, "confidence": confidence,
            "violations": [{"policy_id": p, "evidence": e, "reason": "alasan"} for p, e in violations]}


def make_listing(title="Teh jahe merah untuk menghangatkan badan", description="", listing_id="T1",
                 category="Makanan & Minuman", price=35000):
    return Listing(listing_id, title, description, category, price)


def make_pipeline(judge=None, retriever=None, mode="llm", t=0.8):
    return CheckPipeline(RuleEngine.from_file(ROOT / "data/rules/rules.json"),
                         retriever if retriever is not None else FakeRetriever(),
                         judge if judge is not None else FakeJudge(judge_json()),
                         PipelineConfig(mode=mode, thresholds=Thresholds(t, t)))


@pytest.fixture
def unavailable():
    return LLMUnavailable("timeout")
