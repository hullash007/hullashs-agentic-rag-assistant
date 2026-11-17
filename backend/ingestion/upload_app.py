"""Opt-in local raw-body upload app. No multipart prebuffering or provider default."""
import asyncio
import threading
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect
from .ingestion_service import (MAX_BYTES, validate_metadata, IngestionRejected, IngestionBusy)
from .postgres_repository import DocumentConflict


def create_upload_app(*, service):
    if service is None:
        raise ValueError('explicit ingestion service required')
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    ingress_gate = threading.Lock()

    @app.get('/health')
    async def health():
        return {'status': 'ok', 'mode': 'local-injected-only'}

    @app.post('/documents')
    async def upload(request: Request):
        mime = request.headers.get('content-type', '')
        filename = request.headers.get('x-filename', '')
        try:
            validate_metadata(filename, mime)
        except IngestionRejected:
            return JSONResponse({'error': 'unsupported_metadata'}, status_code=415)
        length = request.headers.get('content-length')
        if length is not None:
            if not length.isascii() or not length.isdigit():
                return JSONResponse({'error': 'invalid_length'}, status_code=400)
            if int(length) > MAX_BYTES:
                return JSONResponse({'error': 'upload_too_large'}, status_code=413)
        if not ingress_gate.acquire(blocking=False):
            return JSONResponse({'error': 'upload_busy'}, status_code=503)
        try:
            data = bytearray()
            try:
                async with asyncio.timeout(10):
                    async for piece in request.stream():
                        if len(data) + len(piece) > MAX_BYTES:
                            return JSONResponse({'error': 'upload_too_large'}, status_code=413)
                        data.extend(piece)
            except TimeoutError:
                return JSONResponse({'error': 'upload_timeout'}, status_code=408)
            except ClientDisconnect:
                return JSONResponse({'error': 'upload_disconnected'}, status_code=400)
            try:
                result = await run_in_threadpool(service.ingest_document, bytes(data),
                                                 filename=filename, content_type=mime)
                return JSONResponse(result, status_code=200 if result['status'] == 'already_present' else 201)
            except DocumentConflict:
                return JSONResponse({'error': 'source_identity_conflict'}, status_code=409)
            except IngestionRejected:
                return JSONResponse({'error': 'document_rejected'}, status_code=422)
            except IngestionBusy:
                return JSONResponse({'error': 'upload_busy'}, status_code=503)
            except Exception:
                return JSONResponse({'error': 'ingestion_failed'}, status_code=500)
        finally:
            ingress_gate.release()
    return app
