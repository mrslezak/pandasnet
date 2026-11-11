from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

import pandasnet
from LibForTests import CollectionsNet, Item

net = pandasnet.wrap_class(CollectionsNet)

DATES = [
    datetime(2026, 1, 5),
    datetime(2026, 1, 12),
    datetime(2026, 1, 19),
    datetime(2026, 1, 26),
    datetime(2026, 2, 2),
]


# --- Python -> CLR: target-aware collection conversion ------------------------------------------


def test_list_of_datetime_to_ienumerable_datetime():
    assert net.CountDates(DATES) == 5


def test_tuple_of_datetime_to_ireadonlylist_datetime():
    assert net.LastDate(tuple(DATES)) == datetime(2026, 2, 2)


@pytest.mark.parametrize(
    "method",
    ["SumEnumerable", "SumReadOnlyList", "SumList", "SumCollection", "SumConcreteList", "SumArray"],
)
@pytest.mark.parametrize("values", [[1.0, 2.5, 3.5], (1.0, 2.5, 3.5), [1, 2.5, np.float64(3.5)]])
def test_python_sequence_to_generic_double_collections(method, values):
    assert getattr(net, method)(values) == 7.0


def test_ilist_parameter_receives_mutable_list():
    assert net.AppendToList([1.0, 2.0]) == 3


def test_empty_list_to_generic_collection():
    assert net.SumEnumerable([]) == 0.0


def test_integer_elements_widen_to_int64():
    assert net.SumInt64Enumerable([1, np.int32(2), np.int64(3)]) == 6


def test_timedelta_elements_to_ienumerable_timespan():
    total = net.TotalDuration([timedelta(hours=1), np.timedelta64(30, "m")])
    assert total == timedelta(hours=1, minutes=30)


def test_string_elements_to_ienumerable_string():
    assert net.JoinStrings(["a", np.str_("b")]) == "a,b"


def test_clr_objects_to_ireadonlylist_of_domain_type():
    assert net.JoinIds([Item("x", 1.0), Item("y", 2.0)]) == "x,y"


def test_object_ndarray_of_clr_objects_to_ireadonlylist():
    items = np.empty(2, dtype=object)
    items[:] = [Item("x", 1.0), Item("y", 2.0)]
    assert net.JoinIds(items) == "x,y"


def test_nested_lists_convert_recursively():
    assert net.CountNested([[1, 2], (3,), []]) == 3


def test_none_elements_to_nullable_collection():
    assert net.CountNonNull([datetime(2026, 1, 5), None, date(2026, 1, 6)]) == 2


def test_dict_to_idictionary():
    assert net.SumDictionary({"a": 1.0, "b": 2.5}) == 3.5


def test_dict_with_datetime_keys_to_ireadonlydictionary():
    assert net.SumReadOnlyDictionary({datetime(2026, 1, 5): 1.0, date(2026, 1, 6): 2.0}) == 3.0


@pytest.mark.parametrize("method", ["SumEnumerable", "SumReadOnlyList", "SumList", "SumConcreteList"])
def test_ndarray_to_generic_collection(method):
    assert getattr(net, method)(np.array([1.0, 2.0, 4.0])) == 7.0


@pytest.mark.parametrize("method", ["SumArray", "SumEnumerable"])
def test_int32_ndarray_safely_cast_for_double_parameters(method):
    assert getattr(net, method)(np.array([1, 2, 4], dtype=np.int32)) == 7.0


def test_datetime64_ndarray_to_ienumerable_datetime():
    assert net.CountDates(np.array(["2026-01-05", "2026-01-12"], dtype="datetime64[us]")) == 2


def test_keyword_arguments_are_converted_for_their_parameter():
    assert net.SumArray(values=[1.0, 2.0]) == 3.0


def test_incompatible_elements_still_raise():
    with pytest.raises(TypeError):
        net.CountDates(["not a date"])


# --- Python -> CLR: scalars and overload resolution ---------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        (5, "Int32"),
        (2**40, "Int64"),
        (np.int16(3), "Int32"),
        (np.int32(3), "Int32"),
        (np.int64(3), "Int64"),
        (np.float32(1.5), "Single"),
        (np.float64(1.5), "Double"),
        (1.5, "Double"),
        (True, "Boolean"),
        (np.bool_(True), "Boolean"),
        ("x", "String"),
        (datetime(2026, 1, 5, 12), "DateTime"),
        (date(2026, 1, 5), "DateTime"),
        (np.datetime64("2026-01-05T12:00"), "DateTime"),
        (timedelta(hours=1), "TimeSpan"),
        (np.timedelta64(1, "h"), "TimeSpan"),
    ],
)
def test_scalar_overload_prefers_native_clr_type(value, expected):
    assert net.Pick(value) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        (np.int8(1), "System.SByte"),
        (np.uint16(1), "System.UInt16"),
        (np.uint64(1), "System.UInt64"),
        (np.float32(1), "System.Single"),
        (np.bool_(False), "System.Boolean"),
    ],
)
def test_numpy_scalar_to_object_parameter_keeps_matching_clr_primitive(value, expected):
    assert net.TypeName(value) == expected


@pytest.mark.parametrize(
    "values, expected",
    [
        (DATES, "IEnumerable<DateTime>"),
        (["a", "b"], "IEnumerable<String>"),
        ([1.0, 2.0], "IEnumerable<Double>"),
        (np.array([1.0, 2.0]), "IEnumerable<Double>"),
    ],
)
def test_collection_overload_chosen_by_element_type(values, expected):
    assert net.PickCollection(values) == expected


def test_more_specific_collection_overload_wins():
    assert net.Specific([1.0, 2.0]) == "IReadOnlyList<Double>"


def test_ambiguous_overloads_raise_useful_error():
    with pytest.raises(TypeError, match=r"Ambiguous call to Ambiguous(.|\n)*List`1(.|\n)*Double\[\]"):
        net.Ambiguous([1.0, 2.0])


def test_exact_ndarray_match_resolves_otherwise_ambiguous_overload():
    assert net.Ambiguous(np.array([1.0, 2.0])) == "Double[]"


# --- CLR -> Python: recursive return conversion --------------------------------------------------


@pytest.mark.parametrize("method", ["ReadOnlyDoubles", "ReadOnlyDoublesArray"])
def test_ireadonlylist_double_returns_float64_ndarray(method):
    prices = getattr(net, method)(1000)
    assert type(prices) is np.ndarray
    assert prices.dtype == np.float64
    assert prices.shape == (1000,)
    assert prices[3] == 1.5


@pytest.mark.parametrize(
    "method, dtype, expected",
    [
        ("LazyDoubles", np.float64, [0.0, 1.0, 2.0, 3.0]),
        ("Int32List", np.int32, [1, 2, 3]),
        ("Int64Collection", np.int64, [4, 5]),
        ("SingleList", np.float32, [1.5, 2.5]),
        ("Booleans", np.bool_, [True, False]),
        ("Int32Array", np.int32, [7, 8]),
    ],
)
def test_numeric_collections_return_ndarrays(method, dtype, expected):
    args = (4,) if method == "LazyDoubles" else ()
    result = getattr(net, method)(*args)
    assert type(result) is np.ndarray
    assert result.dtype == dtype
    np.testing.assert_array_equal(result, np.array(expected, dtype=dtype))


def test_datetime_collection_returns_datetime64_ndarray():
    dates = net.Dates()
    assert dates.dtype.kind == "M"
    assert dates[1] - dates[0] == np.timedelta64(7, "D")


def test_string_collection_uses_string_array_codec():
    np.testing.assert_array_equal(net.Names(), np.array(["a", "b"]))


def test_nullable_collection_returns_list_with_none():
    assert net.NullableDoubles() == [1.0, None]


def test_null_collection_returns_none():
    assert net.NullDoubles() is None


def test_two_dimensional_arrays_return_shaped_ndarrays():
    matrix = net.Matrix()
    assert matrix.dtype == np.float64
    np.testing.assert_array_equal(matrix, [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])

    int_matrix = net.Int32Matrix()
    assert int_matrix.dtype == np.int32
    np.testing.assert_array_equal(int_matrix, [[1, 2], [3, 4]])


def test_domain_objects_stay_clr_objects():
    item = net.MakeItem("x", 1.0)
    assert isinstance(item, Item)
    assert item.Id == "x"


def test_collection_of_domain_objects_returns_list_of_clr_objects():
    items = net.Items()
    assert isinstance(items, list)
    assert [type(item) for item in items] == [Item, Item]
    assert [item.Id for item in items] == ["a", "b"]


def test_nested_collections_convert_recursively():
    jagged = net.Jagged()
    assert isinstance(jagged, list)
    np.testing.assert_array_equal(jagged[0], [1.0])
    np.testing.assert_array_equal(jagged[1], [2.0, 3.0])


def test_dictionary_returns_dict_of_ndarrays():
    prices = net.PricesById()
    assert set(prices) == {"a", "b"}
    np.testing.assert_array_equal(prices["a"], [1.0, 2.0])


def test_nested_dictionaries_convert_keys_and_values():
    prices = net.NestedPrices()
    values = prices["a"][datetime(2026, 1, 5)]
    assert type(values) is np.ndarray
    np.testing.assert_array_equal(values, [1.0, 2.0])


def test_registered_dataframe_codec_still_applies():
    frame = net.Frame()
    assert isinstance(frame, pd.DataFrame)
    assert list(frame["x"]) == [1.0, 2.0]


def test_tuples_return_python_tuples():
    number, values, text = net.TupleResult()
    assert (number, text) == (1, "x")
    np.testing.assert_array_equal(values, [1.0, 2.0])

    text, values = net.ValueTupleResult()
    assert text == "x"
    np.testing.assert_array_equal(values, [1.0])

    key, values = net.PairResult()
    assert key == "k"
    np.testing.assert_array_equal(values, [1])
