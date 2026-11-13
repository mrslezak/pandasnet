"""pandasnet.ask / Class.ask(): one prompt per argument with type, hint and default."""

import builtins
import os
from datetime import datetime

import numpy as np
import pytest

import pandasnet
from LibForTests import Liquidity

LIBRARY = os.path.join(os.path.dirname(__file__), "libs", "LibForTests.dll")


@pytest.fixture(scope="module")
def ns():
    return pandasnet.load(LIBRARY, stubs=False)


class Console:
    """Scripted answers; records the transcript (prompts with answers, plus printed lines)."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.lines = []

    def input(self, prompt):
        answer = self.answers.pop(0)
        self.lines.append(prompt + answer)
        return answer

    def print(self, *parts):
        self.lines.append(" ".join(str(part) for part in parts))

    @property
    def text(self):
        return "\n".join(self.lines)


def _ask(target, console, **kwargs):
    return pandasnet.ask(target, input=console.input, print=console.print, **kwargs)


def test_prompts_show_type_hint_and_default(ns):
    console = Console("A1", "2026-12-31", "12.5", "", "")
    trade = _ask(ns.Trade, console)

    assert (trade.Id, trade.TradeDate, trade.Quantity, trade.Liquidity, trade.Lots) == (
        "A1", datetime(2026, 12, 31), 12.5, Liquidity.Liquid, 1
    )
    assert "  id* (str) text: A1" in console.text
    assert "  tradeDate* (datetime) date, e.g. 2026-12-31: 2026-12-31" in console.text
    assert "  liquidity (Liquidity) choose: 0=Liquid, 1=Illiquid" in console.text
    assert "  lots (int) whole number, e.g. 1000 [Enter = 1]: " in console.text
    assert console.text.endswith("Equivalent code:\n    Trade(id='A1', tradeDate=datetime(2026, 12, 31), quantity=12.5)")


def test_invalid_answers_are_explained_and_asked_again(ns):
    console = Console("A1", "Dec 31st?", "31 Dec 2026", "abc", "12.5", "Medium", "1", "two", "2")
    trade = _ask(ns.Trade, console)

    assert (trade.TradeDate, trade.Quantity, trade.Liquidity, trade.Lots) == (datetime(2026, 12, 31), 12.5, Liquidity.Illiquid, 2)
    assert "! 'Dec 31st?' is not a date; enter e.g. 2026-12-31" in console.text
    assert "= 2026-12-31 00:00" in console.text
    assert "! 'abc' is not a number; enter e.g. 0.25" in console.text
    assert "! enter a number 0-1 or one of Liquid, Illiquid" in console.text
    assert "! 'two' is not a whole number; enter e.g. 1000" in console.text


def test_required_arguments_cannot_be_skipped(ns):
    console = Console("", "A1", "2026-01-01", "1", "", "")
    _ask(ns.Trade, console)
    assert "! required: please enter a value" in console.text


def test_overloads_are_offered_by_their_differences(ns):
    console = Console("1", "named", "3", "2026-01-01", "1", "x", "1.0", "7")
    settings = _ask(ns.Settings, console)

    assert (settings.Name, settings.Count, settings.Factor) == ("named", 3, 7)
    assert "Settings can be called 2 ways:" in console.text
    assert "items[0] = Item (* = required, Enter = keep default):" in console.text
    assert "Settings(name='named', count=3, start=datetime(2026, 1, 1), items=[Item(id='x', value=1.0)], factor=7)" in console.text


def test_interfaces_offer_their_implementations(ns):
    position = ns.Position("p", datetime(2026, 1, 1), "Liquid")
    console = Console("", "1", "", "0", "2.0", "0.5")

    assert _ask(position.Value, console, namespace={"position": position}) == 2.5
    assert "IPricer needs one of these IPricer types:\n      0: FlatPricer\n      1: ShiftedPricer" in console.text
    assert console.text.endswith("position.Value(pricer=ShiftedPricer(inner=FlatPricer(level=2.0), shift=0.5))")


def test_existing_variables_lists_and_matrices(ns):
    settings = ns.Settings(datetime(2026, 1, 1), [datetime(2026, 1, 1)], 3, 1, 1.0)
    processor = ns.Processor()
    console = Console("2", "a", "1.5", "b", "2", "1, 0.5; 0.5", "1, 0.5; 0.5, 1", "nope", "settings")

    result = _ask(processor.Run, console, namespace={"settings": settings, "processor": processor})

    np.testing.assert_array_equal(result.GetValues("b", datetime(2026, 1, 1)), [2.0, 3.0, 4.0])
    assert "! every row needs the same number of values" in console.text
    assert "! no variable named 'nope' holding a Settings" in console.text
    assert "matrix=np.array([[1.0, 0.5], [0.5, 1.0]]), settings=settings)" in console.text


def test_static_method_with_a_list_of_dates(ns):
    console = Console("2026-01-05, 2026-01-12")
    assert _ask(ns.CollectionsNet.CountDates, console) == 2
    assert "CollectionsNet.CountDates(values=[datetime(2026, 1, 5), datetime(2026, 1, 12)])" in console.text


def test_class_ask_uses_the_console(ns, monkeypatch):
    console = Console("u", "2.0")
    monkeypatch.setattr(builtins, "input", console.input)
    monkeypatch.setattr(builtins, "print", console.print)

    item = ns.Item.ask()

    assert (item.Id, item.Value) == ("u", 2.0)
    assert "Item(id='u', value=2.0)" in console.text


def test_ask_rejects_other_callables():
    with pytest.raises(TypeError, match="expects a pandasnet class or one of its methods"):
        pandasnet.ask(len)


def test_values_rejected_by_dotnet_are_explained_and_asked_again(ns):
    settings = ns.Settings(datetime(2026, 1, 1), [datetime(2026, 1, 1)], 3, 1, 1.0)
    processor = ns.Processor()
    console = Console("1", "a", "1.5", "1, 0.5; 0.5, 1", "settings", "1", "a", "1.5", "1", "settings")

    result = _ask(processor.Run, console, namespace={"settings": settings, "processor": processor})

    np.testing.assert_array_equal(result.GetValues("a", datetime(2026, 1, 1)), [1.5, 2.5, 3.5])
    assert "! processor.Run rejected these values: Matrix must be items.Count x items.Count." in console.text
    assert "Please enter them again" in console.text


def test_objects_without_constructor_arguments_offer_their_setup_calls(ns):
    position = ns.Position("p", datetime(2026, 6, 30), "Liquid")
    console = Console("", "2", "2", "2026-01-01", "1.0", "2026-06-01", "3.0")

    assert _ask(position.Value, console, namespace={"position": position}) == 3.0
    assert "StepPricer takes no constructor arguments; it is set up by calling Add(from_: datetime, level: float)" in console.text
    assert console.text.endswith(
        "Equivalent code:\n"
        "    stepPricer = StepPricer()\n"
        "    stepPricer.Add(from_=datetime(2026, 1, 1), level=1.0)\n"
        "    stepPricer.Add(from_=datetime(2026, 6, 1), level=3.0)\n"
        "    position.Value(pricer=stepPricer)"
    )
