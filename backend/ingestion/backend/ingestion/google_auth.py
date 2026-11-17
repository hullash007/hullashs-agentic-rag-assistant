"""Single-process, allowlisted GIS sign-in. No Google API authorization or stored tokens.
Sessions and one-use login nonces live only in bounded process memory. Restart logs out.
"""
import asyncio
import hmac
import hashlib
import base64
import json
import re
import secrets
import threading
import time
from pathlib import Path
from starlette.responses import JSONResponse, HTMLResponse
from starlette.concurrency import run_in_threadpool

COOKIE='__Host-rag_session'
LOGIN_COOKIE='__Host-rag_login'
ROOT=Path(__file__).parent


def html_response(html):
    def hashes(tag):
        return ' '.join("'sha256-"+base64.b64encode(hashlib.sha256(x.encode()).digest()).decode()+"'" for x in re.findall(r'<'+tag+r'>(.*?)</'+tag+r'>',html,re.S))
    policy="default-src 'none'; base-uri 'none'; object-src 'none'; form-action 'self'; frame-ancestors 'none'; script-src "+hashes('script')+" https://accounts.google.com/gsi/client; style-src "+hashes('style')+" https://accounts.google.com/gsi/style; connect-src 'self' https://accounts.google.com/gsi/; frame-src https://accounts.google.com/gsi/; img-src 'self' data:;"
    return HTMLResponse(html,headers={'Content-Security-Policy':policy})


def verify_google_token(token,client_id):
    from google.oauth2.id_token import verify_oauth2_token
    from google.auth.transport.requests import Request
    import requests
    class TimedRequest(Request):
        def __call__(self,*args,**kwargs):
            kwargs['timeout']=5
            return super().__call__(*args,**kwargs)
    # Do not log the credential or include it in an exception response.
    with requests.Session() as session:
        return verify_oauth2_token(token,TimedRequest(session=session),client_id)


class GoogleDemoGate:
    def __init__(self,app,*,client_id,allowed_emails,allowed_origin,audience='allowlist',operations_enabled=True,verifier=verify_google_token,clock=time.monotonic):
        from urllib.parse import urlsplit
        p=urlsplit(allowed_origin)
        if p.scheme!='https' or not p.hostname or p.path or p.query or p.fragment or p.username or p.password:
            raise ValueError('explicit HTTPS origin required')
        if not re.fullmatch(r'[0-9]+-[A-Za-z0-9_-]+\.apps\.googleusercontent\.com',client_id):
            raise ValueError('explicit Google web client ID required')
        emails=frozenset(x.strip().lower() for x in allowed_emails)
        # Only Gmail identities have independently authoritative email ownership here.
        # Workspace/custom domains require an explicitly reviewed domain policy, not guessing.
        if audience not in ('allowlist','any_google'):raise ValueError('explicit audience required')
        if audience=='allowlist' and (not emails or any(not re.fullmatch(r'[a-z0-9._%+-]+@gmail\.com',x) for x in emails)):
            raise ValueError('explicit Gmail account allowlist required')
        if type(operations_enabled) is not bool:raise ValueError('explicit operation state required')
        self.operations_enabled=operations_enabled
        self.audience=audience
        self.app=app;self.client_id=client_id;self.emails=emails;self.origin=allowed_origin
        self.verify=verifier;self.clock=clock;self.sessions={};self.nonces={}
        self.window=clock();self.count=0;self.operations=0;self.operation=threading.Lock();self.auth_operation=asyncio.Semaphore(2)

    def cookie(self,scope,name):
        raw=[v for k,v in scope.get('headers',[]) if k.lower()==b'cookie']
        if len(raw)!=1 or len(raw[0])>8192:return None
        try:
            text=raw[0].decode('ascii')
            # Parse only our generated opaque cookie. Third-party GIS g_state may
            # contain JSON that makes SimpleCookie discard the entire cookie jar.
            matches=[x.strip().split('=',1)[1] for x in text.split(';') if x.strip().startswith(name+'=')]
            if len(matches)!=1 or not re.fullmatch(r'[A-Za-z0-9_-]{43}',matches[0]):return None
            return matches[0]
        except (UnicodeError,ValueError):return None

    async def body(self,receive):
        data=bytearray()
        async with asyncio.timeout(10):
            while True:
                msg=await receive()
                if msg['type']!='http.request':raise ValueError()
                data.extend(msg.get('body',b''))
                if len(data)>12000:raise ValueError()
                if not msg.get('more_body'):break
        obj=json.loads(data)
        if type(obj) is not dict:raise ValueError()
        return obj

    async def __call__(self,scope,receive,send):
        if scope['type']=='lifespan':return await self.app(scope,receive,send)
        if scope['type']!='http':return await send({'type':'websocket.close','code':1008})
        original_send=send
        async def secure_send(msg):
            if msg['type']=='http.response.start':
                msg=dict(msg)
                keys=(b'cache-control',b'x-content-type-options',b'x-frame-options',b'referrer-policy')
                msg['headers']=[(k,v) for k,v in msg.get('headers',[]) if k.lower() not in keys]+[
                    (b'cache-control',b'no-store'),(b'x-content-type-options',b'nosniff'),
                    (b'x-frame-options',b'DENY'),(b'referrer-policy',b'strict-origin-when-cross-origin'),
                    (b'cross-origin-opener-policy',b'same-origin-allow-popups')]
            return await original_send(msg)
        send=secure_send
        async def reply(value,status=200):return await JSONResponse(value,status_code=status)(scope,receive,send)
        path=scope['path'];method=scope['method'];headers=scope.get('headers',[])
        if path=='/healthz' and method=='GET':return await reply({'status':'ok'})
        now=self.clock()
        self.sessions={k:v for k,v in self.sessions.items() if v['expires']>now}
        self.nonces={k:v for k,v in self.nonces.items() if v>now}
        if now-self.window>=60:self.window=now;self.count=0;self.operations=0
        self.count+=1
        if self.count>120:return await reply({'error':'demo_rate_limit'},429)
        if method not in ('GET','HEAD'):
            origins=[v for k,v in headers if k.lower()==b'origin']
            if origins!=[self.origin.encode()]:return await reply({'error':'origin_rejected'},403)
        if path=='/privacy' and method=='GET':
            return await html_response((ROOT/'privacy.html').read_text())(scope,receive,send)
        sid=self.cookie(scope,COOKIE);session=self.sessions.get(sid)
        if path=='/' and method=='GET':
            if session:
                return await html_response((ROOT/'hosted_ui.html').read_text())(scope,receive,send)
            if len(self.nonces)>=200:return await reply({'error':'demo_busy'},503)
            nonce=secrets.token_urlsafe(32);self.nonces[nonce]=now+300
            html=(ROOT/'login_ui.html').read_text().replace('__CLIENT_ID__',self.client_id).replace('__NONCE__',nonce)
            resp=html_response(html)
            resp.set_cookie(LOGIN_COOKIE,nonce,max_age=300,httponly=True,secure=True,samesite='strict',path='/')
            return await resp(scope,receive,send)
        if path=='/auth/login' and method=='POST':
            try:
                value=await self.body(receive)
                nonce=value.get('nonce');token=value.get('credential')
                cookie=self.cookie(scope,LOGIN_COOKIE)
                if type(nonce) is not str or type(cookie) is not str or not hmac.compare_digest(nonce,cookie) or self.nonces.pop(nonce,0)<=now:
                    return await reply({'error':'login_expired'},403)
                if type(token) is not str or not 20<len(token)<10000:return await reply({'error':'sign_in_failed'},401)
                async with self.auth_operation:
                    claims=await run_in_threadpool(self.verify,token,self.client_id)
                # Explicit checks supplement the official library, never trust decoded-only JWTs.
                email=claims.get('email','').lower()
                if claims.get('aud')!=self.client_id or claims.get('iss') not in ('accounts.google.com','https://accounts.google.com') or claims.get('email_verified') is not True or (self.audience=='allowlist' and email not in self.emails) or claims.get('nonce')!=nonce or type(claims.get('sub')) is not str or not 1<=len(claims['sub'])<=255 or type(claims.get('exp')) not in (int,float) or claims['exp']<=time.time():
                    return await reply({'error':'account_not_allowed'},403)
                if len(self.sessions)>=100:return await reply({'error':'demo_busy'},503)
                if sid:self.sessions.pop(sid,None)
                new_id=secrets.token_urlsafe(32)
                self.sessions[new_id]={'sub':claims['sub'],'email':email,'csrf':secrets.token_urlsafe(32),'expires':self.clock()+min(3600,claims['exp']-time.time())}
                resp=JSONResponse({'status':'signed_in'})
                resp.set_cookie(COOKIE,new_id,max_age=3600,httponly=True,secure=True,samesite='strict',path='/')
                resp.delete_cookie(LOGIN_COOKIE,path='/',secure=True,httponly=True,samesite='strict')
                return await resp(scope,receive,send)
            except Exception:
                return await reply({'error':'sign_in_failed'},401)
        if not session:return await reply({'error':'authentication_required'},401)
        if path=='/auth/status' and method=='GET':
            return await reply({'email':session['email'],'csrf':session['csrf'],'expires_in':max(0,int(session['expires']-now)),'operations_enabled':self.operations_enabled})
        if method not in ('GET','HEAD'):
            csrf=[v for k,v in headers if k.lower()==b'x-rag-csrf']
            if len(csrf)!=1 or not hmac.compare_digest(csrf[0],session['csrf'].encode()):return await reply({'error':'csrf_rejected'},403)
        if path=='/auth/logout' and method=='POST':
            self.sessions.pop(sid,None)
            resp=JSONResponse({'status':'signed_out'})
            resp.delete_cookie(COOKIE,path='/',secure=True,httponly=True,samesite='strict')
            return await resp(scope,receive,send)
        if not self.operations_enabled and path!='/capabilities':return await reply({'error':'data_operations_not_enabled'},503)
        if path.startswith('/auth/'):return await reply({'error':'not_found'},404)
        acquired=False
        self.operations+=1
        if self.operations>30:return await reply({'error':'demo_rate_limit'},429)
        if method not in ('GET','HEAD'):
            acquired=self.operation.acquire(blocking=False)
            if not acquired:return await reply({'error':'demo_busy'},503)
        scope=dict(scope)
        scope['rag.google_sub']=session['sub']
        try:return await self.app(scope,receive,send)
        finally:
            if acquired:self.operation.release()
