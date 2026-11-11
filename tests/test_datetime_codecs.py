import pandasnet
from datetime import datetime, date, timedelta, time, timezone

import numpy as np
import pandas as pd
import pytest
from System import DateTimeKind

from LibForTests import DatetimeNet as dtnet

# Houston DST 2026: clocks jump 02:00 -> 03:00 on Mar 8 and fall back 02:00 -> 01:00 on Nov 1.
WALL_CLOCK_VALUES = [
    datetime(2026, 1, 5),                          # midnight
    datetime(2026, 11, 10, 14),                    # intraday, 2 PM
    datetime(2026, 11, 10, 14, 0, 0, 123456),      # sub-second
    datetime(2026, 7, 15, 23, 59, 59, 999999),     # summer time, last microsecond of the day
    datetime(2026, 3, 8, 1, 30),                   # before spring-forward
    datetime(2026, 3, 8, 2, 30),                   # skipped by spring-forward
    datetime(2026, 3, 8, 3, 30),                   # after spring-forward, same day
    datetime(2026, 11, 1, 1, 30),                  # repeated by fall-back
]
IDS = [value.isoformat() for value in WALL_CLOCK_VALUES]


def _ticks(value: datetime) -> int:
    return (value - datetime(1, 1, 1)) // timedelta(microseconds=1) * 10


@pytest.fixture
def local_as_utc():
    pandasnet.set_local_datetime_policy('utc')
    yield
    pandasnet.set_local_datetime_policy('wall_clock')


def test_datetime():
    now = datetime.now()
    result = dtnet.DateTimePassThrough(now)
    assert result == now

def test_date():
    today = datetime.now().date()
    result = dtnet.DateTimePassThrough(today)

    # Convert date to datetime
    today = datetime.combine(today, datetime.min.time())
    assert result == today

def test_timedelta():
    td = timedelta(days=1, hours=2, minutes=12, seconds=24, milliseconds=123)
    result = dtnet.TimeSpanPassThrough(td)

    assert result == td

def test_time():
    now = datetime.now().time()
    result = dtnet.TimeSpanPassThrough(now)

    # convert time to timedelta
    now = datetime.combine(date.min, now) - datetime.min
    assert result == now


# --- What goes in comes back out --------------------------------------------------------------


@pytest.mark.parametrize("value", WALL_CLOCK_VALUES, ids=IDS)
def test_naive_datetime_round_trips_unchanged(value):
    result = dtnet.DateTimePassThrough(value)
    assert result == value
    assert result.tzinfo is None


@pytest.mark.parametrize("value", WALL_CLOCK_VALUES, ids=IDS)
def test_naive_datetime_reaches_dotnet_with_its_wall_clock_ticks(value):
    assert dtnet.Ticks(value) == _ticks(value)


@pytest.mark.parametrize("container", [list, tuple])
def test_naive_datetime_collection_round_trips_unchanged(container):
    result = pandasnet.wrap(dtnet.ListPassThrough)(container(WALL_CLOCK_VALUES))
    np.testing.assert_array_equal(result, np.array(WALL_CLOCK_VALUES, dtype='datetime64[us]'))


def test_naive_datetime_list_to_clr_array_round_trips_unchanged():
    result = pandasnet.wrap(dtnet.ArrayPassThrough)(WALL_CLOCK_VALUES)
    np.testing.assert_array_equal(result, np.array(WALL_CLOCK_VALUES, dtype='datetime64[us]'))


@pytest.mark.parametrize("method", ["ArrayPassThrough", "ListPassThrough"])
def test_datetime64_array_round_trips_unchanged(method):
    values = np.array(WALL_CLOCK_VALUES, dtype='datetime64[us]')
    np.testing.assert_array_equal(pandasnet.wrap(getattr(dtnet, method))(values), values)


@pytest.mark.parametrize("value", WALL_CLOCK_VALUES, ids=IDS)
def test_aware_utc_datetime_round_trips_as_utc(value):
    aware = value.replace(tzinfo=timezone.utc)
    result = dtnet.DateTimePassThrough(aware)
    assert dtnet.Kind(aware) == 'Utc'
    assert result == aware
    assert result.utcoffset() == timedelta(0)


def test_aware_non_utc_datetime_returns_same_instant_in_utc():
    aware = datetime(2026, 11, 10, 14, tzinfo=timezone(timedelta(hours=4)))
    result = dtnet.DateTimePassThrough(aware)
    assert result == aware
    assert result.replace(tzinfo=None) == datetime(2026, 11, 10, 10)


def test_naive_pandas_timestamp_round_trips_unchanged():
    value = pd.Timestamp('2026-11-10 14:00:00.123456')
    assert dtnet.DateTimePassThrough(value) == value


def test_numpy_datetime64_scalar_is_utc():
    value = np.datetime64('2026-11-10T14:00:00.123456')
    result = pandasnet.wrap(dtnet.DateTimePassThrough)(value)
    assert result == datetime(2026, 11, 10, 14, 0, 0, 123456, tzinfo=timezone.utc)


# --- Return policy for each DateTimeKind --------------------------------------------------------


@pytest.mark.parametrize("kind", [DateTimeKind.Unspecified, DateTimeKind.Local], ids=["Unspecified", "Local"])
@pytest.mark.parametrize("value", WALL_CLOCK_VALUES, ids=IDS)
def test_unspecified_and_local_return_naive_wall_clock(value, kind):
    result = dtnet.FromTicks(_ticks(value), kind)
    assert result == value
    assert result.tzinfo is None


@pytest.mark.parametrize("value", WALL_CLOCK_VALUES, ids=IDS)
def test_utc_returns_aware_utc(value):
    result = dtnet.FromTicks(_ticks(value), DateTimeKind.Utc)
    assert result == value.replace(tzinfo=timezone.utc)
    assert result.utcoffset() == timedelta(0)


@pytest.mark.parametrize("kind", [DateTimeKind.Unspecified, DateTimeKind.Local, DateTimeKind.Utc],
                         ids=["Unspecified", "Local", "Utc"])
@pytest.mark.parametrize("method", ["ArrayFromTicks", "ListFromTicks"])
def test_datetime_collections_return_wall_clock_datetime64(method, kind):
    ticks = np.array([_ticks(value) for value in WALL_CLOCK_VALUES], dtype=np.int64)
    result = pandasnet.wrap(getattr(dtnet, method))(ticks, kind)
    assert result.dtype == np.dtype('datetime64[us]')
    np.testing.assert_array_equal(result, np.array(WALL_CLOCK_VALUES, dtype='datetime64[us]'))


# Avoids the skipped/repeated DST hours, whose UTC instant is ambiguous.
LOCAL_INSTANTS = [
    datetime(2026, 1, 5),
    datetime(2026, 7, 15, 14, 0, 0, 123456),
    datetime(2026, 3, 8, 1, 30),
    datetime(2026, 3, 8, 3, 30),
]


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


@pytest.mark.parametrize("value", LOCAL_INSTANTS, ids=[v.isoformat() for v in LOCAL_INSTANTS])
def test_local_policy_utc_returns_aware_utc_scalar(local_as_utc, value):
    result = dtnet.FromTicks(_ticks(value), DateTimeKind.Local)
    assert result == _as_utc(value)
    assert result.utcoffset() == timedelta(0)


def test_local_policy_utc_converts_each_array_element_with_its_own_offset(local_as_utc):
    ticks = np.array([_ticks(value) for value in LOCAL_INSTANTS], dtype=np.int64)
    result = pandasnet.wrap(dtnet.ArrayFromTicks)(ticks, DateTimeKind.Local)
    expected = [_as_utc(value).replace(tzinfo=None) for value in LOCAL_INSTANTS]
    np.testing.assert_array_equal(result, np.array(expected, dtype='datetime64[us]'))


def test_local_policy_utc_leaves_unspecified_values_alone(local_as_utc):
    value = datetime(2026, 11, 10, 14)
    assert dtnet.FromTicks(_ticks(value), DateTimeKind.Unspecified) == value


def test_invalid_local_policy():
    with pytest.raises(ValueError, match='wall_clock'):
        pandasnet.set_local_datetime_policy('local')