"""Isolated free-runner image qualification. No account secrets or deployment.
Only public immutable source and pinned public package/base-image inputs are used.
No registry push, Actions artifact/cache upload, hosted database or provider call.
"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'lifecycle-qualification:local'
CONTAINER = 'lifecycle-qualification-export'

def run(args, **kw):
    return subprocess.run(args, cwd=ROOT, check=True, timeout=kw.pop('timeout', 120), **kw)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

manifest = json.loads((ROOT/'packaging/lifecycle-image-source.json').read_text())
assert manifest['scope'] == 'public_source_only_isolated_build'
# Reject new tracked source before even contacting Docker. The manifest itself
# cannot include its own hash; its exact JSON is a separately reviewed delta.
tracked = set(subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')) - {''}
assert tracked == set(manifest['files']) | {'packaging/lifecycle-image-source.json'}, {
    'unlisted_tracked': sorted(tracked - set(manifest['files']) - {'packaging/lifecycle-image-source.json'}),
    'missing_tracked': sorted(set(manifest['files']) - tracked),
}
for name, sha in manifest['files'].items():
    assert digest((ROOT/name).read_bytes()) == sha, name
assert not any((ROOT/n).exists() for n in ('.env', 'credentials.json', 'service-account.json'))
print(json.dumps({'phase':'source_hashes_verified','files':len(manifest['files']),
    'commit':os.environ.get('GITHUB_SHA')}), flush=True)
run(['docker','version','--format','{{.Server.Version}}'])
try:
    run(['docker','build','--progress=plain','--platform=linux/amd64',
         '-f','packaging/Dockerfile','-t',IMAGE,'.'], timeout=1200)
    inspected = json.loads(subprocess.check_output(['docker','image','inspect',IMAGE], cwd=ROOT))[0]
    assert inspected['Config']['User'] == '65532:65532'
    assert inspected['Config']['Cmd'] == ['/opt/venvs/app/bin/python','/app/packaging/container_smoke.py']
    assert inspected['Architecture'] == 'amd64'
    print(json.dumps({'phase':'built_image','image_id':inspected['Id'],
        'architecture':inspected['Architecture'],'bytes':inspected['Size'],
        'user':inspected['Config']['User']}), flush=True)
    run(['docker','create','--name',CONTAINER,IMAGE], stdout=subprocess.DEVNULL)
    # Inspect actual exported /app content, not a guessed Dockerignore projection.
    with tempfile.TemporaryDirectory(prefix='image-audit-') as d:
        archive=Path(d)/'image.tar'
        with archive.open('wb') as out:
            run(['docker','export',CONTAINER], stdout=out)
        observed={}
        with tarfile.open(archive) as tar:
            for item in tar:
                name=item.name.removeprefix('./')
                if not item.isfile() or not name.startswith('app/'):
                    continue
                relative=name[4:]
                assert relative in manifest['image_app_files'], relative
                raw=tar.extractfile(item).read()
                assert digest(raw) == manifest['image_app_files'][relative], relative
                observed[relative]=digest(raw)
        assert observed == manifest['image_app_files']
    print(json.dumps({'phase':'actual_app_files_exact','count':len(observed),
        'manifest_sha256':digest((ROOT/'packaging/lifecycle-image-source.json').read_bytes())}), flush=True)
    # Ephemeral unprivileged process, no network or exposed ports/volumes/secrets.
    run(['docker','run','--rm','--network=none','--memory=1g','--cpus=2',
         '--pids-limit=128','--cap-drop=ALL','--security-opt=no-new-privileges',
         IMAGE], timeout=180)
    # Existing artifact smoke predates lifecycle routes. Check exact new routes
    # from this image without touching a database or using Google credentials.
    code = '''from starlette.testclient import TestClient
from backend.ingestion.upload_app import create_upload_app
from backend.ingestion.document_management import DocumentManagementService
from backend.ingestion.google_auth import GoogleDemoGate
app=create_upload_app(service=object(),document_service=object())
assert {(r.path,m) for r in app.routes for m in r.methods} >= {('/documents','GET'),('/documents/{document_id}','GET'),('/documents/{document_id}','DELETE')}
gate=GoogleDemoGate(app,client_id='123456-test.apps.googleusercontent.com',allowed_emails=['sample@gmail.com'],allowed_origin='https://sample.invalid')
c=TestClient(gate,base_url='https://sample.invalid')
for method,path in [('GET','/documents'),('GET','/documents/'+'a'*64),('DELETE','/documents/'+'a'*64)]:
 r=c.request(method,path,headers={'Origin':'https://sample.invalid'})
 assert r.status_code==401 and r.json()=={'error':'authentication_required'}
print('FINAL_IMAGE_LIFECYCLE_ROUTES_AND_UNAUTHENTICATED_GATE_OK')
'''
    run(['docker','run','--rm','--network=none','--memory=1g','--cpus=2',
         '--pids-limit=128','--cap-drop=ALL','--security-opt=no-new-privileges',
         '--entrypoint','/opt/venvs/app/bin/python',IMAGE,'-c',code], timeout=60)
    print(json.dumps({'phase':'qualification_complete','hosted_data_used':False,
        'model_calls':0,'registry_push':False,'memory_fit_512MiB_proven':False}), flush=True)
finally:
    container_cleanup=subprocess.run(['docker','rm','-f',CONTAINER], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    image_cleanup=subprocess.run(['docker','image','rm','-f',IMAGE], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(json.dumps({'phase':'ephemeral_cleanup_attempt','container_remove_status':container_cleanup.returncode,'image_remove_status':image_cleanup.returncode,'outer_cleanup':'GitHub-hosted ephemeral runner disposal'}), flush=True)
