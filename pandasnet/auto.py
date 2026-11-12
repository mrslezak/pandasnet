"""Auto-wrapped CLR namespaces: types, constructors, methods and properties adapt Python values automatically."""

import importlib
import importlib.abc
import importlib.util
import os
import sys
import types

import clr
import System
from System import Object

from .conversion import _ClrProxy, _plan, _value_from_clr, _value_to_clr, wrap

_CLR_MODULE = type(System)
_TYPE_PROXIES = {}
_AUTO_NAMESPACES = set()
# Drop finders left by a previous copy of this module (e.g. after an IDE module reload).
sys.meta_path[:] = [finder for finder in sys.meta_path if type(finder).__module__ != __name__]


def unwrap(value):
    """Return the CLR object behind an auto-wrapped proxy (element-wise for tuples); other values unchanged."""
    if isinstance(value, _ClrProxy):
        return value._target
    if isinstance(value, tuple):
        return tuple(unwrap(item) for item in value)
    return value


def _auto(value):
    """Proxy CLR types and objects, recursively inside lists, tuples and dicts; enums and Python values pass through."""
    if isinstance(value, (_ClrProxy, _AutoMethod)):
        return value
    if isinstance(value, list):
        return [_auto(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_auto(item) for item in value)
    if isinstance(value, dict):
        return {_auto(key): _auto(item) for key, item in value.items()}
    if isinstance(value, type):
        if not issubclass(value, Object) or clr.GetClrType(value).IsEnum:
            return value
        proxy = _TYPE_PROXIES.get(value)
        if proxy is None:
            proxy = _TYPE_PROXIES[value] = _AutoProxy(value)
        return proxy
    if isinstance(value, Object) and not value.GetType().IsEnum:
        return _AutoProxy(value)
    return value


def _member_type(clr_type, name):
    prop = clr_type.GetProperty(name)
    if prop is not None:
        return prop.PropertyType
    field = clr_type.GetField(name)
    return None if field is None else field.FieldType


class _AutoMethod:
    """CLR method whose arguments are adapted and whose results are converted and proxied; ``[T]`` binds generics."""

    def __init__(self, method):
        self._method = method
        self._call = wrap(method)
        self.__name__ = self._call.__name__
        self.__doc__ = self._call.__doc__

    def __call__(self, *args, **kwargs):
        return _auto(self._call(*args, **kwargs))

    def __getitem__(self, key):
        return _AutoMethod(self._method[unwrap(key)])

    def __getattr__(self, name):
        if name in ("_method", "_call"):
            raise AttributeError(name)
        return getattr(self._method, name)

    def __repr__(self):
        return f"<pandasnet auto-wrapped method {self.__name__}>"


class _AutoProxy(_ClrProxy):
    """CLR type or object whose members, constructor, indexer and iteration are auto-wrapped."""

    __slots__ = ()

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
            methods[name] = _AutoMethod(member)
        return methods[name]

    def __setattr__(self, name, value):
        target = self._target
        clr_type = clr.GetClrType(target) if isinstance(target, type) else target.GetType()
        member_type = _member_type(clr_type, name)
        plan = None if member_type is None else _plan(value, member_type)
        setattr(target, name, _value_to_clr(value) if plan is None else plan.convert())

    def __call__(self, *args, **kwargs):
        call = self._methods.get(None)
        if call is None:
            call = self._methods[None] = wrap(self._target)
        return _auto(call(*args, **kwargs))

    def __getitem__(self, key):
        target = self._target
        if isinstance(target, type):
            return _auto(target[unwrap(key)])
        return _auto(_value_from_clr(target[unwrap(key)]))

    def __setitem__(self, key, value):
        self._target[unwrap(key)] = _value_to_clr(value)

    def __iter__(self):
        for item in self._target:
            yield _auto(_value_from_clr(item))

    def __len__(self):
        return len(self._target)

    def __bool__(self):
        return bool(self._target)

    def __eq__(self, other):
        return self._target == unwrap(other)

    def __hash__(self):
        return hash(self._target)

    def __str__(self):
        return str(self._target)

    def __instancecheck__(self, instance):
        return isinstance(self._target, type) and isinstance(unwrap(instance), self._target)


class _Namespace(types.ModuleType):
    """CLR namespace module whose types and sub-namespaces are auto-wrapped."""

    def __init__(self, module):
        super().__init__(module.__name__)
        self.__path__ = []
        self.__clr_module__ = module

    def __getattr__(self, name):
        if name == "__clr_module__":
            raise AttributeError(name)
        value = getattr(self.__clr_module__, name)
        value = _Namespace(value) if isinstance(value, _CLR_MODULE) else _auto(value)
        setattr(self, name, value)
        return value

    def __dir__(self):
        return sorted(set(super().__dir__()) | set(dir(self.__clr_module__)))

    def __repr__(self):
        return f"<pandasnet auto-wrapped CLR namespace {self.__name__!r}>"


def _reference(assembly, namespace):
    """Add an assembly reference and return the namespace to wrap (default: its exported types' common root)."""
    loaded = clr.AddReference(os.fspath(assembly))
    if namespace is not None:
        return namespace
    paths = [name.split(".") for name in {clr_type.Namespace for clr_type in loaded.GetExportedTypes()} if name]
    common = os.path.commonprefix(paths) if paths else []
    if not common:
        raise ValueError(f"{loaded.GetName().Name} has no common root namespace; pass namespace=...")
    return ".".join(common)


def _namespace(name):
    module = importlib.import_module(name)
    if isinstance(module, _Namespace):
        return module
    if not isinstance(module, _CLR_MODULE):
        raise ImportError(f"{name!r} resolved to a Python module, not a CLR namespace")
    return _Namespace(module)


def load(assembly, namespace=None):
    """Reference a .NET assembly and return its namespace with every type auto-wrapped.

    ``assembly`` is a DLL path or assembly name; ``namespace`` defaults to the common root
    namespace of its exported types. Constructors, methods, properties and indexers accept plain
    Python/NumPy/pandas values and return converted results; CLR objects come back as proxies
    (use :func:`unwrap` for the raw object). Imports elsewhere are unaffected.

    Example::

        MyLib = pandasnet.load(r"C:\\libs\\MyLib.dll")
        result = MyLib.Engine().Run(items, matrix, settings)
    """

    return _namespace(_reference(assembly, namespace))


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
        return _Namespace(module)

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


def add_reference(assembly, namespace=None):
    """Like ``clr.AddReference``, but imports from the assembly's namespace are auto-wrapped.

    After ``pandasnet.add_reference(r"C:\\libs\\MyLib.dll")``, ``from MyLib import Engine``
    (and sub-namespaces such as ``from MyLib.Models import ...``) yields auto-wrapped types; see
    :func:`load`. Returns the wrapped namespace.
    """

    namespace = _reference(assembly, namespace)
    _AUTO_NAMESPACES.add(namespace)
    if not any(isinstance(finder, _Finder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _Finder())
    for name, module in list(sys.modules.items()):
        if _is_auto(name) and isinstance(module, _CLR_MODULE):
            sys.modules[name] = _Namespace(module)
    return _namespace(namespace)
