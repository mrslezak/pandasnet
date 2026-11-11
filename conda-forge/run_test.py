import numpy as np
import pandasnet
from System import Int32


def accept_int32(value):
    assert isinstance(value, Int32), f"expected System.Int32, got {type(value)!r}"
    return int(value)


assert pandasnet.wrap(accept_int32)(np.int32(42)) == 42
