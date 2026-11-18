"""Deliberate loopback synthetic app startup, without test failure sentinels."""
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from .postgres_repository import PostgresDocumentRepository
from .ingestion_service import BoundedParser, IngestionService
from .persisted_query import PersistedQueryService
from .upload_app import create_upload_app

PROFILE = 'synthetic-local-demo-v1:dimension3'


class SyntheticLocalProvider:
    """Constant test direction, not meaning-based embeddings. No I/O or credentials."""
    def embed_documents(self, texts):
        return [[1., 0., 0.] for _ in texts]

    def embed_query(self, query):
        return [1., 0., 0.]


def make_local_app(*, socket_directory, database, pdf_python, office_python, answer_provider=None, own_answer_provider=False):
    if not Path(socket_directory).is_absolute() or not Path(socket_directory).is_dir():
        if own_answer_provider and answer_provider is not None:
            answer_provider.close()
        raise ValueError('existing local Unix socket directory required')
    engine = create_engine(URL.create('postgresql+psycopg', database=database,
        query={'host': socket_directory, 'port': '55437', 'connect_timeout': '5',
               'options': '-c statement_timeout=5000 -c lock_timeout=2000'}),
        pool_timeout=5, pool_size=2, max_overflow=0)
    try:
        repository = PostgresDocumentRepository(engine, dimension=3, embedding_profile=PROFILE)
        repository.create_schema()
        parser = BoundedParser(pdf_python=pdf_python, office_python=office_python)
        query_service=PersistedQueryService(repository=repository,query_provider=SyntheticLocalProvider())
        from .persisted_answer import PersistedAnswerService
        app = create_upload_app(service=IngestionService(parser=parser,
            provider=SyntheticLocalProvider(), repository=repository),query_service=query_service,
            answer_service=PersistedAnswerService(query_service=query_service,answer_provider=answer_provider) if answer_provider is not None else None,
            answer_cleanup=answer_provider.close if own_answer_provider and answer_provider is not None else None)
    except BaseException:
        engine.dispose()
        if own_answer_provider and answer_provider is not None:
            answer_provider.close()
        raise
    # Holds engine for normal server lifetime; no arbitrary URL/credential loading.
    app.state.engine = engine
    return app


if __name__ == '__main__':
    import uvicorn
    from .answer_config import configured_answer_provider
    answer_provider=None
    app=None
    try:
        answer_provider=configured_answer_provider(os.environ)
        app = make_local_app(socket_directory=os.environ['RAG_LOCAL_DB_SOCKET'],
            database=os.environ.get('RAG_LOCAL_DATABASE', 'rag_local_demo'),
            pdf_python=os.environ['RAG_PDF_PYTHON'], office_python=os.environ['RAG_OFFICE_PYTHON'],
            answer_provider=answer_provider,own_answer_provider=answer_provider is not None)
        uvicorn.run(app, host='127.0.0.1', port=58219, workers=1)
    finally:
        if app is not None:app.state.engine.dispose()
        if answer_provider is not None:answer_provider.close()
