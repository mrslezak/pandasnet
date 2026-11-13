"""Reflection over CLR types and Python-facing type hints that mirror pandasnet's conversions."""

import inspect
import keyword
from typing import NamedTuple

import clr
from System import Enum, MulticastDelegate, Nullable
from System.Reflection import BindingFlags

from .conversion import _DICTIONARIES, _TUPLES, _collection_target, _generic_interface

_INTEGERS = {
    "System.Byte", "System.SByte", "System.Int16", "System.UInt16",
    "System.Int32", "System.UInt32", "System.Int64", "System.UInt64",
}
_SCALARS = {
    **dict.fromkeys(_INTEGERS, "int"),
    "System.Boolean": "bool",
    "System.Single": "float",
    "System.Double": "float",
    "System.Decimal": "float",
    "System.String": "str",
    "System.Char": "str",
    "System.DateTime": "datetime",
    "System.TimeSpan": "timedelta",
    "System.Object": "Any",
    "System.Void": "None",
}
# Element types whose CLR arrays the codecs return as NumPy arrays.
_NDARRAY_ELEMENTS = _INTEGERS | {
    "System.Boolean", "System.Single", "System.Double", "System.DateTime", "System.TimeSpan", "System.String",
}
_ENUMERABLE = "System.Collections.Generic.IEnumerable`1"
_DELEGATE = clr.GetClrType(MulticastDelegate)
_MEMBERS = BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static | BindingFlags.FlattenHierarchy

# Spelling of helper names in hints; stub files substitute module-qualified names.
DISPLAY_NAMES = {
    name: name
    for name in ("Any", "Callable", "Iterable", "Mapping", "datetime", "timedelta", "ndarray", "DataFrame", "DatetimeIndex")
}


class Parameter(NamedTuple):
    name: str
    clr_type: object
    default: object  # inspect.Parameter.empty when required


class EnumDefault(NamedTuple):
    type_name: str
    member: str

    def __repr__(self):
        return f"{self.type_name}.{self.member}"


class Overload(NamedTuple):
    parameters: tuple
    return_type: object  # None for constructors
    clr_signature: str


class Member(NamedTuple):
    name: str
    static: bool
    clr_type: object
    readable: bool
    writable: bool


def python_name(name: str) -> str:
    return f"{name}_" if keyword.iskeyword(name) else name


def _parameters(method):
    parameters = []
    for index, parameter in enumerate(method.GetParameters()):
        name = python_name(parameter.Name or f"arg{index}")
        default = inspect.Parameter.empty
        if parameter.IsOptional:
            value = parameter.DefaultValue if parameter.HasDefaultValue else None
            if parameter.ParameterType.IsEnum and value is not None:
                member = Enum.GetName(parameter.ParameterType, value)
                default = EnumDefault(parameter.ParameterType.Name, str(member if member is not None else value))
            else:
                default = value if isinstance(value, (bool, int, float, str, type(None))) else ...
        parameters.append(Parameter(name, parameter.ParameterType, default))
    return tuple(parameters)


def constructors(clr_type) -> list:
    return [Overload(_parameters(ctor), None, str(ctor)) for ctor in clr_type.GetConstructors()]


def methods(clr_type) -> dict:
    """Public methods by name: {name: (static, generic, [Overload, ...])}.

    Accessors, operators and System.Object's own members (Equals, GetHashCode, ...) are left out; they
    remain callable through pythonnet.
    """
    grouped = {}
    for method in clr_type.GetMethods(_MEMBERS):
        if method.IsSpecialName or method.DeclaringType.FullName == "System.Object":
            continue
        entry = grouped.setdefault(method.Name, [True, False, []])
        entry[0] = entry[0] and method.IsStatic
        entry[1] = entry[1] or method.IsGenericMethodDefinition
        entry[2].append(Overload(_parameters(method), method.ReturnType, str(method)))
    return {name: tuple(entry) for name, entry in grouped.items()}


def members(clr_type) -> list:
    """Public non-indexer properties and fields."""
    result = {}
    for prop in clr_type.GetProperties(_MEMBERS):
        if prop.GetIndexParameters().Length or prop.Name in result:
            continue
        getter, setter = prop.GetGetMethod(), prop.GetSetMethod()
        accessor = getter or setter
        result[prop.Name] = Member(prop.Name, accessor.IsStatic, prop.PropertyType, getter is not None, setter is not None)
    for field in clr_type.GetFields(_MEMBERS):
        if field.Name not in result:
            writable = not (field.IsInitOnly or field.IsLiteral)
            result[field.Name] = Member(field.Name, field.IsStatic, field.FieldType, True, writable)
    return list(result.values())


def indexer(clr_type):
    """(index parameter types, value type, writable) of the default indexer, or None."""
    for prop in clr_type.GetProperties(BindingFlags.Public | BindingFlags.Instance):
        parameters = prop.GetIndexParameters()
        if parameters.Length:
            return [p.ParameterType for p in parameters], prop.PropertyType, prop.GetSetMethod() is not None
    return None


def implementations(clr_type, candidates) -> list:
    """Concrete types among candidates that can be passed where clr_type (an interface/abstract class) is expected."""
    return [
        candidate
        for candidate in candidates
        if not (candidate.IsInterface or candidate.IsAbstract or candidate.IsGenericTypeDefinition)
        and not candidate.Equals(clr_type)
        and clr_type.IsAssignableFrom(candidate)
    ]


def direct_bases(clr_type, include) -> list:
    """Base class and interfaces accepted by include, minus ones already implied by another base (base first)."""
    bases = []
    base = clr_type.BaseType
    if base is not None and include(base):
        bases.append(base)
    implied = {interface.FullName for interface in base.GetInterfaces()} if base is not None else set()
    interfaces = [interface for interface in clr_type.GetInterfaces() if include(interface)]
    for interface in interfaces:
        if interface.FullName in implied:
            continue
        if any(not other.Equals(interface) and interface.IsAssignableFrom(other) for other in interfaces):
            continue
        bases.append(interface)
    return bases


def element_type(clr_type):
    """Element type when instances are enumerable (IEnumerable<T>), else None."""
    if clr_type.FullName == "System.String":
        return None
    enumerable = _generic_interface(clr_type, _ENUMERABLE)
    return None if enumerable is None else enumerable.GetGenericArguments()[0]


def count_property(clr_type) -> bool:
    prop = clr_type.GetProperty("Count", BindingFlags.Public | BindingFlags.Instance)
    return prop is not None and prop.PropertyType.FullName == "System.Int32"


def is_delegate(clr_type) -> bool:
    return _DELEGATE.IsAssignableFrom(clr_type) and not clr_type.Equals(_DELEGATE)


def _opaque(clr_type) -> bool:
    return clr_type.IsByRef or clr_type.IsPointer or clr_type.IsGenericParameter or clr_type.ContainsGenericParameters


def param_hint(clr_type, resolve, names=DISPLAY_NAMES) -> str:
    """Python values accepted for a parameter of this CLR type."""
    if _opaque(clr_type):
        return names["Any"]
    underlying = Nullable.GetUnderlyingType(clr_type)
    if underlying is not None:
        return f"{param_hint(underlying, resolve, names)} | None"
    scalar = _SCALARS.get(clr_type.FullName)
    if scalar is not None:
        return names.get(scalar, scalar)
    if clr_type.IsEnum:
        return resolve(clr_type) or names["Any"]
    if clr_type.IsGenericType and clr_type.GetGenericTypeDefinition().FullName == "System.Collections.Generic.Dictionary`2":
        key, value = clr_type.GetGenericArguments()
        if key.FullName == "System.String" and value.FullName == "System.Array":
            return f"{names['DataFrame']} | {names['Mapping']}[str, {names['ndarray']}]"
    if clr_type.IsArray and clr_type.GetArrayRank() > 1:
        return names["ndarray"]
    dictionary = _generic_interface(clr_type, *_DICTIONARIES)
    if dictionary is not None:
        key, value = (param_hint(argument, resolve, names) for argument in dictionary.GetGenericArguments())
        return f"{names['Mapping']}[{key}, {value}]"
    collection = _collection_target(clr_type)
    if collection is not None:
        element = collection[0]
        text = f"{names['Iterable']}[{param_hint(element, resolve, names)}]"
        if element.FullName == "System.DateTime":
            return f"{text} | {names['DatetimeIndex']} | {names['ndarray']}"
        if element.FullName in _NDARRAY_ELEMENTS - {"System.String"}:
            return f"{text} | {names['ndarray']}"
        return text
    if is_delegate(clr_type):
        invoke = clr_type.GetMethod("Invoke")
        arguments = ", ".join(result_hint(p.ParameterType, resolve, names) for p in invoke.GetParameters())
        return f"{names['Callable']}[[{arguments}], {param_hint(invoke.ReturnType, resolve, names)}]"
    return resolve(clr_type) or names["Any"]


def _framework_collection(clr_type) -> bool:
    namespace = clr_type.Namespace or ""
    return namespace in ("System.Collections", "System.Linq") or namespace.startswith("System.Collections.")


def result_hint(clr_type, resolve, names=DISPLAY_NAMES) -> str:
    """Python type pandasnet returns for a value declared as this CLR type."""
    if _opaque(clr_type):
        return names["Any"]
    underlying = Nullable.GetUnderlyingType(clr_type)
    if underlying is not None:
        return f"{result_hint(underlying, resolve, names)} | None"
    scalar = _SCALARS.get(clr_type.FullName)
    if scalar is not None:
        return names.get(scalar, scalar)
    if clr_type.IsEnum:
        return resolve(clr_type) or names["Any"]
    if clr_type.IsArray:
        element = clr_type.GetElementType()
        if element.FullName in _NDARRAY_ELEMENTS:
            return names["ndarray"]
        return f"list[{result_hint(element, resolve, names)}]" if clr_type.GetArrayRank() == 1 else names["Any"]
    if clr_type.IsGenericType:
        definition = clr_type.GetGenericTypeDefinition().FullName
        arguments = list(clr_type.GetGenericArguments())
        if definition == "System.Collections.Generic.Dictionary`2" and arguments[0].FullName == "System.String" and (
            arguments[1].FullName == "System.Array"
        ):
            return names["DataFrame"]
        if definition.startswith(_TUPLES) or definition == "System.Collections.Generic.KeyValuePair`2":
            return f"tuple[{', '.join(result_hint(argument, resolve, names) for argument in arguments)}]"
    if is_delegate(clr_type):
        invoke = clr_type.GetMethod("Invoke")
        arguments = ", ".join(param_hint(p.ParameterType, resolve, names) for p in invoke.GetParameters())
        return f"{names['Callable']}[[{arguments}], {result_hint(invoke.ReturnType, resolve, names)}]"
    if not _framework_collection(clr_type):
        return resolve(clr_type) or names["Any"]
    dictionary = _generic_interface(clr_type, *_DICTIONARIES)
    if dictionary is not None:
        key, value = (result_hint(argument, resolve, names) for argument in dictionary.GetGenericArguments())
        return f"dict[{key}, {value}]"
    element = element_type(clr_type)
    if element is None:
        return names["Any"]
    if element.FullName in _NDARRAY_ELEMENTS:
        return names["ndarray"]
    return f"list[{result_hint(element, resolve, names)}]"
