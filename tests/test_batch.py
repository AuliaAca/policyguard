import fakeredis
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.batch_service import QUEUE_KEY, process_one
from conftest import FakeJudge, judge_json, make_pipeline

H = {"X-API-Key": "test-key"}


def listing(i, title):
    return {"listing_id": f"B{i}", "title": title, "category": "Kesehatan", "price": 50000}


def test_batch_is_queued_then_processed_by_worker(tmp_path):
    r = fakeredis.FakeRedis()
    judge = FakeJudge(*[judge_json("compliant", confidence=0.95)] * 5)
    s = Settings(database_url=f"sqlite:///{tmp_path}/b.db", service_api_keys="test-key")
    with TestClient(create_app(s, pipeline=make_pipeline(judge=judge), redis_client=r)) as c:
        resp = c.post("/v1/batches", headers=H, json={"listings": [
            listing(1, "Vitamin B kompleks 100 tablet"), listing(2, "Jual Xanax tanpa resep")]})
        assert resp.status_code == 202
        batch = resp.json()
        assert batch["status"] == "processing" and batch["pending"] == 2
        assert r.llen(QUEUE_KEY) == 2

        # Jalankan logika worker untuk setiap item di antrian
        state = c.app.state
        while (item := r.rpop(QUEUE_KEY)) is not None:
            assert process_one(item.decode(), state.session_factory, state.check_service, r) == "done"

        done = c.get(f"/v1/batches/{batch['batch_id']}", headers=H).json()
        assert done["status"] == "completed" and done["done"] == 2
        assert done["decisions"] == {"approve": 1, "reject": 1}


def test_processing_same_item_twice_is_skipped(tmp_path):
    r = fakeredis.FakeRedis()
    s = Settings(database_url=f"sqlite:///{tmp_path}/b2.db", service_api_keys="test-key")
    with TestClient(create_app(s, pipeline=make_pipeline(judge=FakeJudge(judge_json(confidence=0.95))),
                               redis_client=r)) as c:
        c.post("/v1/batches", headers=H, json={"listings": [listing(1, "Vitamin B kompleks 100 tablet")]})
        item = r.rpop(QUEUE_KEY).decode()
        st = c.app.state
        assert process_one(item, st.session_factory, st.check_service, r) == "done"
        assert process_one(item, st.session_factory, st.check_service, r) == "skipped"


def test_batch_returns_503_when_queue_down(tmp_path):
    class DeadRedis:
        def lpush(self, *a):
            raise ConnectionError("redis mati")
    s = Settings(database_url=f"sqlite:///{tmp_path}/b3.db", service_api_keys="test-key")
    with TestClient(create_app(s, pipeline=make_pipeline(), redis_client=DeadRedis())) as c:
        resp = c.post("/v1/batches", headers=H, json={"listings": [listing(1, "Vitamin B kompleks")]})
        assert resp.status_code == 503
