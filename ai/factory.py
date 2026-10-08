"""Merakit CheckPipeline dari konfigurasi. Dipakai API, worker, dan script evaluasi,
supaya ketiganya memakai pipeline yang sama persis."""
from ai.llm import OpenAIJudge
from ai.pipeline import CheckPipeline, PipelineConfig
from ai.policies import load_policy_chunks
from ai.retrieval import LocalEmbedder, OpenAIEmbedder, PolicyRetriever
from ai.router import Thresholds
from ai.rules import RuleEngine


def build_pipeline(settings, *, mode: str | None = None, retrieval_mode: str | None = None) -> CheckPipeline:
    mode = mode or settings.pipeline_mode
    retrieval_mode = retrieval_mode or settings.retrieval_mode
    rules = RuleEngine.from_file(settings.rules_path)
    config = PipelineConfig(mode=mode, thresholds=Thresholds(settings.t_reject, settings.t_approve))
    if mode == "rules_only":
        return CheckPipeline(rules, None, None, config)

    from openai import OpenAI

    key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
    if not key:
        raise RuntimeError("OPENAI_API_KEY kosong. Isi di .env, atau pakai PIPELINE_MODE=rules_only.")
    client = OpenAI(api_key=key, base_url=settings.openai_base_url or None,
                    timeout=settings.llm_timeout_seconds, max_retries=settings.llm_max_retries)

    embedder = None
    if retrieval_mode == "topk":
        embedder = (LocalEmbedder(settings.embedding_model) if settings.embedding_provider == "local"
                    else OpenAIEmbedder(client, settings.embedding_model))
    retriever = PolicyRetriever(load_policy_chunks(settings.policies_dir), embedder,
                                top_k=settings.retrieval_top_k, mode=retrieval_mode)
    judge = OpenAIJudge(client, settings.llm_model, settings.llm_temperature)
    return CheckPipeline(rules, retriever, judge, config)
