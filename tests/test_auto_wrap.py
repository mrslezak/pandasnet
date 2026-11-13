"""Auto-wrapped namespaces: pandasnet.load and the pandasnet.add_reference import hook."""

import importlib
import inspect
import os
import sys
from datetime import datetime

import numpy as np
import pytest

import pandasnet
from pandasnet import auto
from LibForTests import Item, Liquidity, Settings

LIBRARY = os.path.join(os.path.dirname(__file__), "libs", "LibForTests.dll")
DATES = [datetime(2026, 1, 5), datetime(2026, 1, 12)]


@pytest.fixture(scope="module")
def ns():
    return pandasnet.load(LIBRARY)


@pytest.fixture
def import_hook(monkeypatch):
    monkeypatch.setattr(sys, "meta_path", list(sys.meta_path))
    monkeypatch.setattr(auto, "_AUTO_NAMESPACES", set())
    saved = {name: module for name, module in sys.modules.items() if name.split(".")[0] == "LibForTests"}
    yield
    for name in [name for name in sys.modules if name.split(".")[0] == "LibForTests"]:
        del sys.modules[name]
    sys.modules.update(saved)


# --- pandasnet.load -----------------------------------------------------------------------------


def test_load_defaults_to_common_root_namespace(ns):
    assert ns.__name__ == "LibForTests"
    assert "Settings" in dir(ns)


def test_constructor_adapts_python_arguments_and_returns_proxy(ns):
    settings = ns.Settings(datetime(2026, 1, 1), DATES, 3, 1, 1.0)

    assert isinstance(settings, ns.Settings)
    assert not isinstance(settings, Settings)
    assert isinstance(pandasnet.unwrap(settings), Settings)
    assert settings.Name == "default"


def test_properties_are_converted(ns):
    settings = ns.Settings(datetime(2026, 1, 1), DATES, 3, 1, 1.0)
    np.testing.assert_array_equal(settings.Dates, np.array(DATES, dtype="datetime64[us]"))


def test_workflow_without_explicit_wrapping(ns):
    settings = ns.Settings(datetime(2026, 1, 1), DATES, 3, 1, 1.0)

    result = ns.Processor().Run([ns.Item("A", 1.0), ns.Item("B", 2.0)], np.eye(2), settings)
    values = result.GetValues("B", datetime(2026, 1, 12))

    assert isinstance(result, ns.ResultSet)
    assert type(values) is np.ndarray
    np.testing.assert_array_equal(values, [2.0, 3.0, 4.0])


def test_static_methods_return_facades_inside_collections(ns):
    items = ns.CollectionsNet.Items()

    assert [type(item) for item in items] == [ns.Item, ns.Item]
    assert [item.Id for item in items] == ["a", "b"]
    assert ns.CollectionsNet.JoinIds(items) == "a,b"


def test_raw_clr_objects_are_still_accepted(ns):
    assert ns.CollectionsNet.JoinIds([Item("x", 1.0), ns.Item("y", 2.0)]) == "x,y"


def test_facade_classes_are_cached(ns):
    assert ns.Settings is ns.Settings
    assert ns.Position.Leg is ns.Position.Leg
    assert type(ns.Position.Default) is ns.Position


def test_enums_pass_through_unwrapped(ns):
    position = ns.Position("x", datetime(2026, 1, 1), ns.Liquidity.Illiquid)

    assert ns.Liquidity is Liquidity
    assert position.Liquidity == Liquidity.Illiquid


def test_property_setters_convert_to_property_type(ns):
    position = ns.Position("x", datetime(2026, 1, 1), ns.Liquidity.Liquid)

    position.Maturity = datetime(2027, 6, 30)
    position.Weights = [0.25, 0.75]
    position.Underlying = ns.Item("u", 1.0)

    assert position.Maturity == datetime(2027, 6, 30)
    assert position.MaturityKind() == "Local"
    np.testing.assert_array_equal(position.Weights, [0.25, 0.75])
    assert position.Underlying.Id == "u"


def test_static_properties_and_nested_types(ns):
    assert ns.Position.Default.Id == "default"
    assert ns.Position.Leg(2.5).Notional == 2.5


def test_sub_namespace_indexer_and_iteration(ns):
    first = ns.Position("x", datetime(2026, 1, 1), ns.Liquidity.Liquid)
    first.Weights = [1.0, 2.0]
    portfolio = ns.Auto.Portfolio([first, ns.Position.Default])

    assert portfolio[0].Id == "x"
    assert portfolio[0] == first
    assert [position.Id for position in portfolio] == ["x", "default"]
    assert [position.Id for position in portfolio.Positions] == ["x", "default"]
    assert portfolio.TotalWeight() == 3.0
    assert portfolio.LastMaturity([datetime(2030, 1, 1)]) == datetime(2030, 1, 1)


def test_generic_methods_bind_proxied_type_arguments(ns):
    portfolio = ns.Auto.Portfolio([])
    item = ns.Item("e", 1.0)

    echoed = portfolio.Echo[ns.Item](item)

    assert echoed == item
    assert echoed.Id == "e"


def test_explicit_namespace(ns):
    sub = pandasnet.load(LIBRARY, namespace="LibForTests.Auto")
    assert sub.__name__ == "LibForTests.Auto"
    assert sub.Portfolio([]).TotalWeight() == 0.0


def test_load_requires_namespace_without_common_root():
    with pytest.raises(ValueError, match="namespace="):
        pandasnet.load("System")


def test_load_does_not_change_regular_imports(ns):
    assert importlib.import_module("LibForTests").Settings is Settings


def test_wrap_accepts_facade_classes(ns):
    settings = pandasnet.wrap(ns.Settings)(datetime(2026, 1, 1), DATES, 3, 1, 1.0)
    assert isinstance(settings, Settings)


def test_keyword_arguments_ignore_case_and_underscores(ns):
    settings = ns.Settings(Start=datetime(2026, 1, 1), dates=DATES, count=3, FACTOR=1, scale=1.0)
    result = ns.Processor().Run(items=[ns.Item("A", 1.0)], matrix=np.eye(1), settings=settings)

    np.testing.assert_array_equal(result.GetValues(id="A", date=DATES[0]), [1.0, 2.0, 3.0])


# --- Discoverability: real members, Python-facing signatures, IDE completion -------------------


def test_namespace_lists_types_and_sub_namespaces_up_front(ns):
    listed = set(vars(ns))
    assert {"Settings", "Processor", "Item", "Liquidity", "Position", "Auto"} <= listed
    assert "Portfolio" in vars(ns.Auto)


def test_members_are_real_class_attributes(ns):
    assert {"Run"} <= set(vars(ns.Processor))
    assert {"Id", "Maturity", "Weights", "MaturityKind", "Default", "Leg"} <= set(vars(ns.Position))


def test_signatures_describe_python_values(ns):
    assert str(inspect.signature(ns.Settings)) == (
        "(start: datetime, dates: Iterable[datetime] | DatetimeIndex | ndarray, count: int, factor: int, scale: float)"
    )
    assert str(inspect.signature(ns.Processor.Run)) == (
        "(self, items: Iterable[Item], matrix: ndarray, settings: Settings) -> ResultSet"
    )
    assert str(inspect.signature(ns.ResultSet.GetValues)) == "(self, id: str, date: datetime) -> ndarray"
    assert str(inspect.signature(ns.CollectionsNet.SumDictionary)) == "(values: Mapping[str, float]) -> float"
    assert "Settings(name: str, count: int, start: datetime, items: Iterable[Item], factor: int)" in ns.Settings.__doc__
    assert ".NET: LibForTests.ResultSet Run(" in ns.Processor.Run.__doc__


def test_property_docs_describe_types(ns):
    assert ns.Position.Weights.__doc__ == "Weights: ndarray  (settable: Iterable[float] | ndarray)"


def test_interface_docs_list_implementations_and_members(ns):
    doc = ns.IPricer.__doc__

    assert doc.startswith(".NET interface LibForTests.IPricer")
    assert "  FlatPricer\n  ShiftedPricer" in doc
    assert "Price(date: datetime) -> float" in doc
    assert "Price" in vars(ns.IPricer)


def test_interfaces_cannot_be_created_but_implementations_can_be_passed(ns):
    with pytest.raises(TypeError, match="IPricer is a .NET interface .* use one of: FlatPricer, ShiftedPricer"):
        ns.IPricer()

    pricer = ns.ShiftedPricer(ns.FlatPricer(2.0), 0.5)
    position = ns.Position("x", datetime(2026, 1, 1), ns.Liquidity.Liquid)

    assert isinstance(pricer, ns.IPricer)
    assert position.Value(pricer) == 2.5


def test_class_docs_list_members(ns):
    doc = ns.Position.__doc__
    assert "Properties:\n" in doc and "  Weights: ndarray" in doc
    assert "  Id: str  (read-only)" in doc
    assert "Methods:\n" in doc and "  Value(pricer: IPricer) -> float" in doc


def test_read_only_properties_point_to_the_constructor(ns):
    position = ns.Position("x", datetime(2026, 1, 1), ns.Liquidity.Liquid)

    assert ns.Position.Id.__doc__ == "Id: str  (read-only; set with Position(..., id=...))"
    with pytest.raises(TypeError, match=r"Position.Id is a property of Position objects, not a method"):
        ns.Position.Id("y")
    with pytest.raises(AttributeError, match=r"set it when creating the object: Position\(\.\.\., id=\.\.\.\)"):
        position.Id = "y"
    assert position.Id == "x"


def test_enum_defaults_are_shown_by_name(ns):
    assert str(inspect.signature(ns.Position.Describe)) == "(self, liquidity: Liquidity = Liquidity.Illiquid) -> str"
    assert ns.Position("x", datetime(2026, 1, 1), ns.Liquidity.Liquid).Describe() == "Illiquid"


@pytest.mark.parametrize("value", ["Illiquid", "illiquid", "Liquidity.Illiquid", 1])
def test_enum_parameters_accept_names_and_values(ns, value):
    assert ns.Position("x", datetime(2026, 1, 1), value).Liquidity == Liquidity.Illiquid


@pytest.mark.parametrize(
    "call, message",
    [
        (
            lambda ns: ns.Position("x", datetime(2026, 1, 1), "Medium"),
            "argument 'liquidity': got str 'Medium'; expected Liquidity; use Liquidity.<member> or one of 'Liquid', 'Illiquid'",
        ),
        (
            lambda ns: ns.Position("x", datetime(2026, 1, 1), "Liquid").Value(1.5),
            "argument 'pricer': got float 1.5; expected IPricer; pass one of: FlatPricer, ShiftedPricer",
        ),
        (
            lambda ns: ns.Processor().Run([1.0], np.eye(1), None),
            "argument 'items': element 0: got float 1.0; expected Item; create one with Item(id: str, value: float)",
        ),
        (lambda ns: ns.Position("x"), "missing argument 'maturity'"),
        (lambda ns: ns.Position("x", datetime(2026, 1, 1), "Liquid", colour="red"), "unknown argument 'colour'"),
    ],
)
def test_mismatched_calls_explain_what_to_pass(ns, call, message):
    with pytest.raises(TypeError) as error:
        call(ns)
    assert message in str(error.value)


def test_mismatch_explanations_cover_every_overload(ns):
    with pytest.raises(TypeError) as error:
        ns.Settings("365", DATES, 3, 1, 1.0)
    text = str(error.value)
    assert text.startswith("The arguments do not fit any of the 2 overloads of Settings:")
    assert "argument 'start': got str '365'; expected datetime" in text
    assert "argument 'count': got list" in text


@pytest.mark.parametrize(
    "code, expected",
    [
        ("ns.", {"Settings", "Processor", "Auto"}),
        ("ns.Processor.", {"Run"}),
        ("ns.Processor().Run([], None, None).", {"GetValues"}),
        ("ns.Position('x', None, None).Underlying.", {"Id", "Value"}),
        ("ns.Auto.Portfolio([])[0].", {"Maturity", "Weights"}),
        ("ns.Auto.Portfolio([]).Positions.", {"append"}),
        ("ns.IPricer.", {"Price"}),
    ],
)
def test_completion_traverses_calls_and_properties(ns, code, expected):
    jedi = pytest.importorskip("jedi")
    names = {completion.name for completion in jedi.Interpreter(code, [{"ns": ns}]).complete()}
    assert expected <= names


@pytest.mark.parametrize(
    "code, expected",
    [
        ("ns.Settings(", "Settings(start: datetime, dates: Iterable[datetime] | DatetimeIndex | ndarray, "),
        ("ns.Processor().Run(", "Run(items: Iterable[Item], matrix: ndarray, settings: Settings) -> ResultSet"),
    ],
)
def test_completion_shows_signatures(ns, code, expected):
    jedi = pytest.importorskip("jedi")
    signatures = [signature.to_string() for signature in jedi.Interpreter(code, [{"ns": ns}]).get_signatures()]
    assert any(signature.startswith(expected) for signature in signatures)


# --- pandasnet.add_reference ---------------------------------------------------------------------


def test_add_reference_wraps_imports(import_hook):
    namespace = pandasnet.add_reference(LIBRARY)

    from LibForTests import Item as AutoItem, Settings as AutoSettings

    assert isinstance(AutoSettings, auto._AutoType)
    assert sys.modules["LibForTests"] is namespace
    settings = AutoSettings(datetime(2026, 1, 1), DATES, 3, 1, 1.0)
    assert settings.Dates.dtype == np.dtype("datetime64[us]")
    assert AutoItem("a", 1.0).Id == "a"


def test_add_reference_wraps_sub_namespace_imports(import_hook):
    pandasnet.add_reference(LIBRARY)
    sys.modules.pop("LibForTests.Auto", None)

    import LibForTests.Auto as auto_namespace
    from LibForTests.Auto import Portfolio

    assert isinstance(auto_namespace, auto._Namespace)
    assert isinstance(Portfolio, auto._AutoType)
    assert Portfolio([]).TotalWeight() == 0.0


def test_add_reference_leaves_other_namespaces_alone(import_hook):
    pandasnet.add_reference(LIBRARY)

    from System import DateTime

    assert not isinstance(DateTime, auto._AutoType)
