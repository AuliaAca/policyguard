"""CheckPipeline: urutan langkah pemeriksaan satu listing.

    rules -> (hard hit? reject) -> retrieval -> LLM -> validasi (+1x perbaikan) -> router

Tidak ada database, cache, atau HTTP di sini. Itu tugas service layer (app/services).
Karena itu pipeline yang sama dipakai oleh API, worker batch, dan script evaluasi.
"""
import logging
from dataclasses import dataclass

from ai.llm import Judge, LLMUnavailable
from ai.prompts import judge_v1 as prompt
from ai.retrieval import PolicyRetriever
from ai.router import Thresholds, route
from ai.rules import RuleEngine
from ai.types import Decision, Listing, Violation
from ai.validator import validate_output

log = logging.getLogger(__name__)

MAX_REPAIR_ATTEMPTS = 1


@dataclass
class PipelineConfig:
    mode: str                     # "llm" atau "rules_only" (baseline)
    thresholds: Thresholds


class CheckPipeline:
    def __init__(self, rules: RuleEngine, retriever: PolicyRetriever | None, judge: Judge | None,
                 config: PipelineConfig):
        if config.mode not in ("llm", "rules_only"):
            raise ValueError(f"mode pipeline tidak dikenal: {config.mode}")
        if config.mode == "llm" and (retriever is None or judge is None):
            raise ValueError("mode llm membutuhkan retriever dan judge")
        self.rules = rules
        self.retriever = retriever
        self.judge = judge
        self.config = config

    @property
    def model_name(self) -> str:
        return self.judge.model if (self.config.mode == "llm" and self.judge) else "rules-only"

    def run(self, listing: Listing) -> Decision:
        hits = self.rules.match(listing)

        # Baris 1 tabel keputusan: hard hit langsung reject, LLM tidak dipanggil.
        hard = [h for h in hits if h.kind == "hard"]
        if hard:
            violations = [Violation(h.policy_id, h.term, f"cocok dengan rule '{h.term}'")
                          for h in _unique_by_policy(hard)]
            return Decision("reject", "rule", violations=violations, rule_hits=hits)

        if self.config.mode == "rules_only":
            if hits:
                return Decision("needs_review", "rule", "rule_soft_hit", rule_hits=hits)
            return Decision("approve", "rule", rule_hits=hits)

        decision = Decision("needs_review", "fallback", rule_hits=hits)

        # Retrieval
        try:
            retrieved = self.retriever.retrieve(listing)
        except Exception as e:  # API embedding mati, dll. Fail-safe, bukan crash.
            log.warning("retrieval gagal", extra={"error": repr(e)})
            r = route(retrieval_ok=False, llm_ok=False, output=None, rule_hits=hits,
                      t=self.config.thresholds)
            decision.review_reason = r.review_reason
            return decision
        chunks = [c for c, _ in retrieved]
        allowed_ids = {c.policy_id for c in chunks}
        decision.retrieved_policy_ids = [c.policy_id for c in chunks]

        # LLM + validasi, dengan maksimal 1x perbaikan
        messages = prompt.build_messages(listing, chunks)
        output, llm_ok = None, True
        for attempt in range(1 + MAX_REPAIR_ATTEMPTS):
            try:
                resp = self.judge.complete(messages)
            except LLMUnavailable as e:
                log.warning("LLM tidak tersedia", extra={"error": str(e)})
                llm_ok = False
                break
            decision.llm_calls += 1
            decision.prompt_tokens += resp.prompt_tokens
            decision.completion_tokens += resp.completion_tokens
            decision.llm_raw_output = resp.text

            output, errors = validate_output(resp.text, allowed_ids, listing.text)
            if output is not None:
                break
            decision.llm_errors.extend(errors)
            log.info("output LLM tidak valid", extra={"attempt": attempt + 1, "errors": errors})
            messages = prompt.build_repair_messages(messages, resp.text, errors)

        r = route(retrieval_ok=True, llm_ok=llm_ok, output=output, rule_hits=hits,
                  t=self.config.thresholds)
        decision.decision, decision.decided_by = r.decision, r.decided_by
        decision.review_reason, decision.violations = r.review_reason, r.violations
        if output is not None:
            decision.verdict, decision.confidence = output.verdict, output.confidence
        return decision


def _unique_by_policy(hits):
    seen, out = set(), []
    for h in hits:
        if h.policy_id not in seen:
            seen.add(h.policy_id)
            out.append(h)
    return out
