"""Offline artifact smoke. No real key/DB, no public bind. Not hosting proof."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DEFAULTS = {'app': '/opt/venvs/app/bin/python', 'pdf': '/opt/venvs/pdf/bin/python',
            'office': '/opt/venvs/office/bin/python'}
# Overrides are only for source smoke, never evidence about the image.
PY = {k: os.environ.get('SMOKE_' + k.upper() + '_PYTHON', v) for k, v in DEFAULTS.items()}
assert os.path.abspath(sys.executable) == PY['app'], 'run with the explicit app interpreter'


def run(which, code, *args):
    return subprocess.check_output([PY[which], '-c', code, *map(str, args)], cwd=ROOT,
                                   env={'PATH': '/usr/local/bin:/usr/bin:/bin',
                                        'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1'},
                                   timeout=30, text=True).strip()


SMOKE_STARTED = time.monotonic()


def phase(name, **details):
    print(json.dumps({'phase': name, 'elapsed_seconds': round(time.monotonic()-SMOKE_STARTED, 3), **details}), flush=True)


phase('environment_checks_started')
expected = {'app': '3.12.15', 'pdf': '3.10.12', 'office': '3.12.15'}
for which in PY:
    assert Path(PY[which]).is_absolute() and Path(PY[which]).is_file()
    assert run(which, 'import platform;print(platform.python_version())') == expected[which]
    check_command = [PY[which], '-m', 'pip', 'check']
    if os.environ.get('SMOKE_SOURCE_UV'):
        assert PY != DEFAULTS, 'uv override is source-only'
        check_command = [os.environ['SMOKE_SOURCE_UV'], 'pip', 'check', '--python', PY[which]]
    assert subprocess.run(check_command, timeout=30, check=True).returncode == 0
assert run('app', 'import importlib.util as u;assert all(u.find_spec(x) is None for x in ("pypdf","docx","openpyxl"));print("isolated")') == 'isolated'
assert run('pdf', 'import importlib.metadata as m;assert m.version("pypdf")=="7.1.0";print("pdf")') == 'pdf'
assert run('office', 'import importlib.metadata as m;assert m.version("python-docx")=="1.2.0" and m.version("openpyxl")=="3.1.5" and m.version("lxml")=="6.1.3";print("office")') == 'office'

phase('environment_checks_passed', versions=expected)
# The default artifact smoke must inspect packaged assets, not just source imports.
from backend.ingestion.google_auth import GoogleDemoGate
from backend.ingestion.tenant_dispatch import TenantDispatcher
from backend.ingestion.document_management import DocumentManagementService
for name in ('google_auth.py','tenant_dispatch.py','document_management.py','login_ui.html','hosted_ui.html','privacy.html'):
    assert (ROOT/'backend'/'ingestion'/name).is_file()
phase('google_packaged_modules_and_assets_passed', image_default_paths=PY==DEFAULTS)
from backend.ingestion.contracts import SourceDocument
from backend.ingestion.ingestion_service import BoundedParser
parser = BoundedParser(pdf_python=PY['pdf'], office_python=PY['office'])
with tempfile.TemporaryDirectory(prefix='artifact-smoke-') as folder:
    path = Path(folder)
    run('pdf', 'from pypdf import PdfWriter;import sys;w=PdfWriter();w.add_blank_page(width=200,height=200);w.write(sys.argv[1])', path/'fixture.pdf')
    run('office', 'from docx import Document;import sys;d=Document();d.add_paragraph("Packaging smoke paragraph");d.save(sys.argv[1]);from openpyxl import Workbook;w=Workbook();w.active["A1"]="Packaging smoke cell";w.save(sys.argv[2])', path/'fixture.docx', path/'fixture.xlsx')
    for suffix, mime, locator in [
        ('pdf','application/pdf','page'),
        ('docx','application/vnd.openxmlformats-officedocument.wordprocessingml.document','paragraph'),
        ('xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','sheet')]:
        phase('parser_started', format=suffix)
        raw = (path/('fixture.'+suffix)).read_bytes()
        source = SourceDocument('smoke:'+suffix, 'fixture.'+suffix, mime, hashlib.sha256(raw).hexdigest())
        result = parser.parse(raw, source)
        assert result.format == suffix and len(result.segments) == 1
        assert result.segments[0].locator.kind == locator
        assert parser.executions[-1]['reaped'] and parser.executions[-1]['exit_code'] == 0
        phase('parser_passed', format=suffix, reaped=True, exit_code=0)

# Health and unauthorized requests must never touch an external service.
# Child monkeypatches are tripwires, not alternative implementations of the app.
server_code = r'''
import os,socket
import sqlalchemy
import warnings
warnings.simplefilter('ignore', SyntaxWarning)  # SDK 3.3.0 docstring escapes only
from google import genai
class NoKeys(dict):
 def __getitem__(self,k):
  if any(x in k for x in ('API_KEY','TOKEN','SECRET')):raise AssertionError('key read')
  return super().__getitem__(k)
 def get(self,k,d=None):
  if any(x in k for x in ('API_KEY','TOKEN','SECRET')):raise AssertionError('key read')
  return super().get(k,d)
def forbidden(*a,**k):raise AssertionError('external DB/model touched')
sqlalchemy.engine.Engine.connect=forbidden
genai.Client=forbidden
from backend.ingestion.hosted_demo import make_hosted_demo
import uvicorn
settings=NoKeys(DEMO_USERNAME='smoke',DEMO_PASSWORD='offline-smoke-not-a-usable-secret-000000',DEMO_ORIGIN='https://demo.invalid',DATABASE_URL='postgresql+psycopg://smoke:smoke@127.0.0.1:1/smoke?sslmode=verify-full&sslrootcert=system',RAG_PDF_PYTHON=os.environ['RAG_PDF_PYTHON'],RAG_OFFICE_PYTHON=os.environ['RAG_OFFICE_PYTHON'],ANSWER_GENERATION_ENABLED='false')
uvicorn.run(make_hosted_demo(settings),host='127.0.0.1',port=int(os.environ['SMOKE_PORT']),workers=1,access_log=False,log_level='warning')
'''
# Reserve an ephemeral loopback port; readiness handles the small release/bind race.
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
env = {'PATH':'/usr/local/bin:/usr/bin:/bin','PYTHONNOUSERSITE':'1',
       'PYTHONDONTWRITEBYTECODE':'1','RAG_PDF_PYTHON':PY['pdf'],
       'RAG_OFFICE_PYTHON':PY['office'],'SMOKE_PORT':str(port)}
with tempfile.TemporaryFile(mode='w+b') as logs:
    phase('server_child_launch_started', target_host='127.0.0.1', target_port=port)
    process = subprocess.Popen([PY['app'], '-c', server_code], cwd=ROOT, env=env,
                               stdout=logs, stderr=logs, start_new_session=True)
    phase('server_child_launched')
    def request(method, route):
        conn = http.client.HTTPConnection('127.0.0.1',port,timeout=1)
        try:
            conn.request(method,route); response=conn.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:conn.close()
    failure = None
    cleanup_failure = None
    returncode_before_cleanup = None
    started = time.monotonic()
    phase('health_startup_wait', budget_seconds=120)
    try:
        deadline=started+120
        while True:
            if process.poll() is not None:raise AssertionError('smoke server exited')
            try:
                status, body, headers=request('GET','/healthz')
                assert status==200 and json.loads(body)=={'status':'ok'}
                phase('health_passed', status=200, wait_elapsed_seconds=round(time.monotonic()-started, 3))
                break
            except (ConnectionError,TimeoutError):
                if time.monotonic()>deadline:raise
                time.sleep(.05)
        for method,route in [('GET','/'),('GET','/capabilities'),('POST','/upload'),('POST','/query'),('POST','/answer')]:
            status,body,headers=request(method,route)
            assert status==401 and json.loads(body)=={'error':'authentication_required'}
            assert headers.get('cache-control')=='no-store'
    except BaseException as exc:
        failure = exc
    finally:
        import signal
        returncode_before_cleanup = process.poll()
        try:
            if returncode_before_cleanup is None:
                try: os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError: pass
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                process.wait(timeout=5)
        except BaseException as exc:
            cleanup_failure = exc
        try:
            # Bound emitted diagnostics to 64KiB. Tempfile storage is not a disk quota.
            logs.seek(0, 2); log_bytes = logs.tell(); logs.seek(0)
            log_text = logs.read(65536).decode(errors='replace')
        except BaseException as exc:
            cleanup_failure = cleanup_failure or exc
            log_bytes = 0; log_text = ''
        if failure is not None or cleanup_failure is not None:
            # This child has only fixed synthetic settings, no external credentials.
            phase('health_failure_diagnostics', wait_elapsed_seconds=round(time.monotonic()-started, 3),
                  original_error_type=type(failure).__name__ if failure is not None else None,
                  connection_errno=getattr(failure, 'errno', None),
                  cleanup_error_type=type(cleanup_failure).__name__ if cleanup_failure is not None else None,
                  returncode_before_cleanup=returncode_before_cleanup,
                  returncode_after_cleanup=process.returncode, child_log=log_text,
                  child_log_bytes=log_bytes, child_log_truncated=log_bytes>65536)
    if failure is not None: raise failure.with_traceback(failure.__traceback__)
    if cleanup_failure is not None: raise cleanup_failure.with_traceback(cleanup_failure.__traceback__)
    assert process.returncode in (0, -15) and not log_text.strip(), ('smoke server error', process.returncode, log_text)
with socket.socket() as sock:
    sock.settimeout(1); assert sock.connect_ex(('127.0.0.1',port))!=0, 'listener remains'
print(json.dumps({'scope':'local artifact smoke','image_default_paths':PY==DEFAULTS,
                  'versions':expected,'parser_children':parser.executions,
                  'health':200,'unauthorized_routes':5,'server_reaped':True,
                  'listener_closed':True,'no_live_db_or_model':True}))
