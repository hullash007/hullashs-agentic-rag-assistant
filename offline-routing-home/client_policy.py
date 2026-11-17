"""Offline-only candidate client policy. No HTTP client, endpoint or credentials.
Uses an injected exchange(body_bytes, remaining_seconds) for fixtures only.
Not wired into the app; profile constants are review candidates, not activation.
"""
import json
import math
import time

PROFILE = 'hermes-nomic-v1.5-768-512-v1'
DIGEST = '0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f'


class Rejected(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def strict_load(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))


def encode(operation, texts):
    return json.dumps({'profile': PROFILE, 'operation': operation, 'texts': texts},
                      ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def batches(operation, texts):
    if operation not in ('query', 'documents') or type(texts) is not list or not texts:
        raise Rejected('invalid_local_input')
    if (operation == 'query' and len(texts) != 1) or len(texts) > 128:
        raise Rejected('invalid_local_input')
    result, pending = [], []
    for text in texts:
        if type(text) is not str or not text.strip():
            raise Rejected('invalid_local_text')
        try:
            size = len(text.encode('utf-8'))
        except UnicodeError:
            raise Rejected('invalid_local_text') from None
        if size > 8192:
            raise Rejected('local_text_limit')
        if '\x00' in text or any(x in text for x in ('[CLS]', '[SEP]', '[MASK]', '[PAD]', '[UNK]')):
            raise Rejected('unsupported_control_text')
        candidate = pending + [text]
        if pending and (len(candidate) > 4 or len(encode(operation, candidate)) > 16384):
            result.append(pending)
            pending = [text]
        else:
            pending = candidate
        if len(encode(operation, pending)) > 16384:
            raise Rejected('local_wire_limit')
    if pending:
        result.append(pending)
    return result


STATUS_CODES = {400: 'remote_invalid_input', 401: 'remote_unauthorized',
                409: 'remote_profile_mismatch', 413: 'remote_limit',
                429: 'remote_busy', 502: 'remote_invalid_upstream',
                503: 'remote_unavailable', 504: 'remote_timeout'}


def validate_response(raw, operation, count):
    try:
        # 4 * 768 JSON floats plus bounded metadata, below server131072pipecap.
        if type(raw) is not bytes or len(raw) > 131072:
            raise ValueError()
        data = strict_load(raw)
        if type(data) is not dict or set(data) != {'profile', 'model_digest', 'dimension', 'operation', 'input_tokens', 'embeddings'}:
            raise ValueError()
        if data['profile'] != PROFILE or data['model_digest'] != DIGEST or type(data['dimension']) is not int or data['dimension'] != 768 or data['operation'] != operation:
            raise ValueError()
        counts = data['input_tokens']
        vectors = data['embeddings']
        if type(counts) is not list or len(counts) != count or any(type(n) is not int or not 1 <= n <= 512 for n in counts):
            raise ValueError()
        if type(vectors) is not list or len(vectors) != count:
            raise ValueError()
        for vector in vectors:
            if type(vector) is not list or len(vector) != 768 or any(type(x) not in (int, float) or not math.isfinite(x) for x in vector):
                raise ValueError()
            norm = math.hypot(*vector)
            if not .999 <= norm <= 1.001:
                raise ValueError()
        return tuple(tuple(v) for v in vectors)
    except Exception:
        raise Rejected('invalid_remote_response') from None


class OfflineCandidate:
    def __init__(self, exchange, *, max_calls, total_seconds, clock=time.monotonic):
        # No defaults: these policy choices still need app/operator review.
        if not callable(exchange) or type(max_calls) is not int or not 1 <= max_calls <= 32 or type(total_seconds) not in (int, float) or not math.isfinite(total_seconds) or total_seconds <= 0:
            raise Rejected('explicit_policy_required')
        self.exchange, self.max_calls, self.total_seconds, self.clock = exchange, max_calls, total_seconds, clock

    def embed(self, operation, texts):
        deadline = self.clock() + self.total_seconds
        parts = batches(operation, texts)
        if len(parts) > self.max_calls:
            raise Rejected('whole_request_call_limit')
        collected = []
        for part in parts:
            remaining = deadline - self.clock()
            if remaining <= 0:
                raise Rejected('whole_request_deadline')
            try:
                status, raw = self.exchange(encode(operation, part), remaining)
            except Exception:
                raise Rejected('transport_failed') from None
            if self.clock() >= deadline:
                raise Rejected('whole_request_deadline')
            if type(status) is not int or status != 200:
                raise Rejected(STATUS_CODES.get(status, 'remote_failed'))
            collected.extend(validate_response(raw, operation, len(part)))
        return tuple(collected)


def fixture_ingest(client, texts, atomic_store):
    """Recording-store fixture seam only, not an actual repository transaction."""
    all_vectors = client.embed('documents', texts)
    return atomic_store(texts, all_vectors)
