"""End-to-end Python -> .NET -> Python calls through pandasnet.wrap without manual CLR adaptation."""

from datetime import datetime

import numpy as np

import pandasnet
from LibForTests import Item, Processor, ResultSet, Settings

DATES = [
    datetime(2026, 1, 5),
    datetime(2026, 1, 12),
    datetime(2026, 1, 19),
    datetime(2026, 1, 26),
    datetime(2026, 2, 2),
]
MATRIX = np.array([[1.00, 0.75], [0.75, 1.00]], dtype=np.float64)


def test_equal_arity_constructor_overloads_resolved_by_parameter_types():
    create_settings = pandasnet.wrap(Settings)

    settings = create_settings(datetime(2026, 1, 1), DATES, 1000, 12345, 365.0)
    assert isinstance(settings, Settings)
    assert settings.Name == "default"
    assert settings.Dates.Count == 5
    assert (settings.Count, settings.Factor, settings.Scale) == (1000, 12345, 365.0)

    named = create_settings("named", 10, datetime(2026, 1, 1), [Item("a", 1.0), Item("b", 2.0)], 7)
    assert named.Name == "named"
    assert named.Dates.Count == 2


def test_workflow_with_plain_python_inputs():
    items = [Item("first", 100.0), Item("second", 95.0)]
    settings = pandasnet.wrap(Settings)(datetime(2026, 1, 1), DATES, 1000, 12345, 365.0)

    result = pandasnet.wrap(Processor().Run)(items, MATRIX, settings)
    assert isinstance(result, ResultSet)

    values = pandasnet.wrap(result.GetValues)("first", datetime(2026, 1, 5))

    assert type(values) is np.ndarray
    assert values.dtype == np.float64
    assert values.shape == (1000,)
    assert values[0] == 100.0
    assert values[-1] == 1099.0


def test_workflow_through_wrap_class():
    processor = pandasnet.wrap_class(Processor())
    settings = pandasnet.wrap(Settings)(datetime(2026, 1, 1), DATES, 10, 1, 365.0)

    result = processor.Run([Item("A", 1.0), Item("B", 2.0)], MATRIX, settings)
    values = pandasnet.wrap_class(result).GetValues("B", datetime(2026, 2, 2))

    assert type(values) is np.ndarray
    assert values.shape == (10,)
    assert values[0] == 2.0


def test_returned_dates_round_trip_unchanged():
    settings = pandasnet.wrap(Settings)(datetime(2026, 1, 1), DATES, 1, 1, 1.0)
    dates = pandasnet.wrap_class(settings).get_Dates()
    np.testing.assert_array_equal(dates, np.array(DATES, dtype="datetime64[us]"))
