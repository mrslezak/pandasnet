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

For a one-off call, wrap a CLR method or constructor with `pandasnet.wrap`. To adapt a CLR type or instance once and call several methods through a proxy, use `pandasnet.wrap_class`. Both forms convert arguments for the selected CLR overload, including typed arrays; Python.NET's default array conversion does not reliably convert NumPy scalar elements.

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

* Python sequences and iterables (including lists, tuples, sets, ranges and generators) become `T[]`, or a `List<T>` for `List<T>`, `IList<T>`, `ICollection<T>`, `IReadOnlyList<T>` and `IEnumerable<T>` parameters, with elements converted recursively; one-dimensional pandas Series and Index values are supported too;
* mappings such as dicts become `Dictionary<K, V>` for `Dictionary`/`IDictionary`/`IReadOnlyDictionary` parameters;
* NumPy arrays of any rank become `T[]`, `T[,]`, `T[,,]`, ..., safely cast when the element type differs (for example `int32` -> `double[,,]`); numeric, boolean, date/time and string arrays are converted in bulk rather than element by element;
* Python, NumPy and pandas scalars, including `datetime`, `date`, `time`, `timedelta`, `datetime64` and `timedelta64`, become the matching CLR primitive, `DateTime` or `TimeSpan`.

Exact matches win over widening or generic conversions; if several overloads match equally well a `TypeError` lists them. Calls whose signatures cannot be described fall back to Python.NET binding. Wrapped *method* results are converted back recursively: supported numeric, boolean, string and date/time arrays and framework collections (`IEnumerable<T>`, `IReadOnlyList<T>`, `List<T>`, ...) become NumPy arrays, rectangular arrays keep their shape, `Dictionary<string, Array>` becomes a pandas DataFrame, other generic dictionaries become `dict`, tuples become `tuple`, and other collections become `list`. Domain objects stay CLR objects, and wrapped constructors return the constructed CLR object.

For CLR `DateTime` values whose `Kind` is `Local`, results use wall-clock values by default. Call `pandasnet.set_local_datetime_policy("utc")` to convert those values to UTC instead; UTC and unspecified CLR values retain their respective semantics.

```python
settings = pandasnet.wrap(Settings)(datetime(2026, 1, 1), [datetime(2026, 1, 5)], 1000, 12345, 365.0)
result = pandasnet.wrap(Processor().Run)(items, np.eye(2), settings)   # items: list of CLR objects
values = pandasnet.wrap(result.GetValues)("first", datetime(2026, 1, 5))  # IReadOnlyList<double> -> np.ndarray
```

#### Auto-wrapped namespaces

To avoid wrapping each constructor and method, load an assembly with `pandasnet.load`, or register it with `pandasnet.add_reference` so that ordinary imports from its namespace are auto-wrapped:

```python
MyLib = pandasnet.load(r"C:\libs\MyLib.dll")         # returns the assembly's root namespace

items = [MyLib.Item("A", 100.0), MyLib.Item("B", 95.0)]                  # .NET objects from Python values
dates = pd.date_range("2026-01-01", periods=12, freq="MS")
settings = MyLib.Settings(datetime(2026, 1, 1), dates, 1000)             # DatetimeIndex -> IEnumerable<DateTime>
result = MyLib.Engine().Run(items, np.eye(2), settings)                  # list -> IReadOnlyList<Item>, ndarray -> double[,]
values = result.GetValues("A", datetime(2026, 3, 1))                     # IReadOnlyList<double> -> np.ndarray

pandasnet.add_reference(r"C:\libs\MyLib.dll")        # or: auto-wrap `from MyLib import ...`
from MyLib import Engine, Item, Settings
result = Engine().Run([Item("A", 100.0)], np.eye(1), Settings(datetime(2026, 1, 1), dates, 1000))
```

Every constructor, method (static, instance and generic via `Method[T]`), property getter/setter, indexer and iterator then applies the `wrap` conversions above. Keyword arguments match .NET parameter names ignoring case and underscores (`start_date=` or `startDate=`). CLR objects are returned as instances of these classes (also inside returned lists, tuples and dicts) that can be passed straight back to .NET; enums are returned unwrapped. `isinstance(obj, MyLib.Item)` works, and `pandasnet.unwrap(obj)` returns the raw CLR object. The namespace defaults to the common root namespace of the assembly's exported types; pass `namespace=` to choose another. `add_reference` affects only the registered namespace and its sub-namespaces.

#### Discovering the API

Each .NET type is mirrored by a generated Python class whose constructors, methods and properties are real attributes with Python-facing signatures, so console/Jupyter completion, `help()` and `inspect.signature` work through whole call chains:

```python
>>> MyLib.Engine.Run
Run(items: Iterable[Item], matrix: ndarray, settings: Settings) -> ResultSet
    .NET: MyLib.ResultSet Run(System.Collections.Generic.IReadOnlyList`1[MyLib.Item], Double[,], MyLib.Settings)
>>> MyLib.Engine().Run(items, np.eye(2), settings).    # completion lists ResultSet's members
```

Editors that analyse files without running them (VS Code/Pylance, the Spyder editor) use stub files. `pandasnet.load` and `pandasnet.add_reference` keep them current automatically: they write a `MyLib-stubs` package into the active environment's site-packages whenever the assembly build (or pandasnet's stub generator) changed, and do nothing otherwise. Writes are atomic, and a failure (for example a read-only environment) only issues a warning. Pass `stubs=False` or set `PANDASNET_STUBS=0` to turn this off, or `stubs="some/folder"` to write elsewhere. To (re)generate them explicitly:

```python
pandasnet.generate_stubs(r"C:\libs\MyLib.dll")
```

The stubs describe the same Python-facing types, so `from MyLib import Engine` or `import MyLib` (with `pandasnet.add_reference` at runtime) gets completion, signatures and type checking in the editor. Editors cannot infer what `MyLib = pandasnet.load(...)` returns, so prefer the import style in code you edit.

The following tables summarize the registered Python.NET codec mappings. They are not an exhaustive list of `wrap` conversions: the target-aware wrapper also handles Python containers, compatible CLR collection interfaces, and overload-specific scalar conversions as described above.

### Python -> .Net (registered codecs)

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