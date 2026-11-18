"""Explicit test-qualified binary codec binding. No discovery or defaults."""
from dataclasses import dataclass
import math
import struct


@dataclass(frozen=True)
class VectorSendBinding:
    """Supply only after verifying extension membership/signature/namespace.

    The object is not runtime proof. Startup never supplies one. Function and
    schema are quoted by SQLAlchemy; no search_path or conventional-name guess.
    """
    schema: str
    function: str

    def __post_init__(self):
        if any(type(x) is not str or not x.strip() or '\x00' in x for x in (self.schema,self.function)):
            raise ValueError('explicit verified vector-send function binding required')


def decode_vector_binary(value, dimension):
    if type(dimension) is not int or not 1 <= dimension <= 16000:
        raise ValueError('explicit dimension required')
    if isinstance(value,memoryview):
        value=value.tobytes()
    if type(value) is not bytes or len(value) != 4+4*dimension:
        raise ValueError('exact vector binary bytes required')
    actual,reserved=struct.unpack_from('!HH',value)
    if actual != dimension or reserved != 0:
        raise ValueError('vector binary header mismatch')
    result=struct.unpack_from('!'+str(dimension)+'f',value,4)
    if not all(math.isfinite(x) for x in result):
        raise ValueError('finite vector binary components required')
    return result
