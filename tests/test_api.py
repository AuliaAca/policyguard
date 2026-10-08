import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.main import create_app
from conftest import FakeJudge, judge_json, make_pipeline

H = {"X-API-Key": "test-key"}
BODY = {"listing_id": "A1", "title": "Teh jahe merah untuk menghangatkan badan",
        "category": "Makanan & Minuman", "price": 35000}


@pytest.fixture
def judge():
    # Cukup banyak jawaban "compliant" untuk beberapa panggilan
    return FakeJudge(*[judge_json("compliant", confidence=0.95)] * 10)


@pytest.fixture
def client(tmp_path, judge):
    s = Settings(database_url=f"sqlite:///{tmp_path}/t.db", service_api_keys="test-key", redis_url="")
    with TestClient(create_app(s, pipeline=make_pipeline(judge=judge))) as c:
        yield c


def test_requires_api_key(client):
    assert client.post("/v1/checks", json=BODY).status_code == 401
    assert client.post("/v1/checks", json=BODY, headers={"X-API-Key": "salah"}).status_code == 401


def test_validation_rejects_long_description_without_calling_llm(client, judge):
    r = client.post("/v1/checks", headers=H, json={**BODY, "description": "x" * 5001})
    assert r.status_code == 422 and judge.calls == []


def test_validation_rejects_unknown_category_and_bad_price(client):
    assert client.post("/v1/checks", headers=H, json={**BODY, "category": "Senjata"}).status_code == 422
    assert client.post("/v1/checks", headers=H, json={**BODY, "price": 0}).status_code == 422


def test_check_returns_decision_and_versions(client):
    r = client.post("/v1/checks", headers=H, json=BODY)
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "approve" and body["versions"]["model"] == "fake-model"
    assert r.headers["x-request-id"]


def test_idempotent_retry_returns_same_check(client, judge):
    first = client.post("/v1/checks", headers=H, json=BODY).json()
    second = client.post("/v1/checks", headers=H, json=BODY).json()
    assert first["check_id"] == second["check_id"]
    assert len(judge.calls) == 1                     # LLM hanya dipanggil sekali


def test_same_content_other_listing_uses_cache(client, judge):
    client.post("/v1/checks", headers=H, json=BODY)
    r = client.post("/v1/checks", headers=H, json={**BODY, "listing_id": "B2"}).json()
    assert r["cached"] is True and len(judge.calls) == 1


def test_price_change_is_not_a_cache_hit(client, judge):
    client.post("/v1/checks", headers=H, json=BODY)
    r = client.post("/v1/checks", headers=H, json={**BODY, "listing_id": "B2", "price": 99000}).json()
    assert r["cached"] is False and len(judge.calls) == 2


def test_fallback_result_is_not_cached(tmp_path):
    from ai.llm import LLMUnavailable
    judge = FakeJudge(LLMUnavailable("down"), judge_json("compliant", confidence=0.95))
    s = Settings(database_url=f"sqlite:///{tmp_path}/f.db", service_api_keys="test-key", redis_url="")
    with TestClient(create_app(s, pipeline=make_pipeline(judge=judge))) as c:
        first = c.post("/v1/checks", headers=H, json=BODY).json()
        second = c.post("/v1/checks", headers=H, json={**BODY, "listing_id": "B2"}).json()
    assert first["review_reason"] == "llm_unavailable"
    assert second["decision"] == "approve" and second["cached"] is False


def test_database_failure_returns_503(client, monkeypatch):
    from app.db import repository

    def boom(*a, **k):
        raise OperationalError("SELECT", {}, Exception("db down"))
    monkeypatch.setattr(repository, "find_by_idempotency_key", boom)
    r = client.post("/v1/checks", headers=H, json=BODY)
    assert r.status_code == 503 and "request_id" in r.json()


def test_review_flow_and_queue(tmp_path):
    from ai.llm import LLMUnavailable
    s = Settings(database_url=f"sqlite:///{tmp_path}/r.db", service_api_keys="test-key", redis_url="")
    with TestClient(create_app(s, pipeline=make_pipeline(judge=FakeJudge(LLMUnavailable("x"))))) as c:
        check = c.post("/v1/checks", headers=H, json=BODY).json()
        queue = c.get("/v1/checks", headers=H, params={"decision": "needs_review", "unreviewed": True}).json()
        assert [q["check_id"] for q in queue] == [check["check_id"]]

        r = c.post(f"/v1/checks/{check['check_id']}/review", headers=H,
                   json={"moderator_id": "m1", "final_decision": "approve"})
        assert r.status_code == 201
        assert c.get("/v1/checks", headers=H, params={"decision": "needs_review", "unreviewed": True}).json() == []
        assert c.get(f"/v1/checks/{check['check_id']}", headers=H).json()["reviewed"] is True
        assert c.get("/v1/checks/tidak-ada", headers=H).status_code == 404
        assert c.get("/v1/stats", headers=H).json()["reviews"] == 1


def test_health_and_metrics(client):
    client.post("/v1/checks", headers=H, json=BODY)
    assert client.get("/health").json()["checks"]["database"] == "ok"
    text = client.get("/metrics").text
    assert 'policyguard_checks_total{cached="false",decided_by="llm",decision="approve"}' in text


def test_refuses_to_start_without_api_keys(tmp_path):
    s = Settings(database_url=f"sqlite:///{tmp_path}/k.db", service_api_keys="", redis_url="")
    with pytest.raises(RuntimeError, match="SERVICE_API_KEYS"):
        with TestClient(create_app(s, pipeline=make_pipeline())):
            pass


def test_policy_version_change_invalidates_cache(tmp_path):
    """Kebijakan berubah -> listing dengan isi sama harus dinilai ulang, bukan diambil dari cache."""
    from ai.types import Listing
    from app.db.session import init_db, make_session_factory
    from app.services.check_service import CheckService

    sessions = make_session_factory(f"sqlite:///{tmp_path}/v.db")
    init_db(sessions)
    judge = FakeJudge(*[judge_json("compliant", confidence=0.95)] * 3)
    pipeline = make_pipeline(judge=judge)
    listing = lambda lid: Listing(lid, "Teh jahe merah untuk menghangatkan badan", "", "Makanan & Minuman", 35000)

    CheckService(sessions, pipeline, policy_version="v1").check(listing("A"))
    same = CheckService(sessions, pipeline, policy_version="v1").check(listing("B"))
    new_policy = CheckService(sessions, pipeline, policy_version="v2").check(listing("C"))
    assert same.cached is True
    assert new_policy.cached is False and len(judge.calls) == 2


def test_reject_review_requires_policy_and_history_shows_final_decision(tmp_path):
    from ai.llm import LLMUnavailable
    s = Settings(database_url=f"sqlite:///{tmp_path}/h.db", service_api_keys="test-key", redis_url="")
    judge = FakeJudge(LLMUnavailable("x"), LLMUnavailable("x"))
    with TestClient(create_app(s, pipeline=make_pipeline(judge=judge))) as c:
        first = c.post("/v1/checks", headers=H, json=BODY).json()
        second = c.post("/v1/checks", headers=H, json={**BODY, "listing_id": "B2", "price": 40000}).json()

        bad = c.post(f"/v1/checks/{first['check_id']}/review", headers=H,
                     json={"moderator_id": "m1", "final_decision": "reject"})
        assert bad.status_code == 422                     # reject tanpa pasal ditolak
        ok = c.post(f"/v1/checks/{first['check_id']}/review", headers=H,
                    json={"moderator_id": "m1", "final_decision": "reject", "policy_ids": ["POL-HLT-01"]})
        assert ok.status_code == 201

        history = c.get("/v1/checks", headers=H, params={"order": "newest"}).json()
        assert [h["check_id"] for h in history] == [second["check_id"], first["check_id"]]
        assert history[1]["final_decision"] == "reject" and history[1]["reviewed"] is True
        assert history[0]["final_decision"] is None


def test_policies_endpoint(client):
    assert client.get("/v1/policies").status_code == 401
    policies = client.get("/v1/policies", headers=H).json()
    assert len(policies) == 15 and policies[0]["policy_id"].startswith("POL-")


def test_low_confidence_violation_is_shown_as_ai_suggestion(tmp_path):
    """AI ragu -> tidak reject otomatis, tetapi dugaannya tetap terlihat oleh moderator."""
    judge = FakeJudge(judge_json("violating", [("POL-HLT-01", "sembuhkan diabetes")], confidence=0.5))
    s = Settings(database_url=f"sqlite:///{tmp_path}/s.db", service_api_keys="test-key", redis_url="")
    with TestClient(create_app(s, pipeline=make_pipeline(judge=judge))) as c:
        check = c.post("/v1/checks", headers=H, json={**BODY, "title": "Kopi herbal, bisa sembuhkan diabetes"}).json()
        assert check["decision"] == "needs_review" and check["violations"] == []
        detail = c.get(f"/v1/checks/{check['check_id']}", headers=H).json()
        assert detail["verdict"] == "violating"
        assert detail["ai_suggestions"][0]["evidence"] == "sembuhkan diabetes"
