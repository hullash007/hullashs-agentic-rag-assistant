import json,re,time
import pytest
from starlette.responses import JSONResponse
from starlette.testclient import TestClient
from backend.ingestion.google_auth import GoogleDemoGate,COOKIE,LOGIN_COOKIE
CID='123456-test.apps.googleusercontent.com';ORIGIN='https://demo.example'
async def downstream(scope,receive,send):
    await JSONResponse({'protected':True})(scope,receive,send)
def setup(**options):
    claims={'sub':'google-sub-123','email':'owner@gmail.com','email_verified':True,'aud':CID,'iss':'https://accounts.google.com','exp':time.time()+3600}
    def verify(token,client_id):
        assert token=='g'*40 and client_id==CID
        return claims
    gate=GoogleDemoGate(downstream,client_id=CID,allowed_emails=['owner@gmail.com'],allowed_origin=ORIGIN,verifier=options.pop('verifier',verify),**options)
    return TestClient(gate,base_url=ORIGIN),gate,claims

def login(c,claims):
    r=c.get('/');assert r.status_code==200
    nonce=re.search("nonce:'([^']+)'",r.text).group(1);claims['nonce']=nonce
    return c.post('/auth/login',headers={'Origin':ORIGIN},json={'nonce':nonce,'credential':'g'*40})

def test_fail_closed_configuration():
    for emails in [[],['owner@example.com'],['*@gmail.com']]:
        with pytest.raises(ValueError):GoogleDemoGate(downstream,client_id=CID,allowed_emails=emails,allowed_origin=ORIGIN)
    with pytest.raises(ValueError):GoogleDemoGate(downstream,client_id='',allowed_emails=['owner@gmail.com'],allowed_origin=ORIGIN)

def test_public_login_only_and_basic_rejected():
    c,_,_=setup()
    for method,path in [('GET','/capabilities'),('POST','/documents'),('POST','/query'),('POST','/answer'),('GET','/auth/status')]:
        r=c.request(method,path,headers={'Origin':ORIGIN,'Authorization':'Basic dXNlcjpwYXNzd29yZA=='})
        assert r.status_code==401 and 'www-authenticate' not in r.headers
        assert r.headers['cache-control']=='no-store'
    r=c.get('/');assert 'Sign in' in r.text and 'Store document' not in r.text
    assert 'HttpOnly' in r.headers['set-cookie'] and 'Secure' in r.headers['set-cookie'] and 'SameSite=strict' in r.headers['set-cookie']
    assert "object-src 'none'" in r.headers['content-security-policy']
    assert c.get('/healthz').json()=={'status':'ok'}
    assert c.get('/privacy').status_code==200

def test_login_session_csrf_logout_and_replay():
    c,gate,claims=setup();r=login(c,claims);assert r.status_code==200
    sid=c.cookies.get(COOKIE);assert sid and claims['sub'] in [v['sub'] for v in gate.sessions.values()]
    assert 'HttpOnly' in r.headers['set-cookie'];assert 'Store document' in c.get('/').text
    status=c.get('/auth/status').json();csrf=status['csrf'];assert status['email']=='owner@gmail.com'
    assert c.post('/query',headers={'Origin':ORIGIN}).status_code==403
    assert c.post('/query',headers={'Origin':ORIGIN,'X-RAG-CSRF':csrf}).status_code==200
    for headers in [{},{'Origin':'null'},{'Origin':'https://foreign.invalid'},[('Origin',ORIGIN),('Origin',ORIGIN)]]:
        assert c.post('/query',headers=headers).status_code==403
    c.cookies.set(LOGIN_COOKIE,claims['nonce'])
    assert c.post('/auth/login',headers={'Origin':ORIGIN},json={'nonce':claims['nonce'],'credential':'g'*40}).status_code==403
    assert c.post('/auth/logout',headers={'Origin':ORIGIN,'X-RAG-CSRF':csrf}).status_code==200
    assert not gate.sessions
    c.cookies.set(COOKIE,sid);assert c.get('/capabilities').status_code==401

@pytest.mark.parametrize('field,bad',[('aud','wrong'),('iss','https://evil.invalid'),('email','stranger@gmail.com'),('email_verified',False),('nonce','wrong'),('sub',''),('exp',0)])
def test_invalid_identity_denied(field,bad):
    c,gate,claims=setup()
    r=c.get('/');nonce=re.search("nonce:'([^']+)'",r.text).group(1);claims['nonce']=nonce;claims[field]=bad
    assert c.post('/auth/login',headers={'Origin':ORIGIN},json={'nonce':nonce,'credential':'g'*40}).status_code==403
    assert not gate.sessions

def test_invalid_signature_network_failure_denied():
    def bad(*args):raise ValueError('do not expose credential')
    c,gate,claims=setup(verifier=bad)
    r=login(c,claims);assert r.status_code==401 and 'credential' not in r.text and not gate.sessions

def test_nonce_cookie_missing_mismatch_and_bounded_body():
    c,gate,claims=setup();c.get('/')
    for value in [{'nonce':'x','credential':'g'*40},[],{'credential':'g'*40}]:
        assert c.post('/auth/login',headers={'Origin':ORIGIN},json=value).status_code in (401,403)
    assert c.post('/auth/login',headers={'Origin':ORIGIN},content=b'a'*13000).status_code==401
    assert not gate.sessions

def test_session_expiry_and_restart():
    now=[0.0];c,gate,claims=setup(clock=lambda:now[0]);assert login(c,claims).status_code==200
    now[0]=3601;assert c.get('/capabilities').status_code==401
    c2,gate2,claims2=setup();assert not gate2.sessions

def test_nonce_expiry():
    now=[0.0];c,gate,claims=setup(clock=lambda:now[0]);r=c.get('/');nonce=re.search("nonce:'([^']+)'",r.text).group(1)
    now[0]=301;claims['nonce']=nonce
    assert c.post('/auth/login',headers={'Origin':ORIGIN},json={'nonce':nonce,'credential':'g'*40}).status_code==403

def test_official_library_checks_real_signature_audience_and_expiry(monkeypatch):
    import datetime
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from google.auth import jwt,crypt
    from google.auth.exceptions import GoogleAuthError
    import google.auth.transport.requests
    from backend.ingestion.google_auth import verify_google_token
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Ephemeral test public cert')])
    now=datetime.datetime.now(datetime.timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(1).not_valid_before(now-datetime.timedelta(minutes=1)).not_valid_after(now+datetime.timedelta(hours=1)).sign(key,hashes.SHA256())).public_bytes(serialization.Encoding.PEM).decode()
    class Response:
        status=200;headers={};data=json.dumps({'test-key':cert}).encode()
    class Request:
        def __init__(self,**kwargs):pass
        def __call__(self,*args,**kwargs):return Response()
    monkeypatch.setattr(google.auth.transport.requests,'Request',Request)
    pem=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
    signer=crypt.RSASigner.from_string(pem,key_id='test-key')
    claims={'sub':'verified-sub','aud':CID,'iss':'https://accounts.google.com','iat':int(time.time())-1,'exp':int(time.time())+300,'nonce':'n','email':'user@example.org','email_verified':True}
    token=jwt.encode(signer,claims).decode()
    assert verify_google_token(token,CID)['sub']=='verified-sub'
    for payload in [{**claims,'aud':'wrong'},{**claims,'iss':'https://evil.invalid'},{**claims,'exp':int(time.time())-100}]:
        with pytest.raises((ValueError,GoogleAuthError)):verify_google_token(jwt.encode(signer,payload).decode(),CID)
    pieces=token.split('.');pieces[2]=('a' if pieces[2][0]!='a' else 'b')+pieces[2][1:]
    with pytest.raises(ValueError):verify_google_token('.'.join(pieces),CID)

def test_google_state_cookie_does_not_break_opaque_session():
    c,gate,claims=setup();assert login(c,claims).status_code==200
    sid=c.cookies.get(COOKIE)
    r=c.get('/capabilities',headers={'Cookie':COOKIE+'='+sid+'; g_state={"i_l":0}'})
    assert r.status_code==200
    assert c.get('/capabilities',headers={'Cookie':COOKIE+'='+sid+'; '+COOKIE+'='+sid}).status_code==401

def test_staged_sign_in_has_no_data_operations():
    c,gate,claims=setup(operations_enabled=False);assert login(c,claims).status_code==200
    status=c.get('/auth/status').json();assert status['operations_enabled'] is False
    for path in ['/documents','/query','/answer']:
        assert c.post(path,headers={'Origin':ORIGIN,'X-RAG-CSRF':status['csrf']}).status_code==503
    assert c.get('/capabilities').status_code==200
    assert c.post('/auth/logout',headers={'Origin':ORIGIN,'X-RAG-CSRF':status['csrf']}).status_code==200
