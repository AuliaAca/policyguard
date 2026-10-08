from fastapi import APIRouter, Depends

from app.api.deps import get_batch_service
from app.schemas.api import BatchIn, BatchOut
from app.services.batch_service import BatchService

router = APIRouter(prefix="/v1", tags=["batches"])


@router.post("/batches", response_model=BatchOut, status_code=202)
def create_batch(body: BatchIn, svc: BatchService = Depends(get_batch_service)) -> BatchOut:
    # 202 Accepted: permintaan diterima, hasilnya belum ada. Pemanggil mengecek GET /v1/batches/{id}.
    batch_id = svc.create([l.model_dump() for l in body.listings])
    return BatchOut(**svc.status(batch_id))


@router.get("/batches/{batch_id}", response_model=BatchOut)
def get_batch(batch_id: str, svc: BatchService = Depends(get_batch_service)) -> BatchOut:
    return BatchOut(**svc.status(batch_id))
