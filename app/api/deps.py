import secrets

from fastapi import Depends, Header, HTTPException, Request, status

from app.services.batch_service import BatchService
from app.services.check_service import CheckService


def require_api_key(request: Request, x_api_key: str | None = Header(default=None)) -> str:
    allowed: set[str] = request.app.state.api_keys
    # compare_digest: waktu perbandingan tidak bocor informasi tentang isi key
    if not x_api_key or not any(secrets.compare_digest(x_api_key, k) for k in allowed):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key tidak valid")
    return x_api_key


def get_check_service(request: Request, _: str = Depends(require_api_key)) -> CheckService:
    return request.app.state.check_service


def get_batch_service(request: Request, _: str = Depends(require_api_key)) -> BatchService:
    svc = request.app.state.batch_service
    if svc is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "batch tidak aktif: REDIS_URL tidak tersedia")
    return svc
