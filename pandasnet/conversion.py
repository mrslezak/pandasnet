"""Helpers for adapting Python values to pythonnet CLR calls and CLR results back to Python."""

import ctypes
import inspect
from collections.abc import Callable, Iterable, Iterator, Mapping
from datetime import date, datetime, time, timedelta, timezone
from typing import NamedTuple

import clr
import numpy as np
from PandasNet import ArrayShape, Codecs
from System import (
    AppDomain,
    Array,
    Boolean,
    Buffer,
    Byte,
    Char,
    Converter,
    DateTime,
    DateTimeKind,
    Delegate,
    Double,
    Int16,
    Int32,
    Int64,
    IntPtr,
    Nullable,
    Object,
    SByte,
    Single,
    String,
    StringSplitOptions,
    TimeSpan,
    Tuple,
    Type,
    UInt16,
    UInt32,
    UInt64,
)
from System.Collections.Generic import Dictionary, List
from System.Linq import Enumerable
from System.Runtime.InteropServices import GCHandle, GCHandleType, Marshal


_SIGNED_INTEGER_TYPES = {1: SByte, 2: Int16, 4: Int32, 8: Int64}
_UNSIGNED_INTEGER_TYPES = {1: Byte, 2: UInt16, 4: UInt32, 8: UInt64}
_TICKS_PER_UNIT = {
    "W": 6_048_000_000_000,
    "D": 864_000_000_000,
    "h": 36_000_000_000,
    "m": 600_000_000,
    "s": 10_000_000,
    "ms": 10_000,
    "us": 10,
}
_UNIX_EPOCH_TICKS = DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc).Ticks
_MAX_DATETIME_TICKS = DateTime(9999, 12, 31).Ticks + TimeSpan.TicksPerDay - 1
_UTC_BINARY_FLAG = DateTime(0, DateTimeKind.Utc).ToBinary()
_FROM_BINARY = Delegate.CreateDelegate(
    clr.GetClrType(Converter[Int64, DateTime]), clr.GetClrType(DateTime).GetMethod("FromBinary")
)
# Invoked through reflection: a direct ConvertAll call would re-encode the DateTime[] result to NumPy.
_CONVERT_ALL_TO_DATETIME = clr.GetClrType(Array).GetMethod("ConvertAll").MakeGenericMethod(
    clr.GetClrType(Int64), clr.GetClrType(DateTime)
)
_STRING_SEPARATOR = "\x1f"
# Invoked through reflection so the string[] result is not re-encoded to NumPy.
_SPLIT_STRING = next(
    method
    for method in clr.GetClrType(String).GetMethods()
    if method.Name == "Split"
    and [parameter.ParameterType.FullName for parameter in method.GetParameters()]
    == ["System.Char[]", "System.StringSplitOptions"]
)
_SPLIT_ARGUMENTS = Array[Object]([Array[Char]([_STRING_SEPARATOR]), getattr(StringSplitOptions, "None")])


def _temporal_ticks(values: np.ndarray, kind: str) -> np.ndarray:
    """CLR ticks (truncated toward zero) for datetime64/timedelta64 values; datetimes count from 0001-01-01."""
    unit, count = np.datetime_data(values.dtype)
    if unit != "ns" and unit not in _TICKS_PER_UNIT:
        raise TypeError(f"NumPy {kind} unit {unit!r} is not supported")
    if np.isnat(values).any():
        raise ValueError(f"NumPy {kind} arrays containing NaT cannot be converted")

    raw = np.ascontiguousarray(values, dtype=values.dtype.newbyteorder("=")).view(np.int64)
    if unit == "ns":
        scaled = raw * count
        ticks = np.where(scaled < 0, -(-scaled // 100), scaled // 100)
    else:
        factor = _TICKS_PER_UNIT[unit] * count
        if (np.abs(raw) > np.iinfo(np.int64).max // factor).any():
            raise ValueError(f"NumPy {kind} values are outside the range of CLR ticks")
        ticks = raw * factor
    if kind == "timedelta64":
        return ticks
    if ((ticks < -_UNIX_EPOCH_TICKS) | (ticks > _MAX_DATETIME_TICKS - _UNIX_EPOCH_TICKS)).any():
        raise ValueError("NumPy datetime64 values are outside the range of System.DateTime")
    return ticks + _UNIX_EPOCH_TICKS


def _datetime_vector(ticks: np.ndarray):
    binary = ticks.ravel(order="C") | _UTC_BINARY_FLAG
    longs = Array.CreateInstance(Int64, binary.size)
    if binary.size:
        Marshal.Copy(IntPtr(binary.ctypes.data), longs, 0, binary.size)
    return _CONVERT_ALL_TO_DATETIME.Invoke(None, Array[Object]([longs, _FROM_BINARY]))


def _string_values(values: np.ndarray, kind: str) -> list:
    flattened = values.ravel(order="C").tolist()
    if kind == "U":
        return flattened
    if kind == "O" and not all(isinstance(value, (str, bytes)) for value in flattened):
        raise TypeError("Object arrays can only be wrapped when all values are strings")
    return [value.decode("utf-8") if isinstance(value, bytes) else str(value) for value in flattened]


def _string_vector(strings: list):
    joined = _STRING_SEPARATOR.join(strings)
    if not strings or joined.count(_STRING_SEPARATOR) != len(strings) - 1:
        return Array[String](strings)
    return _SPLIT_STRING.Invoke(joined, _SPLIT_ARGUMENTS)


def _timespan_array_to_clr(ticks: np.ndarray):
    # TimeSpan arrays can be pinned on .NET Framework (DateTime arrays cannot).
    ticks = np.ascontiguousarray(ticks)
    result = _clr_shaped_array(TimeSpan, ticks.shape)
    if ticks.size:
        handle = GCHandle.Alloc(result, GCHandleType.Pinned)
        try:
            ctypes.memmove(handle.AddrOfPinnedObject().ToInt64(), ticks.ctypes.data, ticks.nbytes)
        finally:
            handle.Free()
    return result


def _array_element_type(dtype: np.dtype):
    """Return the CLR element type for a NumPy dtype, or None when unsupported."""
    kind = dtype.kind
    if kind == "b":
        return Boolean
    if kind == "i":
        return _SIGNED_INTEGER_TYPES.get(dtype.itemsize)
    if kind == "u":
        return _UNSIGNED_INTEGER_TYPES.get(dtype.itemsize)
    if kind == "f":
        return {4: Single, 8: Double}.get(dtype.itemsize)
    if kind in {"U", "S", "O"}:
        return String
    if kind == "M":
        return DateTime
    if kind == "m":
        return TimeSpan
    return None


def _clr_shaped_array(element_type, shape: tuple):
    return Array.CreateInstance(element_type, Array[Int32]([int(length) for length in shape]))


def _primitive_array_to_clr(values: np.ndarray, element_type):
    # NumPy C order and CLR arrays of any rank are both row-major, so the bytes copy unchanged.
    values = np.ascontiguousarray(values, dtype=values.dtype.newbyteorder("="))
    result = _clr_shaped_array(element_type, values.shape)
    if values.nbytes:
        buffer = Array.CreateInstance(Byte, values.nbytes)
        Marshal.Copy(IntPtr(values.ctypes.data), buffer, 0, values.nbytes)
        Buffer.BlockCopy(buffer, 0, result, 0, values.nbytes)
    return result


def _array_to_clr(values: np.ndarray):
    if values.ndim == 0:
        raise ValueError("Zero-dimensional NumPy arrays cannot be wrapped for CLR array parameters")

    dtype = values.dtype
    kind = dtype.kind
    element_type = _array_element_type(dtype)
    if element_type is None:
        raise TypeError(f"NumPy dtype {dtype} has no supported CLR array mapping")
    if kind in {"b", "i", "u", "f"}:
        return _primitive_array_to_clr(values, element_type)
    if kind == "m":
        return _timespan_array_to_clr(_temporal_ticks(values, "timedelta64"))

    if kind == "M":
        vector = _datetime_vector(_temporal_ticks(values, "datetime64"))
    else:
        vector = _string_vector(_string_values(values, kind))
    if values.ndim == 1:
        return vector
    return ArrayShape.Reshape[element_type](vector, Array[Int32]([int(length) for length in values.shape]))


def _value_to_clr(value):
    if isinstance(value, np.ndarray):
        return _array_to_clr(value)
    # Checked before np.integer because np.timedelta64 subclasses np.signedinteger.
    if isinstance(value, (np.datetime64, np.timedelta64)):
        # GetValue is declared as object, so the CLR value is not re-encoded to a Python datetime.
        return _array_to_clr(np.asarray([value])).GetValue(0)
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
    return value


# --- Target-aware Python -> CLR conversion -----------------------------------------------------

# CLR primitive full name -> (pythonnet type, NumPy dtype), derived from the dtype mapping above.
_CLR_NUMERIC = {
    clr.GetClrType(_array_element_type(dtype)).FullName: (_array_element_type(dtype), dtype)
    for dtype in map(np.dtype, ("?", "i1", "i2", "i4", "i8", "u1", "u2", "u4", "u8", "f4", "f8"))
}
_GENERIC_COST = 10
_UNCERTAIN_COST = 50
_ENUMERABLE = "System.Collections.Generic.IEnumerable`1"
_DICTIONARIES = ("System.Collections.Generic.IDictionary`2", "System.Collections.Generic.IReadOnlyDictionary`2")


class _Plan(NamedTuple):
    """How one Python value is passed to one CLR parameter type."""

    cost: int
    certain: bool  # False when only pythonnet can tell, at call time, whether the value converts
    convert: Callable[[], object]


def _uncertain_plan(value) -> _Plan:
    return _Plan(_UNCERTAIN_COST, False, lambda: _value_to_clr(value))


def _generic_interface(clr_type, *definitions):
    """Return clr_type or one of its interfaces when it closes one of the generic definitions."""
    for candidate in (clr_type, *clr_type.GetInterfaces()):
        if candidate.IsGenericType and candidate.GetGenericTypeDefinition().FullName in definitions:
            return candidate
    return None


def _native_clr_type(value):
    """CLR type a Python scalar maps to without target information, or None if not modelled."""
    if isinstance(value, (bool, np.bool_)):
        return Boolean
    if isinstance(value, (np.integer, np.floating)):
        return _array_element_type(value.dtype)
    if isinstance(value, int):
        for clr_type, dtype in ((Int32, np.int32), (Int64, np.int64), (UInt64, np.uint64)):
            if np.iinfo(dtype).min <= value <= np.iinfo(dtype).max:
                return clr_type
        return None
    if isinstance(value, float):
        return Double
    if isinstance(value, (str, bytes, np.bytes_)):
        return String
    if isinstance(value, (date, np.datetime64)):
        return DateTime
    if isinstance(value, (timedelta, time, np.timedelta64)):
        return TimeSpan
    return None


def _numeric_cost(value, source: np.dtype, target: np.dtype):
    if source == target:
        return 0
    if "b" in (source.kind, target.kind):
        return None
    if target.kind in "iu":
        if source.kind not in "iu":
            return None
        info = np.iinfo(target)
        if not info.min <= int(value) <= info.max:
            return None
        return 1 if np.can_cast(source, target, "safe") else 2
    if source.kind == "f":
        return 1 if np.can_cast(source, target, "safe") else 2
    return 2 if np.can_cast(source, target, "safe") else 3


def _scalar_plan(value, native, target):
    native_type = clr.GetClrType(native)
    source = _CLR_NUMERIC.get(native_type.FullName)
    destination = _CLR_NUMERIC.get(target.FullName)
    if source is not None and destination is not None:
        cost = _numeric_cost(value, source[1], destination[1])
        if cost is None:
            return None
        target_class, dtype = destination
        number = bool(value) if dtype.kind == "b" else int(value) if dtype.kind in "iu" else float(value)
        return _Plan(cost, True, lambda: target_class(number))
    if target.Equals(native_type):
        approximate = isinstance(value, (bytes, np.bytes_, time)) or (
            isinstance(value, date) and not isinstance(value, datetime)
        )
        return _Plan(int(approximate), True, lambda: _scalar_to_clr(value))
    if target.FullName == "System.Char" and isinstance(value, str) and len(value) == 1:
        return _Plan(1, True, lambda: value)
    if target.IsAssignableFrom(native_type):
        return _Plan(_GENERIC_COST, True, lambda: _scalar_to_clr(value))
    return None


_CLR_EPOCH = datetime(1, 1, 1)
_ONE_MICROSECOND = timedelta(microseconds=1)


def _scalar_to_clr(value):
    """Python date/time values as CLR DateTime/TimeSpan (same Kind rules as the codecs); others via _value_to_clr."""
    if isinstance(value, datetime):
        kind = DateTimeKind.Local
        if value.utcoffset() is not None:
            value, kind = value.astimezone(timezone.utc), DateTimeKind.Utc
        wall_clock = datetime.combine(value.date(), value.time())
        ticks = (wall_clock - _CLR_EPOCH) // _ONE_MICROSECOND * 10 + getattr(value, "nanosecond", 0) // 100
        return DateTime(ticks, kind)
    if isinstance(value, date):
        return DateTime(value.year, value.month, value.day)
    if isinstance(value, timedelta):
        return TimeSpan(value // _ONE_MICROSECOND * 10 + getattr(value, "nanoseconds", 0) // 100)
    if isinstance(value, time):
        return TimeSpan((datetime.combine(_CLR_EPOCH, value.replace(tzinfo=None)) - _CLR_EPOCH) // _ONE_MICROSECOND * 10)
    return _value_to_clr(value)


def _clr_instance_plan(value, target):
    if not target.IsInstanceOfType(value):
        return None
    if target.Equals(value.GetType()):
        cost = 0
    elif target.Equals(clr.GetClrType(Object)):
        cost = _GENERIC_COST
    else:
        cost = 1
    return _Plan(cost, True, lambda: value)


def _collection_target(target):
    """(element type, container cost, is_array) when a Python sequence can be built for target."""
    if target.IsArray:
        return (target.GetElementType(), 1, True) if target.GetArrayRank() == 1 else None
    enumerable = _generic_interface(target, _ENUMERABLE)
    if enumerable is None:
        return None
    element = enumerable.GetGenericArguments()[0]
    list_type = clr.GetClrType(List[element])
    if target.Equals(list_type):
        return element, 1, False
    if target.IsAssignableFrom(list_type):
        return element, 2, False
    return None


def _clr_list(element_type, items):
    result = List[element_type]()
    for item in items:
        result.Add(item)
    return result


def _clr_array(element_type, items):
    values = _clr_list(element_type, items)
    result = Array.CreateInstance(element_type, values.Count)
    values.CopyTo(result)
    return result


def _sequence_plan(values, collection):
    element, cost, is_array = collection
    plans = [_plan(value, element) for value in values]
    if any(plan is None for plan in plans):
        return None
    build = _clr_array if is_array else _clr_list
    return _Plan(
        cost + max((plan.cost for plan in plans), default=0),
        all(plan.certain for plan in plans),
        lambda: build(element, [plan.convert() for plan in plans]),
    )


def _mapping_plan(values: Mapping, target):
    key_type, value_type = _generic_interface(target, *_DICTIONARIES).GetGenericArguments()
    dictionary_type = clr.GetClrType(Dictionary[key_type, value_type])
    if target.Equals(dictionary_type):
        cost = 1
    elif target.IsAssignableFrom(dictionary_type):
        cost = 2
    else:
        return None
    plans = [(_plan(key, key_type), _plan(item, value_type)) for key, item in values.items()]
    if any(key is None or item is None for key, item in plans):
        return None

    def build():
        result = Dictionary[key_type, value_type]()
        for key, item in plans:
            result.Add(key.convert(), item.convert())
        return result

    return _Plan(
        cost + max((max(key.cost, item.cost) for key, item in plans), default=0),
        all(key.certain and item.certain for key, item in plans),
        build,
    )


def _ndarray_plan(values: np.ndarray, target):
    native = _array_element_type(values.dtype)
    if native is None or values.ndim == 0:
        return None
    native = clr.GetClrType(native)
    if target.IsArray and target.GetArrayRank() == values.ndim:
        element, cost, is_array = target.GetElementType(), 0, True
    elif values.ndim == 1 and (collection := _collection_target(target)) is not None:
        element, cost, is_array = collection
    else:
        native_array = native.MakeArrayType() if values.ndim == 1 else native.MakeArrayType(values.ndim)
        if target.IsAssignableFrom(native_array):
            return _Plan(_GENERIC_COST, True, lambda: _array_to_clr(values))
        return None

    if element.Equals(native):
        source = lambda: values  # noqa: E731
    else:
        cast = _CLR_NUMERIC.get(element.FullName)
        if cast is None or values.dtype.kind not in "iuf" or cast[1].kind == "b":
            return None
        if not np.can_cast(values.dtype, cast[1], "safe"):
            return None
        cost += 2
        source = lambda: values.astype(cast[1])  # noqa: E731

    if is_array:
        return _Plan(cost, True, lambda: _array_to_clr(source()))
    return _Plan(cost, True, lambda: List[element](_array_to_clr(source())))


def _as_sequence(value):
    """list/tuple/ndarray form of a collection-like value, or None for scalars, mappings and 2-D frames."""
    if isinstance(value, (list, tuple, np.ndarray)):
        return value
    if isinstance(value, (str, bytes, Mapping)):
        return None
    if hasattr(value, "ndim"):
        # pandas Series/Index (incl. DatetimeIndex) keep their dtype; DataFrames and scalars are not sequences.
        return value.to_numpy() if value.ndim == 1 and hasattr(value, "to_numpy") else None
    if isinstance(value, Iterable) and not isinstance(value, Iterator):
        return list(value)
    return None


def _plan(value, target):
    """Plan how to pass a Python value to a CLR parameter type; None if it certainly cannot be."""
    underlying = Nullable.GetUnderlyingType(target)
    if value is None:
        return _Plan(0, True, lambda: None) if not target.IsValueType or underlying is not None else None
    if underlying is not None:
        return _plan(value, underlying)
    if isinstance(value, Object):
        return _clr_instance_plan(value, target)
    sequence = _as_sequence(value)
    if sequence is not None:
        collection = _collection_target(target)
        if isinstance(sequence, np.ndarray):
            plan = _ndarray_plan(sequence, target)
            if plan is not None or sequence.dtype.kind != "O" or sequence.ndim != 1 or collection is None:
                return plan
            sequence = list(sequence)
        elif collection is None:
            return _uncertain_plan(value)
        return _sequence_plan(sequence, collection)
    if isinstance(value, Mapping):
        if _generic_interface(target, *_DICTIONARIES) is None:
            return _uncertain_plan(value)
        return _mapping_plan(value, target)
    native = _native_clr_type(value)
    if native is None:
        return _uncertain_plan(value)
    return _scalar_plan(value, native, target)


# --- CLR signature discovery and overload resolution --------------------------------------------

_TYPE_CACHE = {}


def _lookup_type(name: str):
    """Find a loaded CLR type by the name System.Type.ToString() prints for it."""
    found = _TYPE_CACHE.get(name)
    if found is not None:
        return found
    if "." not in name and "+" not in name:
        # MethodBase.ToString() prints top-level primitives (Double, Int32, Void) without a namespace.
        found = Type.GetType(f"System.{name}")
        if found is not None and not (found.IsPrimitive or found.FullName == "System.Void"):
            found = None
    if found is None:
        found = Type.GetType(name)
    if found is None:
        for assembly in AppDomain.CurrentDomain.GetAssemblies():
            found = assembly.GetType(name)
            if found is not None:
                break
    if found is not None:
        _TYPE_CACHE[name] = found
    return found


def _split_type_list(text: str) -> list:
    parts, depth, start = [], 0, 0
    for index, char in enumerate(text):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    parts.append(text[start:].strip())
    return [part for part in parts if part]


def _parse_clr_type(text: str):
    """Resolve a System.Type.ToString()-style name, including generics and arrays."""
    if text.endswith(("&", "*")):
        return None
    if not text.endswith("]"):
        return _lookup_type(text)
    depth = 0
    for start in range(len(text) - 1, -1, -1):
        depth += {"]": 1, "[": -1}.get(text[start], 0)
        if depth == 0:
            break
    base, inner = _parse_clr_type(text[:start]), text[start + 1 : -1]
    if base is None:
        return None
    if inner == "":
        return base.MakeArrayType()
    if set(inner) == {","}:
        return base.MakeArrayType(len(inner) + 1)
    if not base.IsGenericTypeDefinition:
        return None
    arguments = [_parse_clr_type(argument) for argument in _split_type_list(inner)]
    if any(argument is None for argument in arguments):
        return None
    return base.MakeGenericType(Array[Type](arguments))


class _Parameter(NamedTuple):
    name: str
    clr_type: object
    optional: bool


class _Overload(NamedTuple):
    signature: str
    parameters: tuple
    invoke: Callable


def _constructor_overloads(cls):
    overloads = []
    for constructor in clr.GetClrType(cls).GetConstructors():
        parameters = tuple(
            _Parameter(parameter.Name, parameter.ParameterType, parameter.IsOptional)
            for parameter in constructor.GetParameters()
        )
        if any(parameter.clr_type.IsByRef or parameter.clr_type.IsPointer for parameter in parameters):
            return None
        overloads.append(_Overload(str(constructor), parameters, cls))
    return overloads


def _method_overloads(method):
    """Describe each overload listed in a pythonnet method's docstring; None if any is undescribable."""
    overloads = []
    for signature in filter(None, (line.strip() for line in (method.__doc__ or "").splitlines())):
        open_index = signature.find("(")
        if open_index < 0 or not signature.endswith(")") or signature[:open_index].endswith("]"):
            return None  # generic methods and non-signature docs are left to pythonnet
        types = [_parse_clr_type(name) for name in _split_type_list(signature[open_index + 1 : -1])]
        if any(clr_type is None for clr_type in types):
            return None
        if not types:
            continue  # zero-argument calls never need conversion
        try:
            selected = method.__overloads__[tuple(types)]
            parameters = list(inspect.signature(selected).parameters.values())
        except (TypeError, ValueError):
            return None
        if len(parameters) != len(types):
            return None
        overloads.append(
            _Overload(
                signature,
                tuple(
                    _Parameter(parameter.name, clr_type, parameter.default is not inspect.Parameter.empty)
                    for parameter, clr_type in zip(parameters, types)
                ),
                selected,
            )
        )
    return overloads


class _Match(NamedTuple):
    overload: _Overload
    parameters: list
    plans: list
    cost: int
    certain: bool


def _bind(overload: _Overload, args: tuple, kwargs: dict):
    parameters = overload.parameters
    if len(args) > len(parameters):
        return None
    remaining = {parameter.name: parameter for parameter in parameters[len(args) :]}
    if any(name not in remaining for name in kwargs):
        return None
    if any(not parameter.optional and name not in kwargs for name, parameter in remaining.items()):
        return None
    used = [*zip(args, parameters), *((value, remaining[name]) for name, value in kwargs.items())]
    plans = [_plan(value, parameter.clr_type) for value, parameter in used]
    if any(plan is None for plan in plans):
        return None
    return _Match(
        overload,
        [parameter for _, parameter in used],
        plans,
        sum(plan.cost for plan in plans),
        all(plan.certain for plan in plans),
    )


def _converts_to(source, target) -> bool:
    if target.IsAssignableFrom(source):
        return True
    source_numeric, target_numeric = _CLR_NUMERIC.get(source.FullName), _CLR_NUMERIC.get(target.FullName)
    return bool(source_numeric and target_numeric) and np.can_cast(source_numeric[1], target_numeric[1], "safe")


def _more_specific(match: _Match, other: _Match) -> bool:
    """C#-style betterness: every parameter type converts to other's, and not all the other way round."""
    pairs = [(mine.clr_type, theirs.clr_type) for mine, theirs in zip(match.parameters, other.parameters)]
    return all(_converts_to(mine, theirs) for mine, theirs in pairs) and not all(
        _converts_to(theirs, mine) for mine, theirs in pairs
    )


def _resolve(name: str, overloads: list, args: tuple, kwargs: dict):
    """Pick the best overload for the call, None to defer to pythonnet, or raise if ambiguous."""
    matches = [match for match in (_bind(overload, args, kwargs) for overload in overloads) if match is not None]
    if not matches:
        return None
    best = min(match.cost for match in matches)
    tied = [match for match in matches if match.cost == best]
    if len(tied) > 1:
        tied = [match for match in tied if not any(_more_specific(other, match) for other in tied if other is not match)]
    if len(tied) == 1:
        return tied[0]
    if all(match.certain for match in tied):
        signatures = "\n  ".join(match.overload.signature for match in tied)
        raise TypeError(f"Ambiguous call to {name}; these overloads match the arguments equally well:\n  {signatures}")
    return None


# --- CLR -> Python result conversion ----------------------------------------------------------

_TUPLES = ("System.Tuple`", "System.ValueTuple`")


def _encode(value, clr_type):
    # Codecs.Encode crashes when called from Python (pythonnet releases the GIL around CLR calls),
    # so let pythonnet run the registered encoder while returning a member declared as clr_type.
    return Tuple.Create[clr_type](value).Item1


def _is_collection(value, clr_type) -> bool:
    """Arrays and framework collections convert; domain types implementing IEnumerable<T> do not."""
    if clr_type.IsArray:
        return True
    for candidate in (clr.GetClrType(type(value)), clr_type):
        namespace = candidate.Namespace or ""
        if namespace in ("System.Collections", "System.Linq") or namespace.startswith("System.Collections."):
            return True
    return False


def _value_from_clr(value):
    """Recursively convert CLR data to Python/NumPy; other CLR objects are returned unchanged."""
    if not isinstance(value, Object):
        return value
    clr_type = value.GetType()
    if Codecs.Instance.CanEncode(clr_type):
        return _encode(value, clr_type)
    if clr_type.IsGenericType:
        definition = clr_type.GetGenericTypeDefinition().FullName
        if definition.startswith(_TUPLES):
            arity = clr_type.GetGenericArguments().Length
            items = tuple(_value_from_clr(getattr(value, f"Item{index}")) for index in range(1, min(arity, 7) + 1))
            return items + _value_from_clr(value.Rest) if arity == 8 else items
        if definition == "System.Collections.Generic.KeyValuePair`2":
            return _value_from_clr(value.Key), _value_from_clr(value.Value)
    if not _is_collection(value, clr_type):
        return value
    if clr_type.IsArray and clr_type.GetArrayRank() > 1:
        element = clr_type.GetElementType()
        vector_type = element.MakeArrayType()
        if not Codecs.Instance.CanEncode(vector_type):
            return value
        shape = tuple(value.GetLength(dimension) for dimension in range(clr_type.GetArrayRank()))
        if element.IsPrimitive:
            flat = Array.CreateInstance(element, value.Length)
            Buffer.BlockCopy(value, 0, flat, 0, Buffer.ByteLength(value))
            return _encode(flat, vector_type).reshape(shape)
        if element.Equals(clr.GetClrType(TimeSpan)):
            ticks = np.empty(shape, dtype=np.int64)
            if ticks.size:
                handle = GCHandle.Alloc(value, GCHandleType.Pinned)
                try:
                    ctypes.memmove(ticks.ctypes.data, handle.AddrOfPinnedObject().ToInt64(), ticks.nbytes)
                finally:
                    handle.Free()
            # Same truncation toward zero as the C# TimeSpan[] encoder.
            return np.where(ticks < 0, -(-ticks // 10), ticks // 10).astype("timedelta64[us]")
        return ArrayShape.Flatten[element](value).reshape(shape)
    if _generic_interface(clr_type, *_DICTIONARIES) is not None:
        return {_value_from_clr(pair.Key): _value_from_clr(pair.Value) for pair in value}
    enumerable = _generic_interface(clr_type, _ENUMERABLE)
    if enumerable is None:
        return value
    element = enumerable.GetGenericArguments()[0]
    if Codecs.Instance.CanEncode(element.MakeArrayType()):
        return Enumerable.ToArray[element](value)
    return [_value_from_clr(item) for item in value]


_UNDISCOVERED = object()


def _materialize(value):
    return list(value) if isinstance(value, Iterator) and not isinstance(value, Object) else value


def wrap(method: Callable) -> Callable:
    """Wrap a CLR method or constructor so Python values are adapted to its CLR signature.

    Each argument is converted for the parameter type of the best-matching
    overload: NumPy arrays become ``T[]``/``T[,]``/``T[,,]`` (any rank), lists/tuples become ``T[]``
    or ``List<T>`` for ``IEnumerable<T>``-style parameters, dicts become
    ``Dictionary<K, V>``, and scalars become the matching CLR primitive,
    recursively for elements. Overloads are ranked by conversion cost; equally
    good, certain matches raise ``TypeError``. Calls pandasnet cannot describe
    fall back to the previous behaviour of converting NumPy values and letting
    pythonnet bind.

    Method results are converted back recursively: numeric/temporal CLR arrays
    and framework collections become NumPy arrays, other collections become
    lists/dicts/tuples, and domain objects stay CLR objects. Constructors and
    plain Python callables return their result unchanged.
    """

    if isinstance(method, type) and issubclass(method, Object):
        discover, convert_result = _constructor_overloads, False
    elif hasattr(method, "__overloads__"):
        discover, convert_result = _method_overloads, True
    else:
        discover, convert_result = None, False
    name = getattr(method, "__name__", "wrapped_clr_method")
    overloads = _UNDISCOVERED

    def invoke(*args, **kwargs):
        nonlocal overloads
        match = None
        if discover is not None and (args or kwargs):
            # One-shot iterators are read once so every candidate overload sees the same elements.
            args = tuple(_materialize(value) for value in args)
            kwargs = {key: _materialize(value) for key, value in kwargs.items()}
            if overloads is _UNDISCOVERED:
                overloads = discover(method)
            if overloads:
                match = _resolve(name, overloads, args, kwargs)
        if match is None:
            converted_args = tuple(_value_to_clr(value) for value in args)
            converted_kwargs = {key: _value_to_clr(value) for key, value in kwargs.items()}
            result = method(*converted_args, **converted_kwargs)
        else:
            converted = [plan.convert() for plan in match.plans]
            result = match.overload.invoke(*converted[: len(args)], **dict(zip(kwargs, converted[len(args) :])))
        return _value_from_clr(result) if convert_result else result

    invoke.__name__ = name
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
