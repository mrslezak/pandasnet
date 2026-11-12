"""Auto-wrapped namespaces: pandasnet.load and the pandasnet.add_reference import hook."""

import importlib
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


def test_static_methods_return_proxies_inside_collections(ns):
    items = ns.CollectionsNet.Items()

    assert [type(item) for item in items] == [auto._AutoProxy, auto._AutoProxy]
    assert [item.Id for item in items] == ["a", "b"]
    assert ns.CollectionsNet.JoinIds(items) == "a,b"


def test_raw_clr_objects_are_still_accepted(ns):
    assert ns.CollectionsNet.JoinIds([Item("x", 1.0), ns.Item("y", 2.0)]) == "x,y"


def test_type_proxies_are_cached(ns):
    assert ns.Settings is ns.Settings
    assert ns.Position.Leg is ns.Position.Leg


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


def test_wrap_accepts_type_proxies(ns):
    settings = pandasnet.wrap(ns.Settings)(datetime(2026, 1, 1), DATES, 3, 1, 1.0)
    assert isinstance(settings, Settings)


# --- pandasnet.add_reference ---------------------------------------------------------------------


def test_add_reference_wraps_imports(import_hook):
    namespace = pandasnet.add_reference(LIBRARY)

    from LibForTests import Item as AutoItem, Settings as AutoSettings

    assert isinstance(AutoSettings, auto._AutoProxy)
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
    assert isinstance(Portfolio, auto._AutoProxy)
    assert Portfolio([]).TotalWeight() == 0.0


def test_add_reference_leaves_other_namespaces_alone(import_hook):
    pandasnet.add_reference(LIBRARY)

    from System import DateTime

    assert not isinstance(DateTime, auto._AutoProxy)
