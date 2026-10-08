"""Titik masuk aplikasi: merakit semua komponen saat startup.

Menjalankan:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ai.factory import build_pipeline
from ai.policies import compute_policy_version, load_policy_chunks
from app.api import routes_batches, routes_checks, routes_ops
from app.core import metrics
from app.core.config import Settings, get_settings
from app.core.logging import new_request_id, request_id_var, setup_logging
from app.db.session import init_db, make_session_factory
from app.services.batch_service import BatchService
from app.services.check_service import CheckService, NotFound, ServiceUnavailable

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, pipeline=None, redis_client=None) -> FastAPI:
    """pipeline dan redis_client bisa diganti dari luar (dipakai test)."""
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not settings.api_keys:
            raise RuntimeError("SERVICE_API_KEYS kosong: API tidak boleh berjalan tanpa autentikasi")
        session_factory = make_session_factory(settings.database_url)
        init_db(session_factory)
        p = pipeline or build_pipeline(settings)
        policy_version = compute_policy_version(settings.policies_dir)
        app.state.policies = load_policy_chunks(settings.policies_dir)

        r = redis_client
        if r is None and settings.redis_url:
            import redis
            r = redis.Redis.from_url(settings.redis_url)

        app.state.api_keys = settings.api_keys
        app.state.session_factory = session_factory
        app.state.check_service = CheckService(session_factory, p, policy_version)
        app.state.redis = r
        app.state.batch_service = BatchService(session_factory, r) if r is not None else None
        log.info("service siap", extra={"pipeline_mode": p.config.mode, "model": p.model_name,
                                        "policy_version": policy_version})
        yield

    app = FastAPI(title="PolicyGuard", version="1.0.0", lifespan=lifespan)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id") or new_request_id()
        token = request_id_var.set(rid)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["x-request-id"] = rid
            return response
        finally:
            route = request.scope.get("route")
            path = route.path if route else "unmatched"   # pakai pola route agar label metrik tidak meledak
            metrics.REQUEST_LATENCY.labels(path, request.method, str(status)).observe(time.perf_counter() - start)
            request_id_var.reset(token)

    @app.exception_handler(ServiceUnavailable)
    async def _unavailable(request: Request, exc: ServiceUnavailable):
        return JSONResponse(status_code=503, content={"detail": "layanan sementara tidak tersedia, silakan coba lagi",
                                                      "request_id": request_id_var.get()})

    @app.exception_handler(NotFound)
    async def _not_found(request: Request, exc: NotFound):
        return JSONResponse(status_code=404, content={"detail": f"tidak ditemukan: {exc}"})

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        log.exception("error tak terduga")
        return JSONResponse(status_code=500, content={"detail": "internal error", "request_id": request_id_var.get()})

    app.include_router(routes_checks.router)
    app.include_router(routes_batches.router)
    app.include_router(routes_ops.router)
    return app


app = create_app()
