# pandasnet

[![build](https://github.com/fdieulle/pandasnet/actions/workflows/build.yml/badge.svg)](https://github.com/fdieulle/pandasnet/actions/workflows/build.yml)
[![release](https://github.com/fdieulle/pandasnet/actions/workflows/release.yml/badge.svg)](https://github.com/fdieulle/pandasnet/actions/workflows/release.yml)

[![license](https://img.shields.io/badge/license-MIT-blue.svg?maxAge=3600)](./LICENSE) 
[![pypi](https://img.shields.io/pypi/v/pandasnet.svg)](https://pypi.org/project/pandasnet/)
[![python supported](https://img.shields.io/pypi/pyversions/pandasnet.svg)](https://pypi.org/project/pandasnet/)

`pandasnet` is a python package build on top of [`pythonnet`](https://pythonnet.github.io/). 
It provides additional data conversions for `pandas`, `numpy` and `datetime`

## Prerequisites

* Python 3.11 or higher on Windows.
* NumPy 2.0 or higher and pandas 3.0 or higher.
* The [.NET Framework 4.8 runtime](https://dotnet.microsoft.com/download/dotnet-framework) to run the converters.
* Visual Studio Build Tools with the .NET Framework 4.7.2 targeting pack to build from source. The generated assemblies target .NET Framework 4.7.2 and run on .NET Framework 4.8; the .NET 8 SDK is not required.

## Installation

```
pip install pandasnet
```

## Features

To load the converter you need to import the package once in your python environment.
If the dotnet clr isn't started yet through the pytonnet package the import will.

```python
import pandasnet
```

We construct a simple C# function to test conversion

```csharp
using System;
using System.Collections.Generic;

namespace LibForTests
{
    public class PandasNet
    {
        public static Dictionary<string, Array> BasicDataFrame(Dictionary<string, Array> df)
            => df;
    }
}
```
We build this function into a library named `LibForTests.dll`.
We load this library into our python environment then use it.

```python
import clr
import pandasnet # Load the converters
import pandas as pd
from datetime import datetime

# Load your dll
clr.AddReference('LibForTests.dll')
from LibForTests import PandasNet as pdnet

x = pd.DataFrame({
    'A': [1, 2, 3],
    'B': [1.23, 1.24, 1.22],
    'C': ['foo', 'bar', 'other'],
    'D': [datetime(2021, 1, 22), datetime(2021, 1, 23), datetime(2021, 1, 24)]
})
y = pdnet.BasicDataFrame(x)

print(y)
```

For one-dimensional NumPy arrays passed to CLR methods that expect typed arrays, adapt the CLR type or instance once with `pandasnet.wrap_class`. You can then call its methods normally with NumPy arrays or scalars. Python.NET's default array conversion does not reliably convert NumPy scalar elements; the proxy normalizes them and constructs the matching CLR array before invocation.

```python
import numpy as np
import pandasnet
from LibForTests import NumpyNet as npnet

# Adapt once; the method expects System.Int32[] and the proxy maps dtype=int32.
npnet = pandasnet.wrap_class(npnet)
values = np.array([1, 2, 3], dtype=np.int32)
result = npnet.OneDimensionInt32Array(values)
```

`pandasnet.wrap` (and every method of a `wrap_class` proxy) is target-type aware. It reads the CLR overloads of the wrapped method or constructor, picks the overload whose parameter types best fit the Python arguments, and converts each argument to that parameter's type:

* lists/tuples become `T[]`, or a `List<T>` for `List<T>`, `IList<T>`, `ICollection<T>`, `IReadOnlyList<T>` and `IEnumerable<T>` parameters, with elements converted recursively;
* dicts become `Dictionary<K, V>` for `Dictionary`/`IDictionary`/`IReadOnlyDictionary` parameters;
* NumPy 1-D/2-D arrays become `T[]`/`T[,]`, safely cast when the element type differs (for example `int32` -> `double[]`);
* Python/NumPy scalars, `datetime`, `date`, `timedelta`, `datetime64` and `timedelta64` become the matching CLR primitive, `DateTime` or `TimeSpan`.

Exact matches win over widening or generic conversions; if several overloads match equally well a `TypeError` lists them. Wrapped *method* results are converted back recursively: numeric, boolean, string and date/time arrays and framework collections (`IEnumerable<T>`, `IReadOnlyList<T>`, `List<T>`, ...) become NumPy arrays, rectangular arrays keep their shape, dictionaries become `dict`, tuples become `tuple`, and other collections become `list`. Domain objects stay CLR objects, and wrapped constructors return the constructed CLR object.

```python
settings = pandasnet.wrap(Settings)(datetime(2026, 1, 1), [datetime(2026, 1, 5)], 1000, 12345, 365.0)
result = pandasnet.wrap(Processor().Run)(items, np.eye(2), settings)   # items: list of CLR objects
values = pandasnet.wrap(result.GetValues)("first", datetime(2026, 1, 5))  # IReadOnlyList<double> -> np.ndarray
```

Below an exhausitve list of supported data convertions.

### Python -> .Net (NumPy arrays via `pandasnet.wrap_class`)

|Python                                  |.Net                     |
|----------------------------------------|-------------------------|
|datetime.datetime                       |DateTime                 |
|datetime.date                           |DateTime                 |
|datetime.timedelta                      |TimeSpan                 |
|datetime.time                           |TimeSpan                 |
|numpy.ndarray(dtype=bool_)              |bool[]                   |
|numpy.ndarray(dtype=int8)               |sbyte[]                  |
|numpy.ndarray(dtype=int16)              |short[]                  |
|numpy.ndarray(dtype=int32)              |int[]                    |
|numpy.ndarray(dtype=int64)              |long[]                   |
|numpy.ndarray(dtype=uint8)              |byte[]                   |
|numpy.ndarray(dtype=uint16)             |ushort[]                 |
|numpy.ndarray(dtype=uint32)             |uint[]                   |
|numpy.ndarray(dtype=uint64)             |ulong[]                  |
|numpy.ndarray(dtype=float32)            |float[]                  |
|numpy.ndarray(dtype=float64)            |double[]                 |
|numpy.ndarray(dtype=datetime64)         |DateTime[]               |
|numpy.ndarray(dtype=timedelta64)        |TimeSpan[]               |
|numpy.ndarray(dtype=str)                |string[]                 |
|pandas._libs.tslibs.timestamps.Timestamp|DateTime                 |
|pandas._libs.tslibs.timedeltas.TimeDelta|TimeSpan                 |
|pandas.core.series.Series               |Array                    |
|pandas.core.frame.DataFrame             |Dictionary[string, Array]|

### .Net -> Python

|.Net                     |Python                          |
|-------------------------|--------------------------------|
|DateTime                 |datetime.datetime               |
|TimeSpan                 |datetime.timedelta              |
|bool[]                   |numpy.ndarray(dtype=bool_)      |
|sbyte[]                  |numpy.ndarray(dtype=int8)       |
|short[]                  |numpy.ndarray(dtype=int16)      |
|int[]                    |numpy.ndarray(dtype=int32)      |
|long[]                   |numpy.ndarray(dtype=int64)      |
|byte[]                   |numpy.ndarray(dtype=uint8)      |
|ushort[]                 |numpy.ndarray(dtype=uint16)     |
|uint[]                   |numpy.ndarray(dtype=uint32)     |
|ulong[]                  |numpy.ndarray(dtype=uint64)     |
|float[]                  |numpy.ndarray(dtype=float32)    |
|double[]                 |numpy.ndarray(dtype=float64)    |
|DateTime[]               |numpy.ndarray(dtype=datetime64) |
|TimeSpan[]               |numpy.ndarray(dtype=timedelta64)|
|Dictionary[string, Array]|pandas.core.frame.DataFrame     |

## Contributing

Issue tracker: [https://github.com/fdieulle/pandasnet/issues](https://github.com/fdieulle/pandasnet/issues)

If you want to checkout the project and propose your own contribution, you will need to setup it following few steps:

### Create a virtual environment:

```
python -m venv venv
```

### Activate your virtual environment:

```
venv/Scripts/activate
```

### Install package dependencies

```
pip install -r requirements.txt
```

### Build the pip wheel and conda packages

Requires Windows, Visual Studio Build Tools (MSBuild) and `conda-build`. From an activated conda prompt:

```
.\build_packages.ps1                 # latest release tag, Python 3.11-3.15
.\build_packages.ps1 -Python 3.12    # a single Python version
.\build_packages.ps1 -Tag v2.1 -BuildNumber 1
```

The script builds from a clean checkout of the tag, so `setup.py`'s version must match the tag (`v2.1` -> `2.1.0`). The wheel is written to `dist\wheels` and the conda packages to `dist\conda\win-64`. To install a conda package, copy `install_pandasnet.cmd` next to it and run it from an activated environment.

The conda-forge recipe in `conda-forge/` pins a released tarball, as conda-forge requires; its bot opens a pull request on the feedstock for each new tag.

## License

This project is open source under the [MIT license](./LICENSE).