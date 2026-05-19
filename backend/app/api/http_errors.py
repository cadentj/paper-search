from fastapi import HTTPException


def raise_http_from_service(exc: Exception) -> None:
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, FileExistsError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ConnectionError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    raise exc
