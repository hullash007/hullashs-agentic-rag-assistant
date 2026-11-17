"""Bounded parser child entrypoint. No caller-selected code or filesystem paths."""
import resource
resource.setrlimit(resource.RLIMIT_AS, (268435456, 268435456))
resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
resource.setrlimit(resource.RLIMIT_FSIZE, (1048576, 1048576))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
import os, sys, socket, json, hashlib
for name in list(os.environ):
    if any(k in name for k in ('KEY', 'TOKEN', 'CREDENTIAL', 'TRACING', 'LANGSMITH', 'LANGCHAIN')):
        os.environ.pop(name, None)
attempts = []
def blocked(*args, **kwargs):
    attempts.append(True)
    raise RuntimeError('parser network forbidden')
for name in ('connect', 'connect_ex', 'sendto', 'sendall', 'send'):
    setattr(socket.socket, name, blocked)
for name in ('create_connection', 'getaddrinfo', 'gethostbyname'):
    setattr(socket, name, blocked)
from dataclasses import asdict
sys.path[:0] = ['/downloads/rag-offline-prep/source', '/downloads/rag-office-experiment']
from backend.ingestion.contracts import SourceDocument
metadata = json.loads(sys.argv[2])
source = SourceDocument(**metadata)
with open(sys.argv[1], 'rb') as f:
    raw = f.read(2097153)
if len(raw) > 2097152 or hashlib.sha256(raw).hexdigest() != source.sha256:
    raise ValueError('invalid original bytes')
if source.mime_type == 'application/pdf':
    from backend.ingestion.pdf_adapter import parse_pdf_experiment
    document = parse_pdf_experiment(raw, source)
elif source.mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
    from office_adapter import docx_extract
    document = docx_extract(raw, source)
elif source.mime_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
    from xlsx_inspected import extract_xlsx
    document = extract_xlsx(raw, source)
else:
    raise ValueError('unsupported binary MIME')
print(json.dumps({'document': asdict(document), 'network_attempts': len(attempts)},
                 ensure_ascii=False, allow_nan=False))
