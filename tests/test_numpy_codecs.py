import pandasnet
import numpy as np
import pandas as pd
import pytest
import clr

from LibForTests import NumpyNet
from PandasNet import ArrayShape
from System import Array, DateTime, DateTimeKind, Double, Int32
from pandasnet import conversion

npnet = pandasnet.wrap_class(NumpyNet)


def test_numpy_integer_scalar():
    value = np.int32(42)
    result = npnet.Int32ScalarPassThrough(value)
    assert result == 42


def test_static_method():
    x = np.array([4, 5], dtype='int32')
    y = npnet.OneDimensionInt32Array(x)
    __check(x, y)


def test_instance_method():
    instance_api = pandasnet.wrap_class(NumpyNet())
    x = np.array([4, 5], dtype='int32')
    y = instance_api.InstanceInt32Array(x)
    __check(x, y)


def test_multiple_numpy_arguments():
    left = np.array([1, 2, 3], dtype='int32')
    right = np.array([10, 20, 30], dtype='int32')
    result = npnet.AddInt32Arrays(left, right)
    np.testing.assert_array_equal(result, np.array([11, 22, 33], dtype='int32'))


def test_mixed_arguments():
    values = np.array([2, 3], dtype='int32')
    result = npnet.MixedArguments(values, 4, 'item')
    assert result == 'item:8,12'


def test_none_and_clr_null_arguments():
    assert npnet.NullableInt32Array(None) is None
    assert npnet.ReturnNullInt32Array() is None


def test_overloaded_methods():
    int_values = np.array([1, 2], dtype='int32')
    double_values = np.array([1.5, 2.5], dtype='float64')
    assert npnet.Overloaded(int_values) == 'Int32[]'
    assert npnet.Overloaded(double_values) == 'Double[]'
    assert npnet.Overloaded('text') == 'String'


def test_one_dimensional_numpy_array_remains_clr_vector():
    values = np.array([1.0, 2.0, 3.0], dtype=np.float64)
    result = pandasnet.wrap(lambda value: value)(values)

    assert result.Rank == 1
    assert result.GetLength(0) == 3
    assert result.GetType().GetElementType() == clr.GetClrType(Double)
    assert [result.GetValue(i) for i in range(3)] == [1.0, 2.0, 3.0]


@pytest.mark.parametrize(
    "values, expected_shape",
    [
        (np.array([[1.0], [2.0], [3.0]], dtype=np.float64), (3, 1)),
        (np.array([[1.0, 2.0, 3.0]], dtype=np.float64), (1, 3)),
        (np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64), (2, 2)),
        (
            np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], dtype=np.float64),
            (2, 3),
        ),
    ],
)
def test_two_dimensional_float64_numpy_array_preserves_shape_and_values(values, expected_shape):
    result = pandasnet.wrap(lambda value: value)(values)

    assert result.Rank == 2
    assert (result.GetLength(0), result.GetLength(1)) == expected_shape
    assert result.GetType().GetElementType() == clr.GetClrType(Double)
    for row in range(expected_shape[0]):
        for column in range(expected_shape[1]):
            assert result.GetValue(row, column) == values[row, column]


def test_two_dimensional_int32_numpy_array_uses_existing_dtype_mapping():
    values = np.array([[1, 2], [3, 4]], dtype=np.int32)
    result = pandasnet.wrap(lambda value: value)(values)

    assert result.Rank == 2
    assert result.GetLength(0) == 2
    assert result.GetLength(1) == 2
    assert result.GetType().GetElementType() == clr.GetClrType(Int32)
    assert [result.GetValue(row, column) for row in range(2) for column in range(2)] == [1, 2, 3, 4]


def test_bool_codec():
    x = np.array([True, False, True], dtype='bool')
    y = npnet.OneDimensionBooleanArray(x)
    __check(x, y)

def test_int8_codec():
    x = np.array([1, 2, 3], dtype='int8')
    y = npnet.OneDimensionInt8Array(x)
    __check(x, y)

def test_int16_codec():
    x = np.array([1, 2, 3], dtype='int16')
    y = npnet.OneDimensionInt16Array(x)
    __check(x, y)

def test_int32_codec():
    x = np.array([1, 2, 3], dtype='int32')
    y = npnet.OneDimensionInt32Array(x)
    __check(x, y)

def test_int64_codec():
    x = np.array([1, 2, 3], dtype='int64')
    y = npnet.OneDimensionInt64Array(x)
    __check(x, y)

def test_uint8_codec():
    x = np.array([1, 2, 3], dtype='uint8')
    y = npnet.OneDimensionUInt8Array(x)
    __check(x, y)

def test_uint16_codec():
    x = np.array([1, 2, 3], dtype='uint16')
    y = npnet.OneDimensionUInt16Array(x)
    __check(x, y)

def test_uint32_codec():
    x = np.array([1, 2, 3], dtype='uint32')
    y = npnet.OneDimensionUInt32Array(x)
    __check(x, y)

def test_uint64_codec():
    x = np.array([1, 2, 3], dtype='uint64')
    y = npnet.OneDimensionUInt64Array(x)
    __check(x, y)

def test_float32_codec():
    x = np.array([1, 2, 3], dtype='float32')
    y = npnet.OneDimensionFloat32Array(x)
    __check(x, y)

def test_float64_codec():
    x = np.array([1, 2, 3], dtype='float64')
    y = npnet.OneDimensionFloat64Array(x)
    __check(x, y)

def test_string_codec():
    x = np.array(['foo_1', 'foo_2', 'foo_3'], dtype='str')
    y = npnet.OneDimensionStringArray(x)
    __check(x, y)

def test_datetime64_codec():
    x = np.array(
        ['2024-01-02T03:04:05.123456', '2024-07-08T09:10:11.654321'],
        dtype='datetime64[us]',
    )
    y = npnet.OneDimensionDateTimeArray(x)
    __check(x, y)

def test_timedelta64_codec():
    x = np.array([1, 123456, 999999], dtype='timedelta64[us]')
    y = npnet.OneDimensionTimeSpanArray(x)
    __check(x, y)


@pytest.mark.parametrize(
    "method, values",
    [
        ("ThreeDimensionBooleanArray", np.arange(24).reshape(2, 3, 4) % 3 == 0),
        ("ThreeDimensionInt32Array", np.arange(-12, 12, dtype=np.int32).reshape(2, 3, 4)),
        ("ThreeDimensionUInt64Array", np.arange(24, dtype=np.uint64).reshape(2, 3, 4) + np.uint64(2**63)),
        ("ThreeDimensionFloat32Array", np.linspace(-1, 1, 24, dtype=np.float32).reshape(2, 3, 4)),
        ("ThreeDimensionFloat64Array", np.random.default_rng(0).standard_normal((2, 5, 1000))),
        ("ThreeDimensionStringArray", np.array([f"s{i}" for i in range(12)]).reshape(2, 3, 2)),
        (
            "ThreeDimensionDateTimeArray",
            (np.datetime64("2026-01-01T00:00:00.000001", "us") + np.arange(8) * np.timedelta64(1, "D")).reshape(2, 2, 2),
        ),
        ("ThreeDimensionTimeSpanArray", np.arange(8).astype("timedelta64[us]").reshape(2, 2, 2)),
        ("FourDimensionFloat64Array", np.arange(120.0).reshape(2, 3, 4, 5)),
        ("ThreeDimensionFloat64Array", np.empty((0, 3, 4))),
    ],
)
def test_multi_dimensional_round_trip(method, values):
    result = getattr(npnet, method)(values)

    assert type(result) is np.ndarray
    assert result.dtype == values.dtype
    assert result.shape == values.shape
    np.testing.assert_array_equal(result, values)


def test_three_dimensional_layout_seen_by_clr():
    values = np.arange(24.0).reshape(2, 3, 4)
    for index in [(0, 0, 0), (0, 1, 2), (1, 0, 3), (1, 2, 3)]:
        assert npnet.ThreeDimensionElement(values, *index) == values[index]


def test_three_dimensional_clr_result_layout():
    result = npnet.CreateThreeDimensionFloat64Array(2, 3, 4)
    i, j, k = np.indices((2, 3, 4))
    np.testing.assert_array_equal(result, i * 100 + j * 10 + k)


def test_non_contiguous_and_non_native_byte_order_arrays():
    values = np.arange(48.0).reshape(4, 3, 4)[::2, :, ::-1]
    np.testing.assert_array_equal(npnet.ThreeDimensionFloat64Array(values), values)
    swapped = np.arange(24, dtype=">i4").reshape(2, 3, 4)
    np.testing.assert_array_equal(npnet.ThreeDimensionInt32Array(swapped), swapped)


def test_three_dimensional_safe_cast_to_double():
    values = np.arange(24, dtype=np.int32).reshape(2, 3, 4)
    result = npnet.ThreeDimensionFloat64Array(values)
    assert result.dtype == np.float64
    np.testing.assert_array_equal(result, values)


def test_overload_selected_by_rank():
    assert npnet.RankOverloaded(np.zeros((2, 2))) == 'Double[,]'
    assert npnet.RankOverloaded(np.zeros((2, 2, 2))) == 'Double[,,]'


@pytest.mark.parametrize("unit", ["W", "D", "h", "m", "s", "ms", "us", "ns", "15m", "2D"])
def test_datetime64_units_convert_to_utc_clr_ticks(unit):
    values = np.array(["2024-01-01", "1969-12-01", "2026-11-11"], dtype=f"datetime64[{unit}]")
    result = conversion._array_to_clr(values)
    expected = (values.astype("datetime64[us]").astype(np.int64) * 10 + conversion._UNIX_EPOCH_TICKS).tolist()

    assert result.GetType().GetElementType() == clr.GetClrType(DateTime)
    assert [result.GetValue(i).Ticks for i in range(len(values))] == expected
    assert all(result.GetValue(i).Kind == DateTimeKind.Utc for i in range(len(values)))


def test_datetime64_outside_nanosecond_range_keeps_exact_value():
    values = np.array(["0001-01-01T00:00:00", "9999-12-31T23:59:59.999999"], dtype="datetime64[us]")
    result = conversion._array_to_clr(values)
    assert result.GetValue(0).Ticks == 0
    assert result.GetValue(1).Ticks == conversion._MAX_DATETIME_TICKS - 9
    np.testing.assert_array_equal(npnet.OneDimensionDateTimeArray(values), values)


def test_sub_tick_nanoseconds_truncate_toward_zero():
    datetimes = np.array([150, -150], dtype="datetime64[ns]")
    result = conversion._array_to_clr(datetimes)
    epoch = conversion._UNIX_EPOCH_TICKS
    assert [result.GetValue(0).Ticks, result.GetValue(1).Ticks] == [epoch + 1, epoch - 1]

    spans = conversion._array_to_clr(np.array([150, -150, 99], dtype="timedelta64[ns]"))
    assert [spans.GetValue(i).Ticks for i in range(3)] == [1, -1, 0]


def test_multi_dimensional_timespan_result_matches_vector_encoder():
    nanoseconds = np.array([1500, -1500, 99, -99, 0, 10**15, -(10**15), 7], dtype="timedelta64[ns]")
    vector = conversion._value_from_clr(conversion._array_to_clr(nanoseconds))
    cube = conversion._value_from_clr(conversion._array_to_clr(nanoseconds.reshape(2, 2, 2)))

    assert cube.dtype == vector.dtype == np.dtype("timedelta64[us]")
    np.testing.assert_array_equal(cube, vector.reshape(2, 2, 2))


def test_temporal_values_outside_clr_range_raise():
    with pytest.raises(ValueError, match='outside the range of System.DateTime'):
        conversion._array_to_clr(np.array(["10000-01-01"], dtype="datetime64[D]"))
    with pytest.raises(ValueError, match='outside the range of CLR ticks'):
        conversion._array_to_clr(np.array([np.iinfo(np.int64).max // 2], dtype="timedelta64[W]"))
    with pytest.raises(TypeError, match='not supported'):
        conversion._array_to_clr(np.array([1], dtype="datetime64[ps]"))


def test_large_pandas_datetime_series_round_trip():
    dates = pd.Series(pd.date_range("2026-01-01", periods=200_000, freq="min"))
    np.testing.assert_array_equal(
        npnet.OneDimensionDateTimeArray(dates), dates.to_numpy().astype("datetime64[us]")
    )


@pytest.mark.parametrize(
    "strings",
    [
        ["plain", "", "with space", "comma,separated", "new\nline", "tab\there"],
        ["unicode é", "日本語", "emoji 🙂", "Ω≈ç√"],
        ["contains \x1f separator", "b", ""],
        [""],
        ["\x1f"],
        [f"factor_{i}" for i in range(50_000)],
    ],
    ids=["ascii", "unicode", "separator-fallback", "single-empty", "only-separator", "large"],
)
def test_string_array_round_trip(strings):
    values = np.array(strings)
    clr_values = conversion._array_to_clr(values)

    assert clr_values.GetType().FullName == "System.String[]"
    assert [clr_values.GetValue(i) for i in range(len(strings))] == strings
    result = npnet.OneDimensionStringArray(values)
    assert result.dtype == values.dtype
    np.testing.assert_array_equal(result, values)


def test_object_and_bytes_string_arrays():
    objects = np.array(["a", np.str_("b"), b"c", np.bytes_("d")], dtype=object)
    np.testing.assert_array_equal(npnet.OneDimensionStringArray(objects), np.array(["a", "b", "c", "d"]))
    raw = np.array([b"x", b"yz"], dtype="S")
    np.testing.assert_array_equal(npnet.OneDimensionStringArray(raw), np.array(["x", "yz"]))
    with pytest.raises(TypeError, match='all values are strings'):
        conversion._array_to_clr(np.array(["a", 1], dtype=object))


def test_empty_string_array():
    assert conversion._array_to_clr(np.array([], dtype=str)).Length == 0
    assert npnet.OneDimensionStringArray(np.array([], dtype=str)).size == 0


def test_clr_string_results_with_separator_or_null_fall_back():
    np.testing.assert_array_equal(npnet.StringsWithSeparator(), np.array(["a", "x\x1fy", ""]))
    assert list(npnet.StringsWithNull()) == ["a", None]


def test_three_dimensional_string_and_datetime_layout_seen_by_clr():
    strings = np.array([f"s{i}" for i in range(24)]).reshape(2, 3, 4)
    dates = (np.datetime64("1900-01-01", "us") + np.arange(24) * np.timedelta64(37, "h")).reshape(2, 3, 4)
    expected_ticks = dates.astype(np.int64) * 10 + conversion._UNIX_EPOCH_TICKS
    for index in [(0, 0, 0), (0, 1, 2), (1, 0, 3), (1, 2, 3)]:
        assert npnet.ThreeDimensionStringElement(strings, *index) == strings[index]
        assert npnet.ThreeDimensionDateTimeTicks(dates, *index) == expected_ticks[index]
        assert npnet.ThreeDimensionDateTimeKind(dates, *index) == "Utc"


@pytest.mark.parametrize(
    "method, values",
    [
        ("FiveDimensionStringArray", np.array([f"v{i}" for i in range(2 * 3 * 2 * 2 * 3)]).reshape(2, 3, 2, 2, 3)),
        (
            "FiveDimensionDateTimeArray",
            (np.datetime64("2026-01-01", "us") + np.arange(72) * np.timedelta64(1, "D")).reshape(2, 3, 2, 2, 3),
        ),
        ("ThreeDimensionStringArray", np.empty((0, 2, 3), dtype="<U1")),
        ("ThreeDimensionDateTimeArray", np.empty((2, 0, 3), dtype="datetime64[us]")),
    ],
)
def test_reshape_fallback_ranks_and_empty_arrays(method, values):
    result = getattr(npnet, method)(values)
    assert result.shape == values.shape
    np.testing.assert_array_equal(result, values)


def test_array_shape_rejects_mismatched_lengths():
    with pytest.raises(Exception, match='Cannot reshape 3 elements into 2x2'):
        ArrayShape.Reshape[Double](Array[Double]([1.0, 2.0, 3.0]), Array[Int32]([2, 2]))


def test_unsupported_numpy_dtype():
    with pytest.raises(TypeError, match='no supported CLR array mapping'):
        npnet.OneDimensionInt32Array(np.array([1 + 2j], dtype='complex64'))
    with pytest.raises(TypeError):
        npnet.OneDimensionInt32Array(np.array([[[1, 2]]], dtype='int32'))
    with pytest.raises(ValueError, match='Zero-dimensional'):
        npnet.OneDimensionInt32Array(np.array(1, dtype='int32'))
    with pytest.raises(ValueError, match='NaT'):
        npnet.OneDimensionDateTimeArray(np.array(['NaT'], dtype='datetime64[us]'))


def __check(x: np.array, y: np.array):
    assert x is not y
    assert x.dtype == y.dtype
    assert all(x == y)
