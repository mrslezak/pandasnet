import pandasnet
import numpy as np
import pytest
import clr

from LibForTests import NumpyNet
from System import Double, Int32

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


def test_unsupported_numpy_dtype():
    with pytest.raises(TypeError, match='no supported CLR array mapping'):
        npnet.OneDimensionInt32Array(np.array([1 + 2j], dtype='complex64'))
    with pytest.raises(ValueError, match='one-dimensional'):
        npnet.OneDimensionInt32Array(np.array([[[1, 2]]], dtype='int32'))
    with pytest.raises(ValueError, match='NaT'):
        npnet.OneDimensionDateTimeArray(np.array(['NaT'], dtype='datetime64[us]'))


def __check(x: np.array, y: np.array):
    assert x is not y
    assert x.dtype == y.dtype
    assert all(x == y)
