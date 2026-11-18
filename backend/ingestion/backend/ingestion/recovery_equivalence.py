"""Pure recovery comparison. Local float4 projection is not database proof."""
from enum import Enum
import math
from numbers import Real
import struct

RECOVERY_CHUNK_CAP = 128  # Existing ingestion MAX_CHUNKS; query reads one sentinel.


class Equivalence(Enum):
    EQUIVALENT = 'equivalent'
    DIFFERENT = 'different'
    UNRESOLVED = 'unresolved'


def exact_value(left, right):
    """Exact nested contract value, not Python bool/int/float coercion.

    Vectors use the separate float4 rule, never this metadata comparison.
    JSON dictionaries ignore key order but preserve every key/value type.
    """
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        if len(left) != len(right):
            return False
        # Stored JSON keys are strings; enforce this rather than Python's
        # numeric-key coercion when inspecting malformed fabricated values.
        if any(type(key) is not str for key in (*left, *right)):
            return False
        return left.keys() == right.keys() and all(exact_value(left[key], right[key]) for key in left)
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(exact_value(a,b) for a,b in zip(left,right))
    return left == right


def packed_float4(vector, dimension, *, persisted):
    values = tuple(vector)
    if len(values) != dimension:
        raise ValueError('vector dimension')
    packed = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError('real component required')
        number = float(value)
        if not math.isfinite(number):
            raise ValueError('finite component required')
        binary = struct.pack('!f', number)
        restored = struct.unpack('!f', binary)[0]
        if not math.isfinite(restored) or (persisted and restored != number):
            raise ValueError('already float4-representable component required')
        packed.append(binary)  # Preserve signed zero conservatively.
    return tuple(packed)


def compare_recovery_rows(rows, expected_document, expected_chunks, original_units, dimension):
    """Compare complete aliased LEFT JOIN rows to ORIGINAL prepared input.

    Missing/malformed/incomplete candidate sets are unresolved, not corruption or
    rollback proof. Complete mismatches are different. No retries or mutation.
    """
    try:
        if not rows or len(rows) > RECOVERY_CHUNK_CAP:
            return Equivalence.UNRESOLVED
        child_fields = ('located_id','document_id','ordinal','original_chunk_id','segment_index','text','start','end','locator')
        vector_fields = ('located_id','vector','profile','created_at')
        required = tuple('chunk__'+key for key in child_fields) + tuple('vector__'+key for key in vector_fields)
        if any(any(key not in row for key in required) for row in rows):
            return Equivalence.UNRESOLVED
        count = len(expected_chunks)
        if count > RECOVERY_CHUNK_CAP or len(original_units) != count:
            return Equivalence.UNRESOLVED
        parent = {key: rows[0]['doc__' + key] for key in expected_document}
        if any(not exact_value({key: row['doc__' + key] for key in expected_document}, parent) for row in rows):
            return Equivalence.UNRESOLVED
        declared = parent['chunk_count']
        if type(declared) is not int or not 0 <= declared <= RECOVERY_CHUNK_CAP:
            return Equivalence.UNRESOLVED
        # A zero-chunk parent appears as one null child sentinel under LEFT JOIN.
        if declared == 0:
            if len(rows) != 1 or any(rows[0][key] is not None for key in rows[0] if key.startswith(('chunk__', 'vector__'))):
                return Equivalence.UNRESOLVED
            complete = []
        else:
            if len(rows) != declared:
                return Equivalence.UNRESOLVED
            complete = sorted(rows, key=lambda row: row['chunk__ordinal'])
            if any(type(row['chunk__ordinal']) is not int for row in complete) or [row['chunk__ordinal'] for row in complete] != list(range(declared)):
                return Equivalence.UNRESOLVED
            ids = [row['chunk__located_id'] for row in complete]
            if len(set(ids)) != declared or any(not isinstance(i, str) or not i for i in ids):
                return Equivalence.UNRESOLVED
            for row in complete:
                if any(row['chunk__'+key] is None for key in child_fields):
                    return Equivalence.UNRESOLVED
                if row['vector__profile'] is None:
                    return Equivalence.UNRESOLVED
                if row['vector__located_id'] != row['chunk__located_id'] or row['vector__vector'] is None:
                    return Equivalence.UNRESOLVED
                packed_float4(row['vector__vector'], dimension, persisted=True)
        if not exact_value(parent, expected_document) or declared != count:
            return Equivalence.DIFFERENT
        for row, chunk, unit in zip(complete, expected_chunks, original_units):
            if any(type(row['chunk__'+key]) is not int for key in ('ordinal','segment_index','start','end')):
                return Equivalence.UNRESOLVED
            if not exact_value({key: row['chunk__' + key] for key in chunk}, chunk):
                return Equivalence.DIFFERENT
            if row['vector__profile'] != expected_document['embedding_profile']:
                return Equivalence.DIFFERENT
            if packed_float4(row['vector__vector'], dimension, persisted=True) != packed_float4(unit, dimension, persisted=False):
                return Equivalence.DIFFERENT
        return Equivalence.EQUIVALENT
    except (KeyError, TypeError, ValueError, OverflowError, struct.error):
        return Equivalence.UNRESOLVED
