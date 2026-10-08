"""Menguji kode integrasi OpenAI terhadap server HTTP tiruan yang meniru format API OpenAI.

Yang terbukti: request yang dikirim berbentuk benar (structured output, strict schema),
dan response API diurai dengan benar (isi, token usage, embedding, error).
Yang TIDAK terbukti: perilaku model sungguhan. Itu hanya bisa diuji dengan API key asli.
"""
import json
import socket
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from openai import OpenAI

from ai.llm import LLMUnavailable, OpenAIJudge
from ai.retrieval import OpenAIEmbedder, PolicyRetriever
from conftest import CHUNKS, judge_json, make_listing

captured: list[dict] = []
fake = FastAPI()


@fake.post("/v1/chat/completions")
async def chat(req: Request):
    body = await req.json()
    captured.append(body)
    if body["model"] == "model-error":
        return JSONResponse(status_code=500, content={"error": {"message": "server error", "type": "server_error"}})
    content = json.dumps(judge_json("compliant", confidence=0.9))
    return {"id": "c1", "object": "chat.completion", "created": 0, "model": body["model"],
            "choices": [{"index": 0, "finish_reason": "stop", "logprobs": None,
                         "message": {"role": "assistant", "content": content, "refusal": None}}],
            "usage": {"prompt_tokens": 321, "completion_tokens": 45, "total_tokens": 366}}


@fake.post("/v1/embeddings")
async def embeddings(req: Request):
    body = await req.json()
    texts = body["input"] if isinstance(body["input"], list) else [body["input"]]
    # Vektor sederhana: kata kunci tertentu -> dimensi tertentu, supaya retrieval bisa diuji
    def vec(t):
        t = t.lower()
        return [float("sembuh" in t), float("senjata" in t or "pistol" in t), float("rokok" in t), 0.1]
    return {"object": "list", "model": body["model"], "usage": {"prompt_tokens": 1, "total_tokens": 1},
            "data": [{"object": "embedding", "index": i, "embedding": vec(t)} for i, t in enumerate(texts)]}


@pytest.fixture(scope="module")
def base_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(fake, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    yield f"http://127.0.0.1:{port}/v1"
    server.should_exit = True


@pytest.fixture
def client(base_url):
    return OpenAI(api_key="sk-test", base_url=base_url, max_retries=0, timeout=5)


def test_judge_sends_strict_schema_and_parses_usage(client):
    captured.clear()
    resp = OpenAIJudge(client, "model-ok", temperature=0).complete([{"role": "user", "content": "hai"}])
    assert json.loads(resp.text)["verdict"] == "compliant"
    assert (resp.prompt_tokens, resp.completion_tokens) == (321, 45)
    sent = captured[-1]
    assert sent["response_format"]["type"] == "json_schema"
    assert sent["response_format"]["json_schema"]["strict"] is True
    assert sent["temperature"] == 0


def test_judge_omits_temperature_when_none(client):
    captured.clear()
    OpenAIJudge(client, "model-ok", temperature=None).complete([{"role": "user", "content": "hai"}])
    assert "temperature" not in captured[-1]


def test_server_error_becomes_llm_unavailable(client):
    with pytest.raises(LLMUnavailable):
        OpenAIJudge(client, "model-error").complete([{"role": "user", "content": "hai"}])


def test_embedding_retrieval_ranks_relevant_policy_first(client):
    retriever = PolicyRetriever(CHUNKS, OpenAIEmbedder(client, "embed-model"), top_k=3)
    top = retriever.retrieve(make_listing(title="Kopi herbal bisa sembuhkan diabetes"))
    assert top[0][0].policy_id == "POL-HLT-01"       # satu-satunya pasal yang memuat kata 'sembuh'
    assert len(top) == 3
