"""Deployment preparation only. No default DB, no live answer model, no signup."""
import os
from contextlib import asynccontextmanager
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from .demo_auth import PrivateDemoGate
from .google_auth import GoogleDemoGate
from .local_startup import SyntheticLocalProvider
from .postgres_repository import PostgresDocumentRepository
from .ingestion_service import BoundedParser,IngestionService
from .persisted_query import PersistedQueryService
from .upload_app import create_upload_app


def make_hosted_demo(settings, *, admission=None):
    if settings.get('ANSWER_GENERATION_ENABLED','false')!='false':
        raise ValueError('hosted preparation is retrieval-only')
    # Validate gate before touching any database or constructing expensive resources.
    username=settings.get('DEMO_USERNAME','')
    password=settings.get('DEMO_PASSWORD','')
    from urllib.parse import urlsplit
    origin=settings.get('DEMO_ORIGIN','')
    parts=urlsplit(origin)
    if parts.scheme!='https' or not parts.hostname or parts.username or parts.password or parts.path or parts.query or parts.fragment:
        raise ValueError('explicit HTTPS demo origin without path required')
    mode=settings.get('DEMO_AUTH_MODE','basic')
    if mode=='google':
        if settings.get('GOOGLE_OPERATIONS_ENABLED','false') not in ('true','false'):raise ValueError('explicit operation state required')
        gate=GoogleDemoGate(None,client_id=settings.get('GOOGLE_CLIENT_ID',''),
            allowed_emails=settings.get('GOOGLE_ALLOWED_EMAILS','').split(','),allowed_origin=origin,
            audience=settings.get('GOOGLE_AUDIENCE','allowlist'),
            operations_enabled=settings.get('GOOGLE_OPERATIONS_ENABLED','false')=='true')
    elif mode=='basic':
        if admission is not None:raise ValueError('execution admission requires verified Google tenant scope')
        gate=PrivateDemoGate(None,username=username,password=password,allowed_origin=origin)
    else:
        raise ValueError('explicit supported authentication mode required')
    try:
        url=make_url(settings['DATABASE_URL'])
        if url.drivername!='postgresql+psycopg' or not url.host or not url.database or not url.username or not url.password:
            raise ValueError()
        if url.query.get('sslmode')!='verify-full' or url.query.get('sslrootcert')!='system':raise ValueError()
    except Exception:
        raise ValueError('explicit TLS-verified PostgreSQL URL required') from None
    engine=None
    try:
        parser=BoundedParser(pdf_python=settings['RAG_PDF_PYTHON'],office_python=settings['RAG_OFFICE_PYTHON'])
        engine=create_engine(url,pool_size=2,max_overflow=0,pool_timeout=5,
            connect_args={'connect_timeout':5,'options':'-c statement_timeout=5000 -c lock_timeout=2000'})
        if mode=='google':
            from .tenant_dispatch import TenantDispatcher
            gate.app=TenantDispatcher(engine=engine,parser=parser,admission=admission)
            return gate
        repository=PostgresDocumentRepository(engine,dimension=3,embedding_profile='synthetic-hosted-demo-v1:dimension3')
        # Deliberately no automatic DDL. Provisioning belongs to separately approved setup.
        app=create_upload_app(service=IngestionService(parser=parser,provider=SyntheticLocalProvider(),repository=repository),
            query_service=PersistedQueryService(repository=repository,query_provider=SyntheticLocalProvider()),answer_cleanup=engine.dispose)
        gate.app=app
        return gate
    except BaseException:
        if engine is not None:engine.dispose()
        raise ValueError('hosted demo configuration failed') from None


if __name__=='__main__':
    import uvicorn
    try:
        port=int(os.environ.get('PORT','10000'))
        if not 1024<=port<=65535:raise ValueError()
    except ValueError:
        raise ValueError('valid explicit platform port required') from None
    # This bind is ONLY for an approved protected deployment. Never run as a tunnel.
    uvicorn.run(make_hosted_demo(os.environ),host='0.0.0.0',port=port,workers=1,access_log=False)
