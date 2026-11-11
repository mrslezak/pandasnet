"""End-to-end Python -> .NET -> Python calls through pandasnet.wrap without manual CLR adaptation."""

from datetime import date, datetime, timezone

import clr
import numpy as np
import pandas as pd
import pytest
from System import DateTime, DateTimeKind
from System.Collections.Generic import IEnumerable

import pandasnet
from pandasnet import conversion
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


# --- Arguments are converted to the selected overload's CLR parameter types before invocation ---

DATE_COLLECTIONS = {
    "list": lambda: list(DATES),
    "tuple": lambda: tuple(DATES),
    "generator": lambda: (value for value in DATES),
    "DatetimeIndex": lambda: pd.DatetimeIndex(DATES),
    "Series": lambda: pd.Series(DATES),
    "datetime64 ndarray": lambda: np.array(DATES, dtype="datetime64[us]"),
    "Timestamp list": lambda: [pd.Timestamp(value) for value in DATES],
}
VALUATION_DATES = {
    "datetime": datetime(2026, 1, 1),
    "Timestamp": pd.Timestamp("2026-01-01"),
    "date": date(2026, 1, 1),
    "datetime64": np.datetime64("2026-01-01"),
}


def _converted_constructor_arguments(cls, *args):
    match = conversion._resolve(cls.__name__, conversion._constructor_overloads(cls), args, {})
    return match.overload.signature, [plan.convert() for plan in match.plans]


@pytest.mark.parametrize("dates", DATE_COLLECTIONS.values(), ids=DATE_COLLECTIONS.keys())
@pytest.mark.parametrize("valuation_date", VALUATION_DATES.values(), ids=VALUATION_DATES.keys())
def test_arguments_converted_to_selected_clr_parameter_types(valuation_date, dates):
    signature, converted = _converted_constructor_arguments(
        Settings, valuation_date, conversion._materialize(dates()), 1000, 12345, 365.0
    )
    converted_valuation_date, converted_dates = converted[:2]

    assert "IEnumerable`1[System.DateTime]" in signature
    assert converted_valuation_date.GetType() == clr.GetClrType(DateTime)
    assert clr.GetClrType(IEnumerable[DateTime]).IsInstanceOfType(converted_dates)
    assert converted_dates.Count == len(DATES)
    assert [p.GetType().FullName for p in converted[2:]] == ["System.Int32", "System.Int32", "System.Double"]


@pytest.mark.parametrize("dates", DATE_COLLECTIONS.values(), ids=DATE_COLLECTIONS.keys())
@pytest.mark.parametrize("valuation_date", VALUATION_DATES.values(), ids=VALUATION_DATES.keys())
def test_constructor_succeeds_with_python_date_inputs(valuation_date, dates):
    settings = pandasnet.wrap(Settings)(valuation_date, dates(), 1000, 12345, 365.0)
    np.testing.assert_array_equal(
        pandasnet.wrap_class(settings).get_Dates(), np.array(DATES, dtype="datetime64[us]")
    )


def test_aware_datetime_converts_to_utc_clr_datetime():
    _, converted = _converted_constructor_arguments(
        Settings, datetime(2026, 1, 1, 6, tzinfo=timezone.utc), DATES, 1, 1, 1.0
    )
    assert converted[0].Kind == DateTimeKind.Utc
    assert converted[0].Hour == 6


def test_timestamp_nanoseconds_reach_clr_ticks():
    _, converted = _converted_constructor_arguments(
        Settings, pd.Timestamp("2026-01-01 00:00:00.000000123"), DATES, 1, 1, 1.0
    )
    assert converted[0].Ticks % 10 == 1
