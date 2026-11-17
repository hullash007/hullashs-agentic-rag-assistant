"""Explicit local disposable PostgreSQL integration, never selects a live URL."""
import os,re,sys,time
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import create_engine,text
from sqlalchemy.engine import URL
from sqlalchemy.exc import NoResultFound
from starlette.testclient import TestClient
from backend.ingestion.google_auth import GoogleDemoGate
from backend.ingestion.tenant_dispatch import TenantDispatcher
from backend.ingestion.postgres_repository import PostgresDocumentRepository
from backend.ingestion.ingestion_service import BoundedParser,IngestionService
from backend.ingestion.local_startup import SyntheticLocalProvider

SOCKET=os.environ.get('RAG_TENANT_TEST_SOCKET')
pytestmark=pytest.mark.skipif(not SOCKET,reason='explicit disposable local PostgreSQL socket required')
PROFILE='synthetic-hosted-demo-v1:dimension3';CID='123456-test.apps.googleusercontent.com';ORIGIN='https://demo.example'

def test_real_two_user_postgres_isolation():
    assert SOCKET.startswith('/downloads/') and os.path.isdir(SOCKET)
    engine=create_engine(URL.create('postgresql+psycopg',database='rag_tenant_test',query={'host':SOCKET,'port':'55439'}),pool_size=2,max_overflow=0)
    parser=BoundedParser(pdf_python=sys.executable,office_python=sys.executable)
    def repo(sub=None):return PostgresDocumentRepository(engine,dimension=3,embedding_profile=PROFILE,tenant_subject=sub)
    def service(r):return IngestionService(parser=parser,provider=SyntheticLocalProvider(),repository=r)
    base=repo();base.create_schema()
    with engine.begin() as conn:
        for table in ('rag_chunk_embeddings','rag_located_chunks','rag_documents'):conn.execute(text('DELETE FROM '+table))
    legacy=service(base).ingest_document(b'LEGACY_SHOULD_NEVER_APPEAR',filename='legacy.txt',content_type='text/plain')
    identities={}
    def verify(token,clientid):return identities[token]
    gate=GoogleDemoGate(TenantDispatcher(engine=engine,parser=parser),client_id=CID,allowed_emails=[],allowed_origin=ORIGIN,audience='any_google',verifier=verify)
    a=TestClient(gate,base_url=ORIGIN);b=TestClient(gate,base_url=ORIGIN)
    def login(client,sub):
        r=client.get('/');nonce=re.search("nonce:'([^']+)'",r.text).group(1)
        token=sub*30;identities[token]={'sub':sub,'email':'same@example.org','email_verified':True,'aud':CID,'iss':'https://accounts.google.com','exp':time.time()+3600,'nonce':nonce}
        assert client.post('/auth/login',headers={'Origin':ORIGIN},json={'nonce':nonce,'credential':token}).status_code==200
        return {'Origin':ORIGIN,'X-RAG-CSRF':client.get('/auth/status').json()['csrf']}
    ha=login(a,'subject-A');hb=login(b,'subject-B')
    def query(client,headers):
        r=client.post('/query',headers=headers,json={'query':'anything','top_k':10});assert r.status_code==200,r.text
        return r.json()['evidence']['entries']
    def upload(client,headers,raw,filename):
        return client.post('/documents',headers={**headers,'Content-Type':'text/plain','X-Filename':filename},content=raw)
    assert not query(a,ha) and not query(b,hb)
    ra=upload(a,ha,b'ONLY_USER_A_ALPHA','a.txt');assert ra.status_code==201,ra.text
    assert not query(b,hb)
    rb=upload(b,hb,b'ONLY_USER_B_BETA','b.txt');assert rb.status_code==201,rb.text
    assert [e['text'] for e in query(a,ha)]==['ONLY_USER_A_ALPHA']
    assert [e['text'] for e in query(b,hb)]==['ONLY_USER_B_BETA']
    same=b'Same bytes must be independently owned.'
    xa=upload(a,ha,same,'same.txt');xb=upload(b,hb,same,'same.txt')
    assert xa.status_code==xb.status_code==201
    assert xa.json()['document_id']!=xb.json()['document_id']
    assert upload(a,ha,same,'same.txt').status_code==200
    assert upload(b,hb,same,'same.txt').status_code==200
    # Client headers cannot choose a principal. JSON unknown tenant fields rejected.
    spoof=upload(a,{**ha,'X-Google-Sub':'subject-B','X-Tenant-ID':'subject-B'},b'A_SPOOF_IS_STILL_A','spoof.txt')
    assert spoof.status_code==201 and not any('SPOOF' in e['text'] for e in query(b,hb))
    assert a.post('/query',headers=ha,json={'query':'x','tenant_id':'subject-B'}).status_code==422
    ar=repo('subject-A');br=repo('subject-B')
    for wrong in [rb.json()['document_id'],legacy['document_id']]:
        with pytest.raises(NoResultFound):ar.load_document(wrong)
    bstored=br.load_document(rb.json()['document_id'])
    with pytest.raises(ValueError):ar.find_document(bstored.document.source.source_id)
    with pytest.raises(ValueError):ar.store_document(bstored.document,bstored.original_bytes,bstored.located_chunks,bstored.vectors,extraction_profile=bstored.extraction_profile,embedding_profile=PROFILE)
    # Reverse boundary: retained Basic/legacy mode cannot read or copy Google records.
    with pytest.raises(NoResultFound):base.load_document(rb.json()['document_id'])
    with pytest.raises(ValueError):base.find_document(bstored.document.source.source_id)
    with pytest.raises(ValueError):base.store_document(bstored.document,bstored.original_bytes,bstored.located_chunks,bstored.vectors,extraction_profile=bstored.extraction_profile,embedding_profile=PROFILE)
    assert {h.located_chunk.chunk.text for h in base.retrieve([1.,0.,0.],top_k=10)}=={'LEGACY_SHOULD_NEVER_APPEAR'}
    from backend.ingestion.demo_auth import PrivateDemoGate
    from backend.ingestion.upload_app import create_upload_app
    from backend.ingestion.persisted_query import PersistedQueryService
    basic=TestClient(PrivateDemoGate(create_upload_app(service=service(base),query_service=PersistedQueryService(repository=base,query_provider=SyntheticLocalProvider())),username='legacy-review',password='local-review-password-12345678901234567890',allowed_origin=ORIGIN),base_url=ORIGIN)
    basic_result=basic.post('/query',auth=('legacy-review','local-review-password-12345678901234567890'),headers={'Origin':ORIGIN},json={'query':'anything','top_k':10})
    assert basic_result.status_code==200,basic_result.text
    assert [e['text'] for e in basic_result.json()['evidence']['entries']]==['LEGACY_SHOULD_NEVER_APPEAR']
    # Concurrent independent scoped repositories never depend on global mutable identity.
    def work(sub,word):
        r=repo(sub);s=service(r)
        out=s.ingest_document(word.encode(),filename='parallel.txt',content_type='text/plain')
        hits=r.retrieve([1.,0.,0.],top_k=10)
        return out,{h.located_chunk.chunk.text for h in hits}
    with ThreadPoolExecutor(max_workers=2) as pool:
        fa=pool.submit(work,'subject-A','A_PARALLEL');fb=pool.submit(work,'subject-B','B_PARALLEL')
        va=fa.result();vb=fb.result()
    assert 'B_PARALLEL' not in va[1] and 'A_PARALLEL' not in vb[1]
    assert all('LEGACY' not in e['text'] for e in query(a,ha)+query(b,hb))
    with engine.begin() as conn:
        counts={t:conn.execute(text('SELECT count(*) FROM '+t)).scalar_one() for t in ('rag_documents','rag_located_chunks','rag_chunk_embeddings')}
        assert counts['rag_documents']==8
        conn.execute(text('DELETE FROM rag_documents'))
        assert all(conn.execute(text('SELECT count(*) FROM '+t)).scalar_one()==0 for t in counts)
    engine.dispose()

def test_real_postgres_scoped_quotas_and_dedup():
    from backend.ingestion.postgres_repository import DocumentQuota
    engine=create_engine(URL.create('postgresql+psycopg',database='rag_tenant_test',query={'host':SOCKET,'port':'55439'}))
    repo=PostgresDocumentRepository(engine,dimension=3,embedding_profile=PROFILE,tenant_subject='quota-test')
    parser=BoundedParser(pdf_python=sys.executable,office_python=sys.executable)
    service=IngestionService(parser=parser,provider=SyntheticLocalProvider(),repository=repo)
    with engine.begin() as conn:conn.execute(text('DELETE FROM rag_documents'))
    try:
        for i in range(20):service.ingest_document(('sample '+str(i)).encode(),filename=str(i)+'.txt',content_type='text/plain')
        assert service.ingest_document(b'sample 0',filename='0.txt',content_type='text/plain')['status']=='already_present'
        with pytest.raises(DocumentQuota):service.ingest_document(b'one too many',filename='21.txt',content_type='text/plain')
        with engine.begin() as conn:
            assert conn.execute(text('SELECT count(*) FROM rag_documents')).scalar_one()==20
            conn.execute(text('DELETE FROM rag_documents'))
        seed=service.ingest_document(b'quota seed',filename='seed.txt',content_type='text/plain')
        # Local-only quota fixture models retained bytes, never runs against a remote URL.
        with engine.begin() as conn:conn.execute(text('UPDATE rag_documents SET original_bytes=decode(repeat(\'61\',5242880),\'hex\') WHERE document_id=:id'),{'id':seed['document_id']})
        with pytest.raises(DocumentQuota):service.ingest_document(b'more',filename='more.txt',content_type='text/plain')
        other=PostgresDocumentRepository(engine,dimension=3,embedding_profile=PROFILE,tenant_subject='other-quota-test')
        other_service=IngestionService(parser=parser,provider=SyntheticLocalProvider(),repository=other)
        with engine.begin() as conn:conn.execute(text('UPDATE rag_documents SET original_bytes=decode(repeat(\'61\',26214400),\'hex\') WHERE document_id=:id'),{'id':seed['document_id']})
        with pytest.raises(DocumentQuota):other_service.ingest_document(b'more',filename='more.txt',content_type='text/plain')
    finally:
        with engine.begin() as conn:conn.execute(text('DELETE FROM rag_documents'))
        engine.dispose()
