"""Opt-in local raw-body upload app. No multipart prebuffering or provider default."""
import asyncio
import threading
import json
import urllib.parse
from pathlib import Path
from fastapi.responses import HTMLResponse
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect
from .ingestion_service import (MAX_BYTES, validate_metadata, IngestionRejected, IngestionBusy)
from .postgres_repository import (DocumentConflict, DocumentQuota,
                                  DocumentCommitUnknown, DocumentReadbackUnavailable)
from .execution_admission import AdmissionController, OperationBusy, OperationExpired


def create_upload_app(*, service, query_service=None, answer_service=None, answer_cleanup=None, document_service=None, admission=None, execution_tenant=None):
    if service is None:
        raise ValueError('explicit ingestion service required')
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if answer_cleanup is not None:
                answer_cleanup()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.get('/capabilities')
    async def capabilities():
        return {'answer_generation_enabled': answer_service is not None,
                'retrieval_mode': 'synthetic_not_semantic',
                'answer_provider': 'explicitly_configured' if answer_service is not None else None}
    if admission is not None and (not isinstance(admission,AdmissionController) or type(execution_tenant) is not str or not execution_tenant):
        raise ValueError('explicit verified execution tenant required')
    ingress_gate = threading.Lock()

    def admit(kind):
        return None if admission is None else admission.admit(tenant=execution_tenant,kind=kind)

    async def execute(lease, function, *args, **kwargs):
        if lease is None:
            return await run_in_threadpool(function,*args,**kwargs)
        return await lease.run(function,*args,**kwargs)

    @app.get('/', response_class=HTMLResponse)
    async def home():
        return Path(__file__).with_name('local_ui.html').read_text(encoding='utf-8')

    if document_service is not None:
        async def lifecycle_input(request):
            # No caller tenant, JSON body, filter or other selector is accepted.
            if request.url.query:
                raise ValueError('query parameters unsupported')
            async with asyncio.timeout(5):
                async for piece in request.stream():
                    if piece:
                        raise ValueError('request body unsupported')

        @app.get('/documents')
        async def list_documents(request: Request):
            try:
                await lifecycle_input(request)
                return await run_in_threadpool(document_service.list_documents)
            except (ValueError, TypeError):
                return JSONResponse({'error': 'invalid_document_request'}, status_code=422)
            except (TimeoutError, ClientDisconnect):
                return JSONResponse({'error': 'invalid_document_request'}, status_code=400)
            except Exception:
                return JSONResponse({'error': 'document_operation_failed'}, status_code=500)

        @app.get('/documents/{document_id}')
        async def document_details(document_id: str, request: Request):
            try:
                await lifecycle_input(request)
                result = await run_in_threadpool(document_service.document_details, document_id)
                if result is None:
                    return JSONResponse({'error': 'document_not_found'}, status_code=404)
                return result
            except (ValueError, TypeError):
                return JSONResponse({'error': 'invalid_document_request'}, status_code=422)
            except (TimeoutError, ClientDisconnect):
                return JSONResponse({'error': 'invalid_document_request'}, status_code=400)
            except Exception:
                return JSONResponse({'error': 'document_operation_failed'}, status_code=500)

        @app.delete('/documents/{document_id}')
        async def delete_document(document_id: str, request: Request):
            try:
                await lifecycle_input(request)
                deleted = await run_in_threadpool(document_service.delete_document, document_id)
                if not deleted:
                    return JSONResponse({'error': 'document_not_found'}, status_code=404)
                return {'status': 'deleted', 'document_id': document_id,
                        'deletion_scope': 'application_database_only',
                        'backup_erasure_guaranteed': False}
            except (ValueError, TypeError):
                return JSONResponse({'error': 'invalid_document_request'}, status_code=422)
            except (TimeoutError, ClientDisconnect):
                return JSONResponse({'error': 'invalid_document_request'}, status_code=400)
            except Exception:
                return JSONResponse({'error': 'document_operation_failed'}, status_code=500)

    @app.post('/query')
    async def query(request: Request):
        if query_service is None:
            return JSONResponse({'error': 'query_not_configured'}, status_code=503)
        lease=None
        data = bytearray()
        try:
            lease=admit('query')
            async with asyncio.timeout(10 if lease is None else min(10,lease.operation.remaining())):
                async for piece in request.stream():
                    if len(data)+len(piece) > 12000:
                        return JSONResponse({'error': 'query_too_large'}, status_code=413, headers={'Connection': 'close'})
                    data.extend(piece)
            value = json.loads(data)
            if not isinstance(value, dict) or set(value) - {'query', 'top_k'} or 'query' not in value:
                raise ValueError('invalid query shape')
            result = await execute(lease,query_service.query, value['query'], top_k=value.get('top_k', 5))
            if lease is not None:lease.operation.check()
            return JSONResponse(result)
        except OperationBusy:
            return JSONResponse({'error':'execution_busy'},status_code=503)
        except OperationExpired:
            return JSONResponse({'error':'operation_unconfirmed'},status_code=503)
        except (ValueError, TypeError, UnicodeError):
            return JSONResponse({'error': 'invalid_query'}, status_code=422)
        except TimeoutError:
            return JSONResponse({'error': 'query_receive_timeout'}, status_code=408, headers={'Connection': 'close'})
        except ClientDisconnect:
            return JSONResponse({'error': 'query_disconnected'}, status_code=400, headers={'Connection': 'close'})
        except Exception:
            return JSONResponse({'error': 'query_failed'}, status_code=500)
        finally:
            if lease is not None:lease.abandon()

    @app.post('/answer')
    async def answer(request: Request):
        if answer_service is None:
            return JSONResponse({'error':'answer_not_configured'}, status_code=503, headers={'Connection':'close'})
        from .answer_boundary import InvalidAnswerInput, ModelInvocationFailure, InvalidModelOutput
        data=bytearray()
        try:
            async with asyncio.timeout(10):
                async for piece in request.stream():
                    if len(data)+len(piece)>12000:
                        return JSONResponse({'error':'query_too_large'},status_code=413,headers={'Connection':'close'})
                    data.extend(piece)
            value=json.loads(data)
            if type(value) is not dict or set(value)-{'query','top_k'} or 'query' not in value:
                raise InvalidAnswerInput('invalid_answer_input')
            result=await run_in_threadpool(answer_service.answer,value['query'],top_k=value.get('top_k',5))
            return JSONResponse(result)
        except (InvalidAnswerInput,ValueError,TypeError,UnicodeError):
            return JSONResponse({'error':'invalid_answer_input'},status_code=422)
        except ModelInvocationFailure:
            return JSONResponse({'error':'model_invocation_failure'},status_code=502)
        except InvalidModelOutput:
            return JSONResponse({'error':'invalid_model_output'},status_code=502)
        except TimeoutError:
            return JSONResponse({'error':'answer_receive_timeout'},status_code=408,headers={'Connection':'close'})
        except ClientDisconnect:
            return JSONResponse({'error':'answer_disconnected'},status_code=400,headers={'Connection':'close'})
        except Exception:
            return JSONResponse({'error':'answer_failed'},status_code=500)

    @app.get('/health')
    async def health():
        return {'status': 'ok', 'mode': 'local-injected-only'}

    @app.post('/documents')
    async def upload(request: Request):
        mime = request.headers.get('content-type', '')
        filename = request.headers.get('x-filename', '')
        if request.headers.get('x-filename-encoding') == 'uri':
            try:
                filename = urllib.parse.unquote(filename, encoding='utf-8', errors='strict')
            except UnicodeError:
                return JSONResponse({'error': 'invalid_filename_encoding'}, status_code=415, headers={'Connection': 'close'})
        try:
            validate_metadata(filename, mime)
        except IngestionRejected:
            return JSONResponse({'error': 'unsupported_metadata'}, status_code=415, headers={'Connection': 'close'})
        length = request.headers.get('content-length')
        if length is not None:
            if not length.isascii() or not length.isdigit():
                return JSONResponse({'error': 'invalid_length'}, status_code=400, headers={'Connection': 'close'})
            if int(length) > MAX_BYTES:
                return JSONResponse({'error': 'upload_too_large'}, status_code=413, headers={'Connection': 'close'})
        if not ingress_gate.acquire(blocking=False):
            return JSONResponse({'error': 'upload_busy'}, status_code=503, headers={'Connection': 'close'})
        lease=None
        try:
            try:lease=admit('upload')
            except OperationBusy:return JSONResponse({'error':'execution_busy'},status_code=503)
            data = bytearray()
            try:
                async with asyncio.timeout(10 if lease is None else min(10,lease.operation.remaining())):
                    async for piece in request.stream():
                        if len(data) + len(piece) > MAX_BYTES:
                            return JSONResponse({'error': 'upload_too_large'}, status_code=413, headers={'Connection': 'close'})
                        data.extend(piece)
            except OperationExpired:
                return JSONResponse({'error':'operation_unconfirmed'},status_code=503)
            except TimeoutError:
                return JSONResponse({'error': 'upload_timeout'}, status_code=408, headers={'Connection': 'close'})
            except ClientDisconnect:
                return JSONResponse({'error': 'upload_disconnected'}, status_code=400, headers={'Connection': 'close'})
            try:
                result = await execute(lease,service.ingest_document, bytes(data),
                                                 filename=filename, content_type=mime)
                if lease is not None:lease.operation.check()
                return JSONResponse(result, status_code=200 if result['status'] == 'already_present' else 201)
            except (OperationExpired,OperationBusy):
                return JSONResponse({'error':'operation_unconfirmed'},status_code=503)
            except DocumentCommitUnknown as error:
                return JSONResponse({'error': ('document_transaction_unconfirmed'
                    if error.commit_state == 'not_attempted' else 'document_commit_unknown'),
                    'commit_state': error.commit_state, 'retry_allowed': False}, status_code=500)
            except DocumentReadbackUnavailable as error:
                return JSONResponse({'error': 'document_readback_unavailable',
                    'commit_state': error.commit_state, 'retry_allowed': False}, status_code=500)
            except DocumentQuota:
                return JSONResponse({'error':'sample_storage_limit_reached'},status_code=507)
            except DocumentConflict:
                return JSONResponse({'error': 'source_identity_conflict'}, status_code=409)
            except IngestionRejected:
                return JSONResponse({'error': 'document_rejected'}, status_code=422)
            except IngestionBusy:
                return JSONResponse({'error': 'upload_busy'}, status_code=503, headers={'Connection': 'close'})
            except Exception:
                return JSONResponse({'error': 'ingestion_failed'}, status_code=500)
        finally:
            if lease is not None:lease.abandon()
            ingress_gate.release()
    return app
