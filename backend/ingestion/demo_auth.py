"""Small single-process demo gate, not multi-tenant production identity management."""
import base64
import binascii
import hashlib
import hmac
import threading
import time


class PrivateDemoGate:
    def __init__(self, app, *, username, password, max_requests=30, allowed_origin=None):
        if type(username) is not str or not username or ':' in username or len(username)>100:
            raise ValueError('explicit demo username required')
        if type(password) is not str or len(password)<32 or len(password)>256:
            raise ValueError('demo password must be 32..256 characters')
        self.allowed_origin=allowed_origin
        self.app=app
        self.identity=hashlib.sha256((username+':'+password).encode()).digest()
        self.max_requests=max_requests
        self.lock=threading.Lock()
        self.operation=threading.Lock()
        self.window=time.monotonic()
        self.count=0

    async def __call__(self, scope, receive, send):
        if scope['type']=='lifespan':
            return await self.app(scope,receive,send)
        if scope['type']!='http':
            await send({'type':'websocket.close','code':1008})
            return
        original_send=send
        async def secured_send(message):
            if message['type']=='http.response.start':
                message=dict(message)
                message['headers']=[(k,v) for k,v in message.get('headers',[]) if k.lower() not in (b'cache-control',b'x-content-type-options',b'x-frame-options',b'referrer-policy')]+[
                    (b'cache-control',b'no-store'),(b'x-content-type-options',b'nosniff'),
                    (b'x-frame-options',b'DENY'),(b'referrer-policy',b'no-referrer')]
            await original_send(message)
        send=secured_send
        from starlette.responses import JSONResponse
        if scope['path']=='/healthz' and scope['method']=='GET':
            return await JSONResponse({'status':'ok'})(scope,receive,send)
        headers=scope.get('headers',[])
        auth=[v for k,v in headers if k.lower()==b'authorization']
        valid=False
        if len(auth)==1 and len(auth[0])<1024:
            try:
                prefix,value=auth[0].split(b' ',1)
                decoded=base64.b64decode(value,validate=True)
                valid=prefix.lower()==b'basic' and hmac.compare_digest(hashlib.sha256(decoded).digest(),self.identity)
            except (ValueError,binascii.Error):pass
        if not valid:
            return await JSONResponse({'error':'authentication_required'},status_code=401,
                headers={'WWW-Authenticate':'Basic realm="Private RAG demo", charset="UTF-8"','Connection':'close','Cache-Control':'no-store'})(scope,receive,send)
        if scope['method'] not in ('GET','HEAD'):
            origins=[v for k,v in headers if k.lower()==b'origin']
            expected=self.allowed_origin.encode() if self.allowed_origin else None
            if expected is None or len(origins)!=1 or origins[0]!=expected:
                return await JSONResponse({'error':'origin_rejected'},status_code=403,
                    headers={'Connection':'close'})(scope,receive,send)
        now=time.monotonic()
        with self.lock:
            if now-self.window>=60:self.window,self.count=now,0
            self.count+=1
            allowed=self.count<=self.max_requests
        if not allowed:
            return await JSONResponse({'error':'demo_rate_limit'},status_code=429,
                headers={'Retry-After':'60','Connection':'close','Cache-Control':'no-store'})(scope,receive,send)
        acquired=False
        if scope['method'] not in ('GET','HEAD'):
            acquired=self.operation.acquire(blocking=False)
            if not acquired:
                return await JSONResponse({'error':'demo_busy'},status_code=503,headers={'Connection':'close'})(scope,receive,send)
        try:
            return await self.app(scope,receive,send)
        finally:
            if acquired:self.operation.release()
