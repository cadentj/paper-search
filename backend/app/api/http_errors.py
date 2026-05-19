from fastapi import HTTPException

from app.services.errors import Conflict, EnqueueFailed, NotFound, ValidationFailed


def raise_http_from_service(exc: Exception) -> None:
    if isinstance(exc, NotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ValidationFailed):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, Conflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, EnqueueFailed):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    raise exc
