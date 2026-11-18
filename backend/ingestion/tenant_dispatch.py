"""Immutable per-request repository scope from verified Google identity only.
No user-selected IDs, global current-user state, automatic DDL or legacy assignment.
"""
from starlette.responses import JSONResponse
from .postgres_repository import PostgresDocumentRepository
from .ingestion_service import IngestionService
from .persisted_query import PersistedQueryService
from .local_startup import SyntheticLocalProvider
from .upload_app import create_upload_app
from .document_management import DocumentManagementService

class TenantDispatcher:
    def __init__(self,*,engine,parser,admission=None):
        self.engine=engine;self.parser=parser;self.admission=admission

    async def __call__(self,scope,receive,send):
        if scope['type']=='lifespan':
            while True:
                message=await receive()
                if message['type']=='lifespan.startup':await send({'type':'lifespan.startup.complete'})
                elif message['type']=='lifespan.shutdown':
                    if self.admission is not None:
                        import asyncio
                        await asyncio.to_thread(self.admission.shutdown,wait=True)
                    self.engine.dispose();await send({'type':'lifespan.shutdown.complete'});return
        sub=scope.get('rag.google_sub')
        if type(sub) is not str or not sub:
            return await JSONResponse({'error':'authentication_required'},status_code=401)(scope,receive,send)
        repository=PostgresDocumentRepository(self.engine,dimension=3,
            embedding_profile='synthetic-hosted-demo-v1:dimension3',tenant_subject=sub)
        app=create_upload_app(service=IngestionService(parser=self.parser,provider=SyntheticLocalProvider(),repository=repository),
            query_service=PersistedQueryService(repository=repository,query_provider=SyntheticLocalProvider()),
            document_service=DocumentManagementService(repository),admission=self.admission,execution_tenant=sub)
        return await app(scope,receive,send)
