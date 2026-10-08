from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

router = APIRouter(tags=["ops"])


@router.get("/health")
def health(request: Request, response: Response) -> dict:
    """ok = semua komponen siap. degraded = service berjalan tapi sebagian keputusan akan fallback."""
    state = request.app.state
    checks = {}
    try:
        with state.session_factory() as s:
            s.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {type(e).__name__}"

    retriever = state.check_service.pipeline.retriever
    if retriever is not None:
        try:
            retriever.ensure_index()
            checks["policy_index"] = "ok"
        except Exception as e:
            checks["policy_index"] = f"error: {type(e).__name__}"

    if state.batch_service is not None:
        try:
            state.redis.ping()
            checks["queue"] = "ok"
        except Exception as e:
            checks["queue"] = f"error: {type(e).__name__}"

    healthy = all(v == "ok" for v in checks.values())
    if checks["database"] != "ok":
        response.status_code = 503
    return {"status": "ok" if healthy else "degraded", "pipeline_mode": state.check_service.pipeline.config.mode,
            "model": state.check_service.pipeline.model_name,
            "policy_version": state.check_service.policy_version, "checks": checks}


@router.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
