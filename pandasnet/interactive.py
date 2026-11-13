"""Interactive construction of .NET objects and calls: prompt for each argument with its type and a hint."""

import builtins
import inspect
import re
import sys
from datetime import datetime

import numpy as np
import pandas as pd
from System import Enum, Nullable

from . import clrinfo
from .conversion import _DICTIONARIES, _collection_target, _generic_interface, _plan

_SKIP = object()
_TRUE = {"y", "yes", "true", "t", "1"}
_FALSE = {"n", "no", "false", "f", "0"}
_INTEGERS = clrinfo._INTEGERS
_FLOATS = {"System.Double", "System.Single", "System.Decimal"}


class _Invalid(ValueError):
    pass


def _qualname(clr_type):
    from .auto import _qualname

    return _qualname(clr_type)


def _date_code(value: datetime) -> str:
    parts = [value.year, value.month, value.day]
    if (value.hour, value.minute, value.second, value.microsecond) != (0, 0, 0, 0):
        parts += [value.hour, value.minute, value.second]
    return f"datetime({', '.join(map(str, parts))})"


def _parse_scalar(text, clr_type):
    """(value, code) for one scalar typed as text; raises _Invalid with a hint."""
    name = clr_type.FullName
    if name in ("System.String",):
        return text, repr(text)
    if name == "System.Char":
        if len(text) != 1:
            raise _Invalid(f"{text!r} is not a single character")
        return text, repr(text)
    if name in _INTEGERS:
        try:
            value = int(text.replace("_", "").replace(",", ""))
        except ValueError:
            raise _Invalid(f"{text!r} is not a whole number; enter e.g. 1000") from None
        return value, str(value)
    if name in _FLOATS:
        try:
            value = float(text.replace("_", ""))
        except ValueError:
            raise _Invalid(f"{text!r} is not a number; enter e.g. 0.25") from None
        return value, repr(value)
    if name == "System.Boolean":
        if text.lower() in _TRUE:
            return True, "True"
        if text.lower() in _FALSE:
            return False, "False"
        raise _Invalid(f"{text!r} is not yes/no")
    if name == "System.DateTime":
        try:
            value = pd.Timestamp(text).to_pydatetime()
        except (ValueError, TypeError):
            raise _Invalid(f"{text!r} is not a date; enter e.g. 2026-12-31") from None
        return value, _date_code(value)
    if name == "System.TimeSpan":
        try:
            value = pd.Timedelta(text).to_pytimedelta()
        except (ValueError, TypeError):
            raise _Invalid(f"{text!r} is not a duration; enter e.g. 1 day or 2h") from None
        return value, repr(value).replace("datetime.", "")
    raise _Invalid(f"cannot type a {clr_type.Name} as text")


_SCALAR_HINTS = {
    "System.String": "text",
    "System.Char": "one character",
    "System.Boolean": "yes/no",
    "System.DateTime": "date, e.g. 2026-12-31",
    "System.TimeSpan": "duration, e.g. 1 day or 2h",
    **dict.fromkeys(_INTEGERS, "whole number, e.g. 1000"),
    **dict.fromkeys(_FLOATS, "number, e.g. 0.25"),
}


def _scalar(clr_type) -> bool:
    return clr_type.FullName in _SCALAR_HINTS


def _enum_names(clr_type):
    return [str(name) for name in Enum.GetNames(clr_type)]


def _default_text(default) -> str:
    if isinstance(default, clrinfo.EnumDefault):
        return default.member
    if default is None:
        return "none"
    if default is ...:
        return "default"
    return repr(default)


class _Session:
    """One interactive run; read/write are injectable for tests and notebooks."""

    def __init__(self, read, write, namespace):
        self.read = read
        self.write = write
        self.namespace = namespace
        self.setup = []
        self.taken = set()

    # --- Helpers -----------------------------------------------------------------------------

    def _variable(self, text, clr_type):
        """A caller variable named text whose value fits clr_type, else None."""
        if not text.isidentifier() or text not in self.namespace:
            return None
        value = self.namespace[text]
        return value if _plan(value, clr_type) is not None else None

    def _choose(self, prompt, count, pad):
        while True:
            text = self.read(prompt).strip()
            if not text:
                return 0
            if text.isdigit() and 0 <= int(text) < count:
                return int(text)
            self.write(f"{pad}  ! enter a number from 0 to {count - 1}")

    # --- Arguments ---------------------------------------------------------------------------

    def arguments(self, title, overloads, pad):
        """Choose an overload (if several) and prompt for each argument: (kwargs, code arguments)."""
        overload = overloads[0]
        if len(overloads) > 1:
            common = set.intersection(*({(p.name, p.clr_type.FullName) for p in o.parameters} for o in overloads))
            self.write(f"{pad}{title} can be called {len(overloads)} ways:")
            for index, candidate in enumerate(overloads):
                distinct = [p for p in candidate.parameters if (p.name, p.clr_type.FullName) not in common]
                shown = distinct or candidate.parameters
                text = ", ".join(f"{p.name}: {clrinfo.param_hint(p.clr_type, _qualname)}" for p in shown)
                self.write(f"{pad}  {index}: {'with ' if distinct else ''}{text}")
            overload = overloads[self._choose(f"{pad}Which one? [Enter = 0]: ", len(overloads), pad)]
        if overload.parameters:
            self.write(f"{pad}{title} (* = required, Enter = keep default):")
        kwargs, codes = {}, []
        for parameter in overload.parameters:
            optional = parameter.default is not inspect.Parameter.empty
            value, code = self.value(parameter.name, parameter.clr_type, optional, parameter.default, pad + "  ")
            if value is not _SKIP:
                kwargs[parameter.name] = value
                codes.append(f"{parameter.name}={code}")
        return kwargs, codes

    def value(self, label, clr_type, optional, default, pad):
        """Prompt until a valid value for clr_type is given: (value, code) or (_SKIP, None) to keep the default."""
        underlying = Nullable.GetUnderlyingType(clr_type)
        target = underlying or clr_type
        type_text = clrinfo.param_hint(clr_type, _qualname)
        star = "" if optional else "*"
        suffix = f" [Enter = {_default_text(default)}]" if optional else ""

        if target.IsEnum:
            names = _enum_names(target)
            self.write(f"{pad}{label}{star} ({type_text}) choose: " + ", ".join(f"{i}={n}" for i, n in enumerate(names)))
            while True:
                text = self.read(f"{pad}  > {label}{suffix}: ").strip()
                if not text and optional:
                    return _SKIP, None
                matches = [n for n in names if n.lower() == text.lower()]
                if text.isdigit() and int(text) < len(names):
                    matches = [names[int(text)]]
                if matches:
                    return matches[0], repr(matches[0])
                self.write(f"{pad}  ! enter a number 0-{len(names) - 1} or one of {', '.join(names)}")

        if _scalar(target):
            prompt = f"{pad}{label}{star} ({type_text}) {_SCALAR_HINTS[target.FullName]}{suffix}: "
            return self._loop(prompt, clr_type, optional, pad, lambda text: _parse_scalar(text, target))

        if target.IsArray and target.GetArrayRank() > 1:
            element = target.GetElementType()
            hint = "rows separated by ';', values by ',' (e.g. 1, 0.75; 0.75, 1), or a variable name"
            prompt = f"{pad}{label}{star} ({type_text}) {hint}{suffix}: "
            return self._loop(prompt, clr_type, optional, pad, lambda text: self._matrix(text, element))

        dictionary = _generic_interface(target, *_DICTIONARIES)
        if dictionary is not None:
            key_type, value_type = dictionary.GetGenericArguments()
            if _scalar(key_type) and _scalar(value_type):
                hint = "key=value pairs separated by ',' (e.g. a=1, b=2), or a variable name"
                prompt = f"{pad}{label}{star} ({type_text}) {hint}{suffix}: "
                return self._loop(prompt, clr_type, optional, pad, lambda text: self._mapping(text, key_type, value_type))

        collection = _collection_target(target)
        if collection is not None:
            element = collection[0]
            if _scalar(element) or element.IsEnum:
                example = {"System.DateTime": "2026-01-05, 2026-01-12"}.get(element.FullName, "1, 2.5")
                hint = f"values separated by ',' (e.g. {example}), or a variable name"
                prompt = f"{pad}{label}{star} ({type_text}) {hint}{suffix}: "
                return self._loop(prompt, clr_type, optional, pad, lambda text: self._list(text, element))
            return self._objects(label, clr_type, element, optional, suffix, type_text, pad)

        if clrinfo.is_delegate(target) or not _constructible(target):
            prompt = f"{pad}{label}{star} ({type_text}) name of a variable holding it{suffix}: "
            return self._loop(prompt, clr_type, optional, pad, None)

        return self._object(label, clr_type, optional, suffix, type_text, pad)

    def _loop(self, prompt, clr_type, optional, pad, parse):
        while True:
            text = self.read(prompt).strip()
            if not text:
                if optional:
                    return _SKIP, None
                self.write(f"{pad}  ! required: please enter a value")
                continue
            variable = self._variable(text, clr_type)
            if variable is not None:
                return variable, text
            if parse is None:
                self.write(f"{pad}  ! no variable named {text!r} with a suitable value")
                continue
            try:
                value, code = parse(text)
            except _Invalid as error:
                self.write(f"{pad}  ! {error}")
                continue
            if _plan(value, clr_type) is None:
                self.write(f"{pad}  ! {text!r} does not fit {clrinfo.param_hint(clr_type, _qualname)}")
                continue
            if isinstance(value, datetime) and text != value.strftime("%Y-%m-%d"):
                self.write(f"{pad}  = {value:%Y-%m-%d %H:%M}")
            return value, code

    def _list(self, text, element):
        values, codes = [], []
        for part in (piece.strip() for piece in text.replace(";", ",").split(",")):
            if not part:
                continue
            if element.IsEnum:
                names = {name.lower(): name for name in _enum_names(element)}
                if part.lower() not in names:
                    raise _Invalid(f"{part!r} is not one of {', '.join(names.values())}")
                value, code = names[part.lower()], repr(names[part.lower()])
            else:
                value, code = _parse_scalar(part, element)
            values.append(value)
            codes.append(code)
        if not values:
            raise _Invalid("enter at least one value")
        return values, f"[{', '.join(codes)}]"

    def _matrix(self, text, element):
        rows = [[_parse_scalar(cell.strip(), element)[0] for cell in row.split(",") if cell.strip()] for row in text.split(";")]
        rows = [row for row in rows if row]
        if not rows or len({len(row) for row in rows}) != 1:
            raise _Invalid("every row needs the same number of values, e.g. 1, 0.75; 0.75, 1")
        matrix = np.array(rows)
        return matrix, f"np.array({matrix.tolist()!r})"

    def _mapping(self, text, key_type, value_type):
        values, codes = {}, []
        for pair in (piece.strip() for piece in text.split(",")):
            if not pair:
                continue
            if "=" not in pair:
                raise _Invalid(f"{pair!r} is not key=value")
            key_text, value_text = (side.strip() for side in pair.split("=", 1))
            key, key_code = _parse_scalar(key_text, key_type)
            value, value_code = _parse_scalar(value_text, value_type)
            values[key] = value
            codes.append(f"{key_code}: {value_code}")
        return values, "{" + ", ".join(codes) + "}"

    def _object(self, label, clr_type, optional, suffix, type_text, pad):
        target = Nullable.GetUnderlyingType(clr_type) or clr_type
        how = "variable name, or 'new' to create one" if optional else "variable name, or Enter to create one"
        prompt = f"{pad}{label}{_star(optional)} ({type_text}) {how}{suffix}: "
        while True:
            text = self.read(prompt).strip()
            if not text and optional:
                return _SKIP, None
            if not text or (optional and text.lower() == "new"):
                return self.create(target, pad + "  ")
            variable = self._variable(text, clr_type)
            if variable is not None:
                return variable, text
            self.write(f"{pad}  ! no variable named {text!r} holding a {type_text}")

    def _objects(self, label, clr_type, element, optional, suffix, type_text, pad):
        prompt = f"{pad}{label}{_star(optional)} ({type_text}) variable name, or how many to create{suffix}: "
        while True:
            text = self.read(prompt).strip()
            if not text and optional:
                return _SKIP, None
            variable = self._variable(text, clr_type)
            if variable is not None:
                return variable, text
            if text.isdigit() and int(text) > 0:
                items = [self.create(element, pad + "  ", f"{label}[{index}]") for index in range(int(text))]
                return [item for item, _ in items], f"[{', '.join(code for _, code in items)}]"
            self.write(f"{pad}  ! enter a variable name or a number of items, e.g. 2")

    # --- Objects and calls -------------------------------------------------------------------

    def create(self, clr_type, pad, label=None):
        """Build one object of clr_type (choosing an implementation for interfaces): (object, code)."""
        from .auto import _DOMAIN_TYPES, _facade

        if clr_type.IsInterface or clr_type.IsAbstract:
            implementations = clrinfo.implementations(clr_type, _DOMAIN_TYPES.values())
            if not implementations:
                raise TypeError(f"no known class implements {_qualname(clr_type)}")
            self.write(f"{pad}{label or _qualname(clr_type)} needs one of these {_qualname(clr_type)} types:")
            for index, implementation in enumerate(implementations):
                self.write(f"{pad}  {index}: {_qualname(implementation)}")
            clr_type = implementations[self._choose(f"{pad}Which one? [Enter = 0]: ", len(implementations), pad)]
        cls = _facade(clr_type)
        title = f"{label} = {cls.__qualname__}" if label else cls.__qualname__
        constructors = clrinfo.constructors(clr_type)
        created, code = self.attempt(title, constructors, cls, cls.__qualname__, pad)
        setters = _setup_methods(clr_type)
        if not setters or any(constructor.parameters for constructor in constructors):
            return created, code

        # Objects without constructor arguments are configured through methods such as Add(...).
        variable = self._variable_name(label or cls.__qualname__)
        calls = ", ".join(f"{name}({_signature_text(overloads[0])})" for name, overloads in setters)
        self.write(f"{pad}{cls.__qualname__} takes no constructor arguments; it is set up by calling {calls}")
        lines = [f"{variable} = {code}"]
        for name, overloads in setters:
            count = self._count(f"{pad}How many {name}(...) calls? [Enter = 0]: ", pad)
            for index in range(count):
                method = getattr(created, name)
                _, call = self.attempt(f"{variable}.{name} #{index + 1}", overloads, method, f"{variable}.{name}", pad + "  ")
                lines.append(call)
        self.setup.extend(lines)
        return created, variable

    def _count(self, prompt, pad):
        while True:
            text = self.read(prompt).strip()
            if not text:
                return 0
            if text.isdigit():
                return int(text)
            self.write(f"{pad}  ! enter a whole number, e.g. 2")

    def _variable_name(self, label):
        base = re.sub(r"\W", "_", label)
        base = base[0].lower() + base[1:] if base else "value"
        name, suffix = base, 2
        while name in self.taken or name in self.namespace:
            name, suffix = f"{base}{suffix}", suffix + 1
        self.taken.add(name)
        return name

    def attempt(self, title, overloads, invoke, subject, pad):
        """Prompt for arguments and call; if .NET rejects the values, show why and ask again."""
        while True:
            kwargs, codes = self.arguments(title, overloads, pad)
            try:
                return invoke(**kwargs), f"{subject}({', '.join(codes)})"
            except Exception as error:
                message = getattr(error, "Message", None) or str(error)
                self.write(f"{pad}! {subject} rejected these values: {message}")
                self.write(f"{pad}  Please enter them again (Ctrl+C to stop).")


def _star(optional) -> str:
    return "" if optional else "*"


def _setup_methods(clr_type):
    """Public instance methods returning nothing (e.g. Add, Set...), which configure an object after creation."""
    return [
        (name, overloads)
        for name, (static, generic, overloads) in clrinfo.methods(clr_type).items()
        if not static and not generic and all(o.return_type.FullName == "System.Void" for o in overloads)
    ]


def _signature_text(overload) -> str:
    return ", ".join(f"{p.name}: {clrinfo.param_hint(p.clr_type, _qualname)}" for p in overload.parameters)


def _constructible(clr_type) -> bool:
    from .auto import _is_domain

    if clr_type.IsInterface or (clr_type.IsAbstract and not clr_type.IsSealed):
        return True
    namespace = clr_type.Namespace or ""
    return (_is_domain(clr_type) or not namespace.startswith("System")) and bool(clrinfo.constructors(clr_type))


def _caller_namespace(depth):
    frame = sys._getframe(depth + 1)
    return {**frame.f_globals, **frame.f_locals}


def ask(target, *, overload=None, input=None, print=None, namespace=None):
    """Build an object or make a call by answering one prompt per argument.

    ``target`` is an auto-wrapped class (``pandasnet.ask(MyLib.Item)`` or ``MyLib.Item.ask()``) or one
    of its methods (``pandasnet.ask(engine.Run)``). Each prompt shows the argument's Python type and a
    hint; Enter keeps an optional argument's default; enum choices are numbered; objects can be named
    by an existing variable or created on the spot. The equivalent Python code is printed at the end.
    Returns the created object or the call's result.
    """

    from .auto import _AutoType

    read = builtins.input if input is None else input
    write = builtins.print if print is None else print
    session = _Session(read, write, _caller_namespace(1) if namespace is None else namespace)
    if isinstance(target, _AutoType):
        constructors = clrinfo.constructors(target.__clr_type__)
        if not constructors:
            if target.__clr_type__.IsInterface or target.__clr_type__.IsAbstract:
                result, code = session.create(target.__clr_type__, "")
            else:
                raise TypeError(f"{target.__qualname__} has no public constructors")
        else:
            if overload is not None:
                constructors = [constructors[overload]]
            result, code = session.attempt(target.__qualname__, constructors, target, target.__qualname__, "")
    else:
        owner, name = getattr(target, "__clr_owner__", None), getattr(target, "__clr_name__", None)
        if owner is None:
            raise TypeError("ask() expects a pandasnet class or one of its methods, e.g. pandasnet.ask(MyLib.Engine().Run)")
        _, _, overloads = clrinfo.methods(owner.__clr_type__)[name]
        if overload is not None:
            overloads = [overloads[overload]]
        instance = getattr(target, "__self__", None)
        if instance is None:
            subject = owner.__qualname__
        else:
            subject = next((key for key, value in session.namespace.items() if value is instance), f"{owner.__qualname__}(...)")
        result, code = session.attempt(f"{subject}.{name}", overloads, target, f"{subject}.{name}", "")
    lines = [*session.setup, code]
    session.write("\nEquivalent code:\n" + "\n".join(f"    {line}" for line in lines))
    return result
