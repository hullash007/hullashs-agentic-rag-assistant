"""Disposable local PostgreSQL only. Never accepts a remote URL or hosted data."""
import os, re, sys, time
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from starlette.testclient import TestClient
from backend.ingestion.postgres_repository import PostgresDocumentRepository
from backend.ingestion.document_management import DocumentManagementService
from backend.ingestion.ingestion_service import BoundedParser, IngestionService
from backend.ingestion.local_startup import SyntheticLocalProvider
from backend.ingestion.tenant_dispatch import TenantDispatcher
from backend.ingestion.google_auth import GoogleDemoGate

SOCKET = os.environ.get('RAG_LIFECYCLE_TEST_SOCKET')
pytestmark = pytest.mark.skipif(not SOCKET, reason='explicit disposable local socket required')
PROFILE = 'synthetic-hosted-demo-v1:dimension3'
ORIGIN = 'https://demo.example'
CID = '123456-test.apps.googleusercontent.com'

@pytest.fixture
def env():
    assert SOCKET == '/downloads/rag-google/lifecycle-db/socket'
    engine = create_engine(URL.create('postgresql+psycopg', database='rag_lifecycle_test',
        query={'host': SOCKET, 'port': '55439'}), pool_size=3, max_overflow=0)
    parser = BoundedParser(pdf_python=sys.executable, office_python=sys.executable)
    def repo(sub):
        return PostgresDocumentRepository(engine, dimension=3, embedding_profile=PROFILE, tenant_subject=sub)
    base = repo(None)
    base.create_schema()
    with engine.begin() as c:
        assert c.execute(text('select count(*) from rag_documents')).scalar_one() == 0
    def seed(sub, value=b'FABRICATED shared sample', filename='same.txt'):
        return IngestionService(parser=parser, provider=SyntheticLocalProvider(), repository=repo(sub)).ingest_document(
            value, filename=filename, content_type='text/plain')['document_id']
    claims = {}
    gate = GoogleDemoGate(TenantDispatcher(engine=engine, parser=parser), client_id=CID,
        allowed_emails=[], allowed_origin=ORIGIN, audience='any_google', verifier=lambda token, cid: claims[token])
    def login(sub):
        client = TestClient(gate, base_url=ORIGIN)
        nonce = re.search("nonce:'([^']+)'", client.get('/').text).group(1)
        token = sub * 40
        claims[token] = {'sub': sub, 'email': 'same@example.org', 'email_verified': True,
            'aud': CID, 'iss': 'https://accounts.google.com', 'exp': time.time()+3600, 'nonce': nonce}
        assert client.post('/auth/login', headers={'Origin': ORIGIN}, json={'nonce': nonce, 'credential': token}).status_code == 200
        return client, {'Origin': ORIGIN, 'X-RAG-CSRF': client.get('/auth/status').json()['csrf']}
    yield engine, repo, seed, login, gate
    # This database is created solely for this file, no existing records retained.
    base.metadata.drop_all(engine)
    engine.dispose()


def test_own_listing_details_and_foreign_absence(env):
    engine, repo, seed, login, gate = env
    a_id, b_id, legacy_id = seed('A'), seed('B'), seed(None)
    assert len({a_id, b_id, legacy_id}) == 3
    a, ha = login('A'); b, hb = login('B')
    for client, headers, own, foreign in ((a, ha, a_id, b_id), (b, hb, b_id, a_id)):
        listing = client.get('/documents').json()
        assert [x['document_id'] for x in listing['documents']] == [own]
        assert listing['retention'] == {'automatic_expiry': False, 'logout_deletes_documents': False,
            'deletion_scope': 'application_database_only', 'backup_erasure_guaranteed': False}
        details = client.get('/documents/'+own)
        assert details.status_code == 200 and details.json() == listing['documents'][0]
        assert details.json()['filename'] == 'same.txt'
        assert details.json()['byte_size'] == len(b'FABRICATED shared sample')
        assert 'source_id' not in details.json() and 'original_bytes' not in details.json()
        for denied in (foreign, legacy_id, '0'*64):
            response = client.get('/documents/'+denied)
            assert response.status_code == 404 and response.json() == {'error': 'document_not_found'}
            response = client.delete('/documents/'+denied, headers=headers)
            assert response.status_code == 404 and response.json() == {'error': 'document_not_found'}
    assert repo('A').load_document(a_id).original_bytes == b'FABRICATED shared sample'
    assert repo('B').load_document(b_id).original_bytes == b'FABRICATED shared sample'
    assert repo(None).load_document(legacy_id).original_bytes == b'FABRICATED shared sample'


def test_delete_cascade_repeat_and_other_owner_untouched(env):
    engine, repo, seed, login, gate = env
    a_id, b_id, legacy_id = seed('A'), seed('B'), seed(None)
    a, ha = login('A')
    out = a.delete('/documents/'+a_id, headers=ha)
    assert out.status_code == 200 and out.json()['deletion_scope'] == 'application_database_only'
    assert out.json()['backup_erasure_guaranteed'] is False
    assert a.get('/documents').json()['documents'] == []
    assert a.get('/documents/'+a_id).status_code == 404
    assert a.delete('/documents/'+a_id, headers=ha).status_code == 404
    assert not repo('A').retrieve([1.,0.,0.], top_k=5)
    with engine.connect() as c:
        for table in ('rag_documents','rag_located_chunks','rag_chunk_embeddings'):
            assert c.execute(text('select count(*) from '+table)).scalar_one() == 2
    assert repo('B').load_document(b_id) and repo(None).load_document(legacy_id)
    assert seed('A') == a_id  # Freed quota, stable original content identity.


@pytest.mark.parametrize('stage', ['vectors_deleted', 'chunks_deleted', 'document_deleted'])
def test_delete_rollback_at_each_stage(env, stage):
    engine, repo, seed, login, gate = env
    key = seed('A'); r = repo('A')
    def fail(at):
        if at == stage:
            raise RuntimeError('local injected rollback')
    with pytest.raises(RuntimeError):
        r.delete_document(key, _checkpoint=fail)
    assert r.load_document(key).original_bytes == b'FABRICATED shared sample'
    with engine.connect() as c:
        assert all(c.execute(text('select count(*) from '+t)).scalar_one() == 1
            for t in ('rag_documents','rag_located_chunks','rag_chunk_embeddings'))


def test_delete_is_race_safe_and_idempotent(env):
    engine, repo, seed, login, gate = env
    key = seed('A')
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(lambda _: repo('A').delete_document(key), range(2)))
    assert sorted(result) == [False, True]
    assert not repo('A').list_documents()


def test_fail_closed_identity_origin_csrf_and_operation_switch(env):
    engine, repo, seed, login, gate = env
    key = seed('A'); a, ha = login('A')
    anon = TestClient(gate, base_url=ORIGIN)
    assert anon.get('/documents').status_code == 401
    assert anon.get('/documents/'+key).status_code == 401
    assert anon.delete('/documents/'+key, headers={'Origin': ORIGIN}).status_code == 401
    assert a.delete('/documents/'+key, headers={'Origin': ORIGIN}).status_code == 403
    assert a.delete('/documents/'+key, headers={'Origin':'https://foreign.invalid','X-RAG-CSRF':ha['X-RAG-CSRF']}).status_code == 403
    gate.operations_enabled = False
    assert a.get('/documents').status_code == 503
    assert a.get('/documents/'+key).status_code == 503
    assert a.delete('/documents/'+key, headers=ha).status_code == 503
    assert repo('A').load_document(key)


@pytest.mark.parametrize('bad', ['foreign', 'A'*64, '1'*65, '1'*63])
def test_invalid_id_uniformly_rejected(env, bad):
    engine, repo, seed, login, gate = env
    a, ha = login('A')
    assert a.get('/documents/'+bad).status_code == 422
    assert a.delete('/documents/'+bad, headers=ha).status_code == 422


def test_tenant_spoofing_and_unknown_inputs_rejected(env):
    engine, repo, seed, login, gate = env
    ka, kb = seed('A'), seed('B')
    a, ha = login('A')
    spoof = {**ha, 'X-Google-Sub':'B', 'X-Tenant-ID':'B'}
    assert a.get('/documents',headers=spoof).json()['documents'][0]['document_id'] == ka
    assert a.get('/documents/'+kb, headers=spoof).status_code == 404
    assert a.get('/documents?tenant_id=B').status_code == 422
    assert a.request('GET','/documents/'+ka,content=b'{}').status_code == 422
    assert a.request('DELETE','/documents/'+ka,headers=ha,json={'tenant_id':'B'}).status_code == 422
    assert repo('A').load_document(ka) and repo('B').load_document(kb)


def test_logout_relogin_and_process_reconstruction(env):
    engine, repo, seed, login, gate = env
    key = seed('A'); a, ha = login('A')
    assert a.post('/auth/logout',headers=ha).status_code == 200
    assert a.get('/documents').status_code == 401
    again, _ = login('A')
    assert again.get('/documents').json()['documents'][0]['document_id'] == key
    engine.dispose()  # New pool/repository, same disposable data.
    assert DocumentManagementService(repo('A')).document_details(key)['document_id'] == key


def test_legacy_lifecycle_is_explicitly_unavailable(env):
    engine, repo, seed, login, gate = env
    base = repo(None)
    with pytest.raises(ValueError): DocumentManagementService(base)
    for method in (base.list_documents, lambda:base.document_details('0'*64), lambda:base.delete_document('0'*64)):
        with pytest.raises(ValueError): method()


def test_delete_frees_full_document_quota(env):
    from backend.ingestion.postgres_repository import DocumentQuota
    engine, repo, seed, login, gate = env
    keys = [seed('A', ('fabricated '+str(i)).encode(), str(i)+'.txt') for i in range(20)]
    with pytest.raises(DocumentQuota): seed('A', b'over limit')
    assert repo('A').delete_document(keys[0])
    seed('A', b'replacement fabricated sample')
    assert len(repo('A').list_documents()) == 20


def test_api_errors_do_not_leak_database_exception(env, monkeypatch):
    engine, repo, seed, login, gate = env
    key = seed('A'); a, ha = login('A')
    def fail(*args, **kwargs): raise RuntimeError('private fake database detail')
    monkeypatch.setattr(PostgresDocumentRepository, 'delete_document', fail)
    result = a.delete('/documents/'+key, headers=ha)
    assert result.status_code == 500 and result.json() == {'error':'document_operation_failed'}
    assert repo('A').load_document(key)


def test_legacy_and_unconfigured_apps_have_no_lifecycle_routes(env):
    from backend.ingestion.upload_app import create_upload_app
    engine, repo, seed, login, gate = env
    client = TestClient(create_upload_app(service=object()))
    assert client.get('/documents').status_code == 405
    assert client.get('/documents/'+'0'*64).status_code == 404
    assert client.delete('/documents/'+'0'*64).status_code == 404


def test_delete_removes_all_chunks_not_only_first(env):
    engine, repo, seed, login, gate = env
    key = seed('A', ('fabricated long sample ' * 170).encode(), 'long.txt')
    stored = repo('A').load_document(key)
    assert len(stored.located_chunks) > 1
    assert repo('A').delete_document(key)
    with engine.connect() as c:
        assert all(c.execute(text('select count(*) from '+t)).scalar_one() == 0
            for t in ('rag_documents','rag_located_chunks','rag_chunk_embeddings'))
