import pandasnet
import pandas as pd
import numpy as np
from datetime import datetime
import pytest

from LibForTests import PandasNet as pdnet


def test_basic_dataframe():
    x = pd.DataFrame({
        'A': [1, 2, 3],
        'B': [1.23, 1.24, 1.22],
        'C': ['foo', 'bar', 'other'],
        'D': [datetime(2021, 1, 22), datetime(2021, 1, 23), datetime(2021, 1, 24)],
        'E': [True, False, True]
    })
    y = pdnet.BasicDataFrame(x)
    
    __check(x, y)


def test_datetime64_into_dataframe():
    utc_minus_6 = pd.to_datetime([
        '2010-03-14T15:00:00.00-0600',
        '2010-03-15T15:00:00.00-0600',
        '2010-03-16T15:00:00.00-0600',
    ], utc=True).tz_localize(None).to_numpy(dtype='datetime64[us]')
    utc_plus_4 = pd.to_datetime([
        '2010-03-14T15:00:00.00+0400',
        '2010-03-15T15:00:00.00+0400',
        '2010-03-16T15:00:00.00+0400',
    ], utc=True).tz_localize(None).to_numpy(dtype='datetime64[us]')

    x = pd.DataFrame({
        'Utc': [
            np.datetime64('2010-03-14T15:00:00.00'),
            np.datetime64('2010-03-15T15:00:00.00'),
            np.datetime64('2010-03-16T15:00:00.00'),
        ],
        'Utc-6': utc_minus_6,
        'Utc+4': utc_plus_4,
    })

    assert x['Utc-6'].iloc[0] == np.datetime64('2010-03-14T21:00:00')
    assert x['Utc+4'].iloc[0] == np.datetime64('2010-03-14T11:00:00')
    y = pdnet.DateTimeDataFrame(x)
    
    __check(x, y)


def __check(x: pd.DataFrame, y: pd.DataFrame):
    assert x is not y
    assert y is not None
    assert all(x.columns == y.columns)
    for c in x.columns:
        assert all(x[c] == y[c])