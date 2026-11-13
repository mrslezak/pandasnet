"""DataFrame helpers for auto-wrapped classes: input schemas, templates, rows -> objects and objects -> rows."""

import inspect

import pandas as pd
from System import Enum, Nullable

from . import clrinfo
from .conversion import _ClrProxy, _explain, _keyword, _plan

_INTEGER_DTYPES = dict.fromkeys(clrinfo._INTEGERS, "Int64")
_DTYPES = {
    **_INTEGER_DTYPES,
    "System.Double": "float64",
    "System.Single": "float64",
    "System.Decimal": "float64",
    "System.Boolean": "boolean",
    "System.String": "string",
    "System.Char": "string",
    "System.DateTime": "datetime64[ns]",
    "System.TimeSpan": "timedelta64[ns]",
}
_MAX_REPORTED = 20


def _dtype(clr_type):
    underlying = Nullable.GetUnderlyingType(clr_type) or clr_type
    if underlying.IsEnum:
        return pd.CategoricalDtype([str(name) for name in Enum.GetNames(underlying)])
    return _DTYPES.get(underlying.FullName, "object")


def _default(parameter):
    default = parameter.default
    if default is inspect.Parameter.empty or default is ...:
        return pd.NA
    return default.member if isinstance(default, clrinfo.EnumDefault) else default


def _constructors(cls):
    clr_type = cls.__clr_type__
    constructors = clrinfo.constructors(clr_type)
    if not constructors:
        if clr_type.IsInterface or clr_type.IsAbstract:
            cls()  # raises the facade's explanation, naming implementations where there are any
        raise TypeError(f"{cls.__qualname__} has no public constructors")
    return constructors


def _pick(cls, constructors, overload):
    if overload is None:
        return max(constructors, key=lambda constructor: len(constructor.parameters))
    if not 0 <= overload < len(constructors):
        raise IndexError(f"{cls.__qualname__} has {len(constructors)} constructors; overload must be 0..{len(constructors) - 1}")
    return constructors[overload]


def input_schema(cls) -> pd.DataFrame:
    """One row per constructor argument: Python type, whether it is required, and its default."""
    from .auto import _qualname

    rows = []
    for index, constructor in enumerate(_constructors(cls)):
        for parameter in constructor.parameters:
            rows.append(
                {
                    "overload": index,
                    "argument": parameter.name,
                    "type": clrinfo.param_hint(parameter.clr_type, _qualname),
                    "required": parameter.default is inspect.Parameter.empty,
                    "default": _default(parameter),
                    "net_type": parameter.clr_type.ToString(),
                }
            )
    return pd.DataFrame(rows, columns=["overload", "argument", "type", "required", "default", "net_type"])


def template_frame(cls, rows: int = 0, overload=None) -> pd.DataFrame:
    """Empty (or ``rows``-long) DataFrame with one typed column per constructor argument.

    Optional arguments are pre-filled with their defaults; required ones are missing (NA) until filled.
    Fill it in (or export it with ``to_csv``/``to_excel``) and pass it to ``from_frame``.
    """

    constructor = _pick(cls, _constructors(cls), overload)
    columns = {}
    for parameter in constructor.parameters:
        default = _default(parameter)
        # None becomes each dtype's own missing marker (NaN, NaT, <NA>); pd.NA cannot fill float64.
        columns[parameter.name] = pd.Series([None if default is pd.NA else default] * rows, dtype=_dtype(parameter.clr_type))
    frame = pd.DataFrame(columns)
    frame.attrs["pandasnet"] = {
        "type": cls.__qualname__,
        "required": [p.name for p in constructor.parameters if p.default is inspect.Parameter.empty],
    }
    return frame


def _missing(value) -> bool:
    return pd.api.types.is_scalar(value) and bool(pd.isna(value))


def _parse_text(value, clr_type):
    """Date/time text (as read from CSV or Excel) parsed for DateTime/TimeSpan arguments; other values unchanged."""
    if not isinstance(value, str):
        return value
    name = (Nullable.GetUnderlyingType(clr_type) or clr_type).FullName
    parse = {"System.DateTime": pd.Timestamp, "System.TimeSpan": pd.Timedelta}.get(name)
    if parse is None:
        return value
    try:
        return parse(value)
    except ValueError:
        return value


def _match(cls, constructors, columns, overload):
    """The constructor whose arguments fit the frame's columns (names ignore case and underscores)."""
    keys = {_keyword(str(column)): column for column in columns}
    candidates = range(len(constructors)) if overload is None else [overload]
    problems, fits = [], []
    for index in candidates:
        constructor = _pick(cls, constructors, index)
        parameters = {_keyword(p.name): p for p in constructor.parameters}
        unknown = [column for key, column in keys.items() if key not in parameters]
        missing = [p.name for key, p in parameters.items() if p.default is inspect.Parameter.empty and key not in keys]
        if unknown or missing:
            detail = "; ".join(
                part
                for part in (
                    f"unknown columns {unknown}" if unknown else "",
                    f"missing required columns {missing}" if missing else "",
                )
                if part
            )
            problems.append(f"  {cls.__qualname__}({', '.join(p.name for p in constructor.parameters)}): {detail}")
        else:
            fits.append((len(parameters) - len(keys), constructor, {keys[key]: parameters[key] for key in keys}))
    if not fits:
        raise ValueError(f"The frame's columns do not fit any constructor of {cls.__qualname__}:\n" + "\n".join(problems))
    return min(fits, key=lambda fit: fit[0])[1:]


def from_frame(cls, frame: pd.DataFrame, overload=None) -> list:
    """Create one object per row, matching columns to constructor arguments by name.

    Missing cells in optional columns use the argument's default. All rows are checked before any
    object is created, and every problem is reported with its row label and column.
    """

    _, columns = _match(cls, _constructors(cls), frame.columns, overload)
    calls, problems = [], []
    for label, record in zip(frame.index, frame.to_dict("records")):
        arguments = {}
        for column, parameter in columns.items():
            value = _parse_text(record[column], parameter.clr_type)
            if _missing(value):
                if parameter.default is inspect.Parameter.empty:
                    problems.append(f"  row {label!r}, column {column!r}: missing value for required argument")
                continue
            if _plan(value, parameter.clr_type) is None:
                problems.append(f"  row {label!r}, column {column!r}: {_explain(value, parameter.clr_type)}")
                continue
            arguments[parameter.name] = value
        calls.append((label, arguments))
    if problems:
        shown = problems[:_MAX_REPORTED]
        more = f"\n  ... and {len(problems) - len(shown)} more" if len(problems) > len(shown) else ""
        raise ValueError(f"{len(problems)} problem(s) creating {cls.__qualname__} from the frame:\n" + "\n".join(shown) + more)

    objects = []
    for label, arguments in calls:
        try:
            objects.append(cls(**arguments))
        except Exception as error:
            raise ValueError(f"row {label!r}: creating {cls.__qualname__} failed: {error}") from error
    return objects


def to_frame(objects) -> pd.DataFrame:
    """One row per object and one column per readable property (values converted as usual)."""
    from .auto import _AutoObject, _auto

    if isinstance(objects, (_ClrProxy, _AutoObject)) or not hasattr(objects, "__iter__"):
        objects = [objects]
    rows = []
    for item in objects:
        item = _auto(item)
        if not isinstance(item, _AutoObject):
            raise TypeError(f"to_frame expects .NET objects, got {type(item).__name__}")
        names = [
            member.name
            for member in clrinfo.members(item.__clr_type__)
            if member.readable and not member.static and not member.name.startswith("_")
        ]
        rows.append({name: getattr(item, name) for name in names})
    return pd.DataFrame(rows)
