"""DataFrame helpers on auto-wrapped classes: input_schema, template_frame, from_frame and pandasnet.to_frame."""

import os
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

import pandasnet
from LibForTests import Liquidity

LIBRARY = os.path.join(os.path.dirname(__file__), "libs", "LibForTests.dll")


@pytest.fixture(scope="module")
def ns():
    return pandasnet.load(LIBRARY, stubs=False)


def _filled(ns):
    frame = ns.Trade.template_frame(rows=2)
    frame["id"] = ["A", "B"]
    frame["tradeDate"] = pd.to_datetime(["2026-01-05", "2026-02-05"])
    frame["quantity"] = [10.0, 20.0]
    return frame


def test_input_schema_lists_arguments_types_and_defaults(ns):
    schema = ns.Trade.input_schema()

    assert schema["argument"].tolist() == ["id", "tradeDate", "quantity", "liquidity", "lots"]
    assert schema["type"].tolist() == ["str", "datetime", "float", "Liquidity", "int"]
    assert schema["required"].tolist() == [True, True, True, False, False]
    assert schema["default"].tolist()[3:] == ["Liquid", 1]


def test_input_schema_covers_every_constructor(ns):
    schema = ns.Settings.input_schema()
    assert sorted(schema["overload"].unique()) == [0, 1]


def test_template_has_typed_columns_and_defaults(ns):
    frame = ns.Trade.template_frame(rows=2)

    assert list(frame.columns) == ["id", "tradeDate", "quantity", "liquidity", "lots"]
    assert frame["tradeDate"].dtype == np.dtype("datetime64[ns]")
    assert frame["quantity"].dtype == np.float64
    assert list(frame["liquidity"].cat.categories) == ["Liquid", "Illiquid"]
    assert frame["lots"].dtype == "Int64"
    assert frame["liquidity"].tolist() == ["Liquid", "Liquid"]
    assert frame["lots"].tolist() == [1, 1]
    assert frame["id"].isna().all() and frame["tradeDate"].isna().all()
    assert frame.attrs["pandasnet"]["required"] == ["id", "tradeDate", "quantity"]


def test_empty_template_by_default(ns):
    assert len(ns.Trade.template_frame()) == 0


def test_from_frame_creates_one_object_per_row(ns):
    frame = _filled(ns)
    frame.loc[1, "lots"] = pd.NA
    frame.loc[1, "liquidity"] = "Illiquid"

    trades = ns.Trade.from_frame(frame)

    assert [type(trade) for trade in trades] == [ns.Trade, ns.Trade]
    assert [trade.Id for trade in trades] == ["A", "B"]
    assert trades[1].TradeDate == datetime(2026, 2, 5)
    assert trades[1].Lots == 1
    assert trades[1].Liquidity == Liquidity.Illiquid


def test_from_frame_accepts_any_column_spelling_and_date_text(ns):
    frame = pd.DataFrame({"ID": ["A"], "trade_date": ["2026-01-05"], "Quantity": [5.0]})
    (trade,) = ns.Trade.from_frame(frame)
    assert (trade.Id, trade.TradeDate, trade.Quantity, trade.Lots) == ("A", datetime(2026, 1, 5), 5.0, 1)


def test_from_frame_reports_every_problem_before_creating_anything(ns):
    frame = pd.DataFrame(
        {"id": ["A", None], "tradeDate": ["Dec-26x", "2026-01-01"], "quantity": [1.0, "x"], "liquidity": ["Liquid", "Medium"]}
    )
    with pytest.raises(ValueError) as error:
        ns.Trade.from_frame(frame)
    text = str(error.value)

    assert text.startswith("4 problem(s) creating Trade from the frame:")
    assert "row 0, column 'tradeDate': got str 'Dec-26x'; expected datetime" in text
    assert "row 1, column 'id': missing value for required argument" in text
    assert "row 1, column 'quantity': got str 'x'; expected float" in text
    assert "row 1, column 'liquidity': got str 'Medium'; expected Liquidity" in text


def test_from_frame_reports_column_mismatches(ns):
    with pytest.raises(ValueError, match=r"unknown columns \['colour'\]; missing required columns \['tradeDate', 'quantity'\]"):
        ns.Trade.from_frame(pd.DataFrame({"id": ["A"], "colour": ["red"]}))


def test_from_frame_picks_the_constructor_matching_the_columns(ns):
    frame = pd.DataFrame({"name": ["n"], "count": [3], "start": [datetime(2026, 1, 1)], "items": [[ns.Item("a", 1.0)]], "factor": [1]})
    (settings,) = ns.Settings.from_frame(frame)
    assert settings.Name == "n"


def test_frame_helpers_explain_interfaces(ns):
    with pytest.raises(TypeError, match="use one of: FlatPricer, ShiftedPricer"):
        ns.IPricer.template_frame()


def test_to_frame_lists_readable_properties(ns):
    frame = pandasnet.to_frame(ns.Trade.from_frame(_filled(ns)))

    assert list(frame.columns) == ["Id", "TradeDate", "Quantity", "Liquidity", "Lots", "Notional"]
    assert frame["Notional"].tolist() == [10.0, 20.0]
    assert frame["TradeDate"].tolist() == [datetime(2026, 1, 5), datetime(2026, 2, 5)]


def test_to_frame_round_trips_through_from_frame(ns):
    trades = ns.Trade.from_frame(_filled(ns))
    again = ns.Trade.from_frame(pandasnet.to_frame(trades).drop(columns=["Notional"]))
    assert [(t.Id, t.Quantity) for t in again] == [("A", 10.0), ("B", 20.0)]


def test_to_frame_accepts_a_single_object(ns):
    assert pandasnet.to_frame(ns.Item("a", 1.0)).to_dict("records") == [{"Id": "a", "Value": 1.0}]
