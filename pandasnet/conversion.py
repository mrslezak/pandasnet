"""Helpers for adapting NumPy values to pythonnet CLR method parameters."""

from collections.abc import Callable

import numpy as np
from System import (
    Array,
    Boolean,
    Byte,
    DateTime,
    DateTimeKind,
    Double,
    Int16,
    Int32,
    Int64,
    SByte,
    Single,
    String,
    TimeSpan,
    UInt16,
    UInt32,
    UInt64,
)


_SIGNED_INTEGER_TYPES = {1: SByte, 2: Int16, 4: Int32, 8: Int64}
_UNSIGNED_INTEGER_TYPES = {1: Byte, 2: UInt16, 4: UInt32, 8: UInt64}
_SUPPORTED_TIME_UNITS = {"W", "D", "h", "m", "s", "ms", "us", "ns"}
_UNIX_EPOCH_TICKS = DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc).Ticks


def _nanoseconds_to_ticks(value: np.integer) -> int:
    nanoseconds = int(value)
    return nanoseconds // 100 if nanoseconds >= 0 else -((-nanoseconds) // 100)


def _temporal_values(values: np.ndarray, kind: str) -> list:
    unit, _ = np.datetime_data(values.dtype)
    if unit not in _SUPPORTED_TIME_UNITS:
        raise TypeError(f"NumPy {kind} unit {unit!r} is not supported")
    if np.isnat(values).any():
        raise ValueError(f"NumPy {kind} arrays containing NaT cannot be converted")

    nanoseconds = values.astype(f"{kind}[ns]").view(np.int64).ravel(order="C")
    ticks = [_nanoseconds_to_ticks(value) for value in nanoseconds]
    if kind == "datetime64":
        return [DateTime(_UNIX_EPOCH_TICKS + value, DateTimeKind.Utc) for value in ticks]
    return [TimeSpan.FromTicks(value) for value in ticks]


def _array_to_clr(values: np.ndarray):
    if values.ndim not in (1, 2):
        raise ValueError("Only one-dimensional or two-dimensional NumPy arrays can be wrapped for CLR array parameters")

    dtype = values.dtype
    kind = dtype.kind
    flattened = values.ravel(order="C")
    if kind == "b":
        element_type = Boolean
        converted = [bool(value) for value in flattened]
    elif kind == "i":
        element_type = _SIGNED_INTEGER_TYPES.get(dtype.itemsize)
        converted = [int(value) for value in flattened]
    elif kind == "u":
        element_type = _UNSIGNED_INTEGER_TYPES.get(dtype.itemsize)
        converted = [int(value) for value in flattened]
    elif kind == "f" and dtype.itemsize == 4:
        element_type = Single
        converted = [float(value) for value in flattened]
    elif kind == "f" and dtype.itemsize == 8:
        element_type = Double
        converted = [float(value) for value in flattened]
    elif kind in {"U", "S", "O"}:
        element_type = String
        if kind == "O" and not all(isinstance(value, (str, bytes, np.str_, np.bytes_)) for value in flattened):
            raise TypeError("Object arrays can only be wrapped when all values are strings")
        converted = [value.decode("utf-8") if isinstance(value, (bytes, np.bytes_)) else str(value) for value in flattened]
    elif kind == "M":
        element_type = DateTime
        converted = _temporal_values(values, "datetime64")
    elif kind == "m":
        element_type = TimeSpan
        converted = _temporal_values(values, "timedelta64")
    else:
        raise TypeError(f"NumPy dtype {dtype} has no supported CLR array mapping")

    if element_type is None:
        raise TypeError(f"NumPy dtype {dtype} has no supported CLR array mapping")

    if values.ndim == 1:
        return Array[element_type](converted)

    rows, columns = (int(length) for length in values.shape)
    result = Array.CreateInstance(element_type, rows, columns)
    for row in range(rows):
        for column in range(columns):
            value = converted[row * columns + column]
            if not isinstance(value, element_type):
                value = element_type(value)
            result.SetValue(value, row, column)
    return result


def _value_to_clr(value):
    if isinstance(value, np.ndarray):
        return _array_to_clr(value)
    if isinstance(value, np.integer):
        dtype = value.dtype
        element_type = (_SIGNED_INTEGER_TYPES if dtype.kind == "i" else _UNSIGNED_INTEGER_TYPES).get(dtype.itemsize)
        if element_type is None:
            raise TypeError(f"NumPy integer dtype {dtype} has no supported CLR mapping")
        return element_type(int(value))
    if isinstance(value, np.bool_):
        return Boolean(bool(value))
    if isinstance(value, np.floating):
        if value.dtype.itemsize == 4:
            element_type = Single
        elif value.dtype.itemsize == 8:
            element_type = Double
        else:
            raise TypeError(f"NumPy floating dtype {value.dtype} has no supported CLR mapping")
        return element_type(float(value))
    if isinstance(value, (np.str_, str)):
        return String(str(value))
    if isinstance(value, (np.bytes_, bytes)):
        return String(bytes(value).decode("utf-8"))
    if isinstance(value, (np.datetime64, np.timedelta64)):
        array = np.asarray([value])
        return _array_to_clr(array)[0]
    return value


def wrap(method: Callable) -> Callable:
    """Wrap a CLR method so NumPy arrays/scalars become typed CLR values first.

    Arrays are mapped by dtype to corresponding CLR element types. One-
    dimensional inputs become CLR vectors, and two-dimensional inputs become
    rectangular CLR arrays with row and column order preserved. NumPy integer
    scalars are normalized with ``int`` before constructing the matching CLR
    scalar or array. The CLR method's return value is left to pandasnet's
    registered encoders.
    """

    def invoke(*args, **kwargs):
        converted_args = tuple(_value_to_clr(value) for value in args)
        converted_kwargs = {name: _value_to_clr(value) for name, value in kwargs.items()}
        return method(*converted_args, **converted_kwargs)

    invoke.__name__ = getattr(method, "__name__", "wrapped_clr_method")
    invoke.__doc__ = getattr(method, "__doc__", None)
    return invoke


class _ClrProxy:
    """Proxy a CLR type or instance and adapt its callable members on access."""

    __slots__ = ("_target", "_methods")

    def __init__(self, target):
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_methods", {})

    def __getattr__(self, name):
        member = getattr(self._target, name)
        if not callable(member):
            return member

        methods = self._methods
        if name not in methods:
            methods[name] = wrap(member)
        return methods[name]

    def __setattr__(self, name, value):
        setattr(self._target, name, value)

    def __dir__(self):
        return sorted(set(dir(type(self)) + dir(self._target)))

    def __repr__(self):
        return f"pandasnet proxy for {self._target!r}"


def wrap_class(target):
    """Adapt a CLR type/instance once; NumPy arguments are converted on calls.

    Example::

        safe_api = pandasnet.wrap_class(ClrApi)
        result = safe_api.ProcessArray(numpy_values)
    """

    return _ClrProxy(target)
