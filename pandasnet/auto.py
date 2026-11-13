"""Auto-wrapped CLR namespaces: generated Python classes mirror CLR types and adapt Python values automatically.

Each CLR type gets a facade class whose constructors, methods and properties are real class attributes
with Python-facing signatures, so IDE completion can traverse ``Namespace.Type().Method().Property``.
"""

import importlib
import importlib.abc
import importlib.util
import inspect
import os
import re
import sys
import types
from datetime import datetime, timedelta

import clr
import numpy as np
import pandas as pd
import System
from System import Nullable, Object
from System.Reflection import BindingFlags

from . import clrinfo
from .conversion import _ClrProxy, _keyword, _plan, _value_from_clr, _value_to_clr, wrap

_CLR_MODULE = type(System)
_FACADES = {}
_NAMESPACES = {}
_AUTO_NAMESPACES = set()
_DOMAIN_ASSEMBLIES = set()
_DOMAIN_TYPES = {}
_RUNTIME_TYPES = {
    "int": int, "float": float, "str": str, "bool": bool, "datetime": datetime, "timedelta": timedelta,
    "ndarray": np.ndarray, "DataFrame": pd.DataFrame, "list": list, "dict": dict, "tuple": tuple,
}
# Drop finders left by a previous copy of this module (e.g. after an IDE module reload).
sys.meta_path[:] = [finder for finder in sys.meta_path if type(finder).__module__ != __name__]


def unwrap(value):
    """Return the CLR object or class behind an auto-wrapped value (element-wise for tuples); others unchanged."""
    if isinstance(value, _ClrProxy):
        return value._target
    if isinstance(value, _AutoType):
        return value.__clr_class__
    if isinstance(value, tuple):
        return tuple(unwrap(item) for item in value)
    return value


def _wrappable(clr_type) -> bool:
    return not (clr_type.IsEnum or clrinfo.is_delegate(clr_type))


def _auto(value):
    """Facade CLR classes and objects, recursively inside lists, tuples and dicts; enums and Python values pass through."""
    if isinstance(value, (_ClrProxy, _AutoType, _AutoMethod)):
        return value
    if isinstance(value, list):
        return [_auto(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_auto(item) for item in value)
    if isinstance(value, dict):
        return {_auto(key): _auto(item) for key, item in value.items()}
    if isinstance(value, type):
        if issubclass(value, Object) and _wrappable(clr_type := clr.GetClrType(value)):
            return _facade(clr_type, value)
        return value
    if isinstance(value, Object):
        # pythonnet exposes objects as their declared type (e.g. an interface), so mirror that type.
        python_class = type(value)
        clr_type = clr.GetClrType(python_class)
        if _wrappable(clr_type):
            return _adopt(_facade(clr_type, python_class), value)
    return value


def _adopt(facade, target):
    instance = object.__new__(facade)
    object.__setattr__(instance, "_target", target)
    object.__setattr__(instance, "_methods", {})
    return instance


def _member_type(clr_type, name):
    prop = clr_type.GetProperty(name)
    if prop is not None:
        return prop.PropertyType
    field = clr_type.GetField(name)
    return None if field is None else field.FieldType


def _assign(target, clr_type, name, value):
    member_type = _member_type(clr_type, name)
    plan = None if member_type is None else _plan(value, member_type)
    setattr(target, name, _value_to_clr(value) if plan is None else plan.convert())


class _AutoMethod:
    """CLR method whose arguments are adapted and whose results are converted and proxied; ``[T]`` binds generics."""

    def __init__(self, method, declaring_type=None):
        self._method = method
        self._declaring_type = declaring_type
        self._call = wrap(method, declaring_type=declaring_type)
        self.__name__ = self._call.__name__
        self.__doc__ = self._call.__doc__

    def __call__(self, *args, **kwargs):
        return _auto(self._call(*args, **kwargs))

    def __getitem__(self, key):
        return _AutoMethod(self._method[unwrap(key)], self._declaring_type)

    def __getattr__(self, name):
        if name in ("_method", "_call", "_declaring_type"):
            raise AttributeError(name)
        return getattr(self._method, name)

    def __repr__(self):
        return f"<pandasnet auto-wrapped method {self.__name__}>"


# --- Facade classes -----------------------------------------------------------------------------


class _Hint(str):
    """Annotation text shown verbatim in signatures (e.g. ``Iterable[datetime] | DatetimeIndex``)."""

    __slots__ = ()

    def __repr__(self):
        return str(self)


class _AutoType(type):
    """Metaclass of facade classes: lazy CLR class lookup, static member assignment, generics and isinstance."""

    @property
    def __clr_class__(cls):
        python_class = cls.__dict__["_python_class"]
        if python_class is None:
            python_class = _python_class(cls.__clr_type__)
            type.__setattr__(cls, "_python_class", python_class)
        return python_class

    def __getattr__(cls, name):
        if name.startswith("__") or name == "_python_class":
            raise AttributeError(name)
        member = getattr(cls.__clr_class__, name)
        if isinstance(member, type):
            return _auto(member)
        if callable(member):
            return _AutoMethod(member, cls.__clr_type__)
        return _auto(_value_from_clr(member))

    def __setattr__(cls, name, value):
        if isinstance(cls.__dict__.get(name), _StaticMember):
            _assign(cls.__clr_class__, cls.__clr_type__, name, value)
        else:
            type.__setattr__(cls, name, value)

    def __getitem__(cls, key):
        return _auto(cls.__clr_class__[unwrap(key)])

    def __instancecheck__(cls, instance):
        return cls.__clr_type__.IsInstanceOfType(unwrap(instance))


class _AutoObject(_ClrProxy):
    """Base of facade instances: wraps one CLR object; unknown members fall back to pythonnet."""

    __slots__ = ()

    def __new__(cls, *args, **kwargs):
        constructor = cls.__dict__.get("_constructor")
        if constructor is None:
            clr_type = cls.__clr_type__
            if clr_type.IsInterface or clr_type.IsAbstract:
                kind = _kind(clr_type)
                names = ", ".join(_qualname(t) for t in clrinfo.implementations(clr_type, _DOMAIN_TYPES.values()))
                raise TypeError(f"{cls.__qualname__} is a .NET {kind} and cannot be created" + (f"; use one of: {names}" if names else ""))
            constructor = wrap(cls.__clr_class__)
            type.__setattr__(cls, "_constructor", constructor)
        return _auto(constructor(*args, **kwargs))

    def __init__(self, *args, **kwargs):
        pass

    @classmethod
    def input_schema(cls) -> pd.DataFrame:
        """Constructor arguments: one row each with its Python type, whether it is required, and its default."""
        from .frames import input_schema

        return input_schema(cls)

    @classmethod
    def template_frame(cls, rows: int = 0, overload: int | None = None) -> pd.DataFrame:
        """Typed DataFrame with one column per constructor argument (defaults pre-filled) to fill and pass to from_frame."""
        from .frames import template_frame

        return template_frame(cls, rows, overload)

    @classmethod
    def from_frame(cls, frame: pd.DataFrame, overload: int | None = None) -> list:
        """One object per row, matching columns to constructor arguments; all rows are validated first."""
        from .frames import from_frame

        return from_frame(cls, frame, overload)

    @classmethod
    def ask(cls, overload: int | None = None):
        """Create one object by answering a prompt per constructor argument (type, hint and default shown)."""
        from .interactive import _caller_namespace, ask

        return ask(cls, overload=overload, namespace=_caller_namespace(1))

    def __getattr__(self, name):
        if name in _ClrProxy.__slots__:
            raise AttributeError(name)
        member = getattr(self._target, name)
        if isinstance(member, type):
            return _auto(member)
        if not callable(member):
            return _auto(_value_from_clr(member))
        methods = self._methods
        if name not in methods:
            methods[name] = _AutoMethod(member, self.__clr_type__)
        return methods[name]

    def __setattr__(self, name, value):
        descriptor = type(self).__dict__.get(name)
        if isinstance(descriptor, _ClrProperty) and not descriptor.settable:
            raise AttributeError(descriptor.usage)
        _assign(self._target, self.__clr_type__, name, value)

    def __eq__(self, other):
        return self._target == unwrap(other)

    def __hash__(self):
        return hash(self._target)

    def __str__(self):
        return str(self._target)

    def __repr__(self):
        name = f"{type(self).__module__}.{type(self).__qualname__}"
        text = str(self._target)
        return f"<{name}>" if text == self.__clr_type__.ToString() else f"<{name}: {text}>"


class _Iterable:
    __slots__ = ()

    def __iter__(self):
        for item in self._target:
            yield _auto(_value_from_clr(item))


class _Sized:
    __slots__ = ()

    def __len__(self):
        return self._target.Count


def _get_item(instance, key):
    return _auto(_value_from_clr(instance._target[unwrap(key)]))


def _set_item(instance, key, value):
    instance._target[unwrap(key)] = _value_to_clr(value)


class _StaticMember:
    """Static CLR property or field, read and converted on access."""

    def __init__(self, name, doc):
        self._name = name
        self.__doc__ = doc

    def __get__(self, instance, owner):
        return _auto(_value_from_clr(getattr(owner.__clr_class__, self._name)))


class _ClrProperty(property):
    """Instance property; read on the class it explains its use instead of failing obscurely."""

    def __call__(self, *args, **kwargs):
        raise TypeError(self.usage)

    def __repr__(self):
        return f"<property {self.__doc__}>"


class _LazyMember:
    """Class member resolved through pythonnet on access (generic methods, nested enums)."""

    def __init__(self, name, doc):
        self._name = name
        self.__doc__ = doc

    def __get__(self, instance, owner):
        member = getattr(owner.__clr_class__ if instance is None else instance._target, self._name)
        if isinstance(member, type):
            return _auto(member)
        return _AutoMethod(member, owner.__clr_type__) if callable(member) else _auto(_value_from_clr(member))


def _python_class(clr_type):
    """The pythonnet class for a CLR type, found through its namespace module."""
    if clr_type.IsNested:
        return getattr(_python_class(clr_type.DeclaringType), clr_type.Name.split("`")[0])
    module = _NAMESPACES.get(clr_type.Namespace) or importlib.import_module(clr_type.Namespace)
    python_class = getattr(getattr(module, "__clr_module__", module), clr_type.Name.split("`")[0])
    if clr_type.IsGenericType and not clr_type.IsGenericTypeDefinition:
        python_class = python_class[tuple(_python_class(argument) for argument in clr_type.GetGenericArguments())]
    return python_class


def _is_domain(clr_type) -> bool:
    return (
        not (clr_type.IsGenericParameter or clr_type.IsArray or clr_type.IsByRef or clr_type.IsPointer)
        and clr_type.Assembly is not None
        and clr_type.Assembly.FullName in _DOMAIN_ASSEMBLIES
    )


def _qualname(clr_type) -> str:
    name = clr_type.Name.split("`")[0]
    return f"{_qualname(clr_type.DeclaringType)}.{name}" if clr_type.IsNested else name


def _annotation(clr_type, text):
    """Real Python type for results declared as clr_type, so IDEs can infer what a call returns."""
    head = text.split(" | ")[0].split("[")[0]
    if head in _RUNTIME_TYPES:
        return _RUNTIME_TYPES[head]
    underlying = Nullable.GetUnderlyingType(clr_type) or clr_type
    if _is_domain(underlying) and _wrappable(underlying) and head == _qualname(underlying):
        return _facade(underlying)
    return None


def _signature(overload, self_parameter: bool):
    parameters = [inspect.Parameter("self", inspect.Parameter.POSITIONAL_OR_KEYWORD)] if self_parameter else []
    for parameter in overload.parameters:
        name = "self_" if self_parameter and parameter.name == "self" else parameter.name
        hint = _Hint(clrinfo.param_hint(parameter.clr_type, _qualname))
        parameters.append(
            inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=parameter.default, annotation=hint)
        )
    if overload.return_type is None:
        return inspect.Signature(parameters)
    return inspect.Signature(parameters, return_annotation=_Hint(clrinfo.result_hint(overload.return_type, _qualname)))


def _overloads_doc(name, overloads) -> str:
    return "\n".join(
        f"{name}{_signature(overload, False)}\n    .NET: {overload.clr_signature}" for overload in overloads
    )


def _compile(source, name, qualname, module, namespace):
    scope = {}
    exec(compile(source, f"<pandasnet {module}.{qualname}>", "exec"), namespace, scope)
    function = scope["function"]
    function.__name__, function.__qualname__, function.__module__ = name, qualname, module
    return function


def _call(instance, name, args, kwargs):
    methods = instance._methods
    method = methods.get(name)
    if method is None:
        method = methods[name] = wrap(getattr(instance._target, name), declaring_type=instance.__clr_type__)
    return _auto(method(*args, **kwargs))


def _call_static(facade, name, args, kwargs):
    calls = facade.__dict__["_static_calls"]
    method = calls.get(name)
    if method is None:
        method = calls[name] = wrap(getattr(facade.__clr_class__, name), declaring_type=facade.__clr_type__)
    return _auto(method(*args, **kwargs))


def _get(instance, name):
    return _auto(_value_from_clr(getattr(instance._target, name)))


def _method(facade, name, static, overloads):
    # Generated without a source file so IDEs read __signature__/__annotations__ instead of the source.
    qualname = f"{facade.__qualname__}.{name}"
    if static:
        source = "def function(*args, **kwargs):\n    return _call_static(_facade, _name, args, kwargs)\n"
        scope = {"_call_static": _call_static, "_facade": facade, "_name": name}
    else:
        source = "def function(self, *args, **kwargs):\n    return _call(self, _name, args, kwargs)\n"
        scope = {"_call": _call, "_name": name}
    function = _compile(source, name, qualname, facade.__module__, scope)
    primary = max(overloads, key=lambda overload: len(overload.parameters))
    function.__signature__ = _signature(primary, not static)
    function.__doc__ = _overloads_doc(name, overloads)
    annotation = _annotation(primary.return_type, str(function.__signature__.return_annotation))
    function.__annotations__ = {} if annotation is None else {"return": annotation}
    function.__clr_owner__, function.__clr_name__ = facade, name
    return staticmethod(function) if static else function


def _property(facade, member, constructors):
    text = clrinfo.result_hint(member.clr_type, _qualname)
    owner = facade.__qualname__
    parameter = next(
        (p.name for overload in constructors for p in overload.parameters if _keyword(p.name) == _keyword(member.name)),
        None,
    )
    doc = f"{member.name}: {text}"
    usage = f"{owner}.{member.name} is a property of {owner} objects, not a method. Read it with obj.{member.name}"
    if member.writable:
        doc += f"  (settable: {clrinfo.param_hint(member.clr_type, _qualname)})"
        usage += f" and set it with obj.{member.name} = value."
    elif parameter is not None:
        doc += f"  (read-only; set with {owner}(..., {parameter}=...))"
        usage += f"; it is read-only, so set it when creating the object: {owner}(..., {parameter}=...)."
    else:
        doc += "  (read-only)"
        usage += "; it is read-only."
    if member.static:
        return _StaticMember(member.name, doc)
    source = "def function(self):\n    return _get(self, _name)\n"
    getter = _compile(source, member.name, f"{owner}.{member.name}", facade.__module__, {"_get": _get, "_name": member.name})
    annotation = _annotation(member.clr_type, text)
    getter.__annotations__ = {} if annotation is None else {"return": annotation}
    prop = _ClrProperty(getter, doc=doc)
    prop.settable, prop.usage = member.writable, usage
    return prop


def _indexer(facade, index_types, value_type):
    text = clrinfo.result_hint(value_type, _qualname)
    source = "def function(self, key):\n    return _get_item(self, key)\n"
    getter = _compile(source, "__getitem__", f"{facade.__qualname__}.__getitem__", facade.__module__, {"_get_item": _get_item})
    key = inspect.Parameter("key", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=_Hint(clrinfo.param_hint(index_types[0], _qualname)))
    self = inspect.Parameter("self", inspect.Parameter.POSITIONAL_OR_KEYWORD)
    getter.__signature__ = inspect.Signature([self, key], return_annotation=_Hint(text))
    annotation = _annotation(value_type, text)
    getter.__annotations__ = {} if annotation is None else {"return": annotation}
    return getter


def _kind(clr_type) -> str:
    if clr_type.IsInterface:
        return "interface"
    if clr_type.IsValueType:
        return "struct"
    if clr_type.IsAbstract:
        return "static class" if clr_type.IsSealed else "abstract class"
    return "class"


def _type_doc(clr_type, constructors) -> str:
    sections = [f".NET {_kind(clr_type)} {clr_type.FullName}"]
    if clr_type.IsInterface or (clr_type.IsAbstract and not clr_type.IsSealed):
        implementations = [_qualname(t) for t in clrinfo.implementations(clr_type, _DOMAIN_TYPES.values())]
        text = "Cannot be created directly."
        if implementations:
            text += " Pass an instance of one of:\n" + "\n".join(f"  {name}" for name in implementations)
        sections.append(text)
    if constructors:
        sections.append("Constructors:\n" + _overloads_doc(_qualname(clr_type), constructors))
    properties = [
        f"  {member.name}: {clrinfo.result_hint(member.clr_type, _qualname)}" + ("" if member.writable else "  (read-only)")
        for member in clrinfo.members(clr_type)
        if not member.name.startswith("_")
    ]
    if properties:
        sections.append("Properties:\n" + "\n".join(properties))
    methods = []
    for name, (static, _, overloads) in clrinfo.methods(clr_type).items():
        primary = max(overloads, key=lambda overload: len(overload.parameters))
        prefix = "static " if static else ""
        more = f"  (+{len(overloads) - 1} overloads)" if len(overloads) > 1 else ""
        methods.append(f"  {prefix}{name}{_signature(primary, False)}{more}")
    if methods:
        sections.append("Methods:\n" + "\n".join(methods))
    return "\n\n".join(sections)


def _facade(clr_type, python_class=None):
    """The facade class mirroring a CLR type, created (with all public members) on first use."""
    key = clr_type.AssemblyQualifiedName or clr_type.ToString()
    facade = _FACADES.get(key)
    if facade is not None:
        if python_class is not None and facade.__dict__["_python_class"] is None:
            type.__setattr__(facade, "_python_class", python_class)
        return facade

    bases = []
    if clrinfo.element_type(clr_type) is not None:
        bases.append(_Iterable)
    if clrinfo.count_property(clr_type):
        bases.append(_Sized)
    name = clr_type.Name.split("`")[0]
    namespace = {
        "__slots__": (),
        "__module__": clr_type.Namespace or "",
        "__qualname__": _qualname(clr_type),
        "__clr_type__": clr_type,
        "_python_class": python_class,
        "_static_calls": {},
    }
    # Jedi names constructor signatures after the metaclass, so each facade gets its own.
    metaclass = type(name, (_AutoType,), {"__module__": __name__})
    facade = metaclass(name, (*bases, _AutoObject), namespace)
    _FACADES[key] = facade

    indexer = clrinfo.indexer(clr_type)
    if indexer is not None:
        index_types, value_type, writable = indexer
        type.__setattr__(facade, "__getitem__", _indexer(facade, index_types, value_type))
        if writable:
            type.__setattr__(facade, "__setitem__", _set_item)
    constructors = clrinfo.constructors(clr_type)
    if constructors:
        primary = max(constructors, key=lambda overload: len(overload.parameters))
        type.__setattr__(facade, "__signature__", _signature(primary, False))
    type.__setattr__(facade, "__doc__", _type_doc(clr_type, constructors))
    for member in clrinfo.members(clr_type):
        if not member.name.startswith("_") and member.name not in facade.__dict__:
            type.__setattr__(facade, member.name, _property(facade, member, constructors))
    for name, (static, generic, overloads) in clrinfo.methods(clr_type).items():
        if name.startswith("_") or name in facade.__dict__:
            continue
        if generic:
            type.__setattr__(facade, name, _LazyMember(name, _overloads_doc(name, overloads)))
        else:
            type.__setattr__(facade, name, _method(facade, name, static, overloads))
    for nested in clr_type.GetNestedTypes(BindingFlags.Public):
        name = nested.Name.split("`")[0]
        if name in facade.__dict__:
            continue
        if _wrappable(nested) and not nested.IsGenericTypeDefinition:
            type.__setattr__(facade, name, _facade(nested))
        else:
            type.__setattr__(facade, name, _LazyMember(name, f".NET {nested.FullName}"))
    return facade


# --- Namespaces ---------------------------------------------------------------------------------


class _Namespace(types.ModuleType):
    """CLR namespace module listing its types (as facade classes) and sub-namespaces up front."""

    def __init__(self, module):
        super().__init__(module.__name__)
        self.__path__ = []
        self.__clr_module__ = module

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        value = getattr(self.__clr_module__, name)
        value = _namespace_for(value) if isinstance(value, _CLR_MODULE) else _auto(value)
        setattr(self, name, value)
        return value

    def __dir__(self):
        return sorted(set(super().__dir__()) | set(dir(self.__clr_module__)))

    def __repr__(self):
        return f"<pandasnet auto-wrapped CLR namespace {self.__name__!r}>"


def _namespace_for(module):
    """The single auto-wrapped namespace for a pythonnet namespace module, populated on creation."""
    namespace = _NAMESPACES.get(module.__name__)
    if namespace is not None:
        return namespace
    namespace = _NAMESPACES[module.__name__] = _Namespace(module)
    # pythonnet's __all__ lists the namespace's public types (sub-namespaces are listed separately).
    classes = {}
    for name in getattr(module, "__all__", ()):
        if "`" in name:
            continue  # .NET's generic arity name (Box`1); pythonnet also lists Box, used as Box[T]
        try:
            classes[name] = getattr(module, name)
        except AttributeError:
            continue
    for value in classes.values():
        if isinstance(value, type) and issubclass(value, Object):
            clr_type = clr.GetClrType(value)
            _DOMAIN_ASSEMBLIES.add(clr_type.Assembly.FullName)
            _DOMAIN_TYPES.setdefault(clr_type.FullName, clr_type)
    for name, value in classes.items():
        namespace.__dict__.setdefault(name, _auto(value))
    prefix = module.__name__ + "."
    for full_name in sorted(getattr(clr, "_available_namespaces", ())):
        child = full_name[len(prefix) :]
        if full_name.startswith(prefix) and "." not in child and child not in namespace.__dict__:
            namespace.__dict__[child] = _namespace_for(getattr(module, child))
    return namespace


def _reference(assembly, namespace):
    """Add an assembly reference; return it and the namespace to wrap (default: its exported types' common root)."""
    loaded = clr.AddReference(os.fspath(assembly))
    _DOMAIN_ASSEMBLIES.add(loaded.FullName)
    _DOMAIN_TYPES.update((clr_type.FullName, clr_type) for clr_type in loaded.GetExportedTypes())
    if namespace is not None:
        return loaded, namespace
    return loaded, _root_namespace(loaded)


def _root_namespace(loaded) -> str:
    """The assembly's own root namespace: the common root of its types, else the one named after the assembly."""
    names = {clr_type.Namespace for clr_type in loaded.GetExportedTypes() if clr_type.Namespace}
    common = os.path.commonprefix([name.split(".") for name in names]) if names else []
    if common:
        return ".".join(common)
    roots = {}
    for name in names:
        root = name.split(".")[0]
        roots[root] = roots.get(root, 0) + 1
    # Visual Studio's default root namespace is the assembly name with invalid characters as "_".
    default = re.sub(r"[^0-9A-Za-z_.]", "_", loaded.GetName().Name)
    if default in roots:
        return default
    choices = ", ".join(f"{root!r} ({count} namespaces)" for root, count in sorted(roots.items(), key=lambda item: -item[1]))
    raise ValueError(f"{loaded.GetName().Name} has several root namespaces; pass namespace= one of: {choices}")


def _namespace(name):
    module = importlib.import_module(name)
    if isinstance(module, _Namespace):
        return module
    if not isinstance(module, _CLR_MODULE):
        raise ImportError(f"{name!r} resolved to a Python module, not a CLR namespace")
    return _namespace_for(module)


def _refresh_stubs(loaded, namespace, stubs):
    """stubs: True/False, an output folder, or None to follow PANDASNET_STUBS (default on)."""
    if stubs is None:
        stubs = os.environ.get("PANDASNET_STUBS", "1").strip().lower() not in ("0", "false", "no", "off")
    if stubs is False:
        return
    from .stubs import refresh_stubs

    refresh_stubs(loaded, namespace, None if stubs is True else stubs)


def load(assembly, namespace=None, stubs=None) -> types.ModuleType:
    """Reference a .NET assembly and return its namespace with every type auto-wrapped.

    ``assembly`` is a DLL path or assembly name; ``namespace`` defaults to the common root
    namespace. Every type is a Python class with real constructors, methods and properties, so
    IDE completion and ``help()`` work on ``Namespace.Type().Method()`` chains. Arguments accept plain
    Python/NumPy/pandas values and results come back converted; CLR objects come back as instances of
    these classes (use :func:`unwrap` for the raw object). Imports elsewhere are unaffected.

    Editor stubs (see :func:`generate_stubs`) are refreshed when the assembly build changed; pass
    ``stubs=False`` (or set ``PANDASNET_STUBS=0``) to skip that, or a folder to write them there.

    Example::

        MyLib = pandasnet.load(r"C:\\libs\\MyLib.dll")
        result = MyLib.Engine().Run(items, matrix, settings)
    """

    loaded, namespace = _reference(assembly, namespace)
    module = _namespace(namespace)
    _refresh_stubs(loaded, namespace, stubs)
    return module


def _is_auto(name):
    return any(name == root or name.startswith(root + ".") for root in _AUTO_NAMESPACES)


class _Loader(importlib.abc.Loader):
    def __init__(self, spec):
        self._spec = spec

    def create_module(self, spec):
        module = importlib.util.module_from_spec(self._spec)
        self._spec.loader.exec_module(module)
        if not isinstance(module, _CLR_MODULE):
            raise ImportError(f"{spec.name!r} resolved to a Python module, not a CLR namespace")
        return _namespace_for(module)

    def exec_module(self, module):
        pass


class _Finder(importlib.abc.MetaPathFinder):
    """Serve registered CLR namespaces as auto-wrapped modules, delegating discovery to the other finders."""

    def find_spec(self, fullname, path, target=None):
        if not _is_auto(fullname):
            return None
        for finder in sys.meta_path:
            find_spec = getattr(finder, "find_spec", None)
            if finder is self or find_spec is None:
                continue
            spec = find_spec(fullname, path, target)
            if spec is not None:
                if spec.loader is None:
                    return None
                return importlib.util.spec_from_loader(fullname, _Loader(spec), is_package=True)
        return None


def add_reference(assembly, namespace=None, stubs=None) -> types.ModuleType:
    """Like ``clr.AddReference``, but imports from the assembly's namespace are auto-wrapped.

    After ``pandasnet.add_reference(r"C:\\libs\\MyLib.dll")``, ``from MyLib import Engine``
    (and sub-namespaces such as ``from MyLib.Models import ...``) yields auto-wrapped types; see
    :func:`load` (including ``stubs``). Returns the wrapped namespace.
    """

    loaded, namespace = _reference(assembly, namespace)
    _AUTO_NAMESPACES.add(namespace)
    if not any(isinstance(finder, _Finder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _Finder())
    for name, module in list(sys.modules.items()):
        if _is_auto(name) and isinstance(module, _CLR_MODULE):
            sys.modules[name] = _namespace_for(module)
    module = _namespace(namespace)
    _refresh_stubs(loaded, namespace, stubs)
    return module
