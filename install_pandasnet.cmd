@echo off
setlocal EnableDelayedExpansion

rem Install pandasnet into the currently activated Conda environment.
rem Keep this script beside the pandasnet-<version>-py*_*.conda package files (dist\conda\win-64).

if not defined CONDA_PREFIX (
    echo ERROR: No Conda environment is active.
    echo Activate your Miniforge environment first, then run this script from its folder.
    exit /b 1
)

if not defined CONDA_EXE (
    echo ERROR: CONDA_EXE is not set. Activate the environment using Miniforge Prompt or conda activate.
    exit /b 1
)

if not exist "%CONDA_PREFIX%\python.exe" (
    echo ERROR: Could not find python.exe in the active environment:
    echo        %CONDA_PREFIX%
    exit /b 1
)

if not exist "%CONDA_EXE%" (
    echo ERROR: Could not find the Conda executable:
    echo        %CONDA_EXE%
    exit /b 1
)

set "PY_TAG="
set "PY_VERSION_FILE=%TEMP%\pandasnet-python-version-%RANDOM%.txt"
"%CONDA_PREFIX%\python.exe" -c "import sys; print(str(sys.version_info.major) + str(sys.version_info.minor))" > "%PY_VERSION_FILE%" 2>nul
if errorlevel 1 (
    del "%PY_VERSION_FILE%" 2>nul
    echo ERROR: Could not run Python from the active Conda environment:
    echo        %CONDA_PREFIX%\python.exe
    exit /b 1
)
set /p "PY_TAG=" < "%PY_VERSION_FILE%"
del "%PY_VERSION_FILE%" 2>nul

if not defined PY_TAG (
    echo ERROR: Could not determine Python version from the active environment.
    exit /b 1
)

set "SUPPORTED= 311 312 313 314 315 "
if "!SUPPORTED: %PY_TAG% =!"=="%SUPPORTED%" (
    echo ERROR: Python %PY_TAG:~0,1%.%PY_TAG:~1% is unsupported by the available pandasnet packages.
    echo Supported versions: Python 3.11, 3.12, 3.13, 3.14, and 3.15.
    exit /b 1
)

rem Pick the most recently built package for this Python version (any pandasnet version or build number).
for /f "delims=" %%F in ('dir /b /o:-d "%CD%\pandasnet-*-py%PY_TAG%_*.conda" 2^>nul') do if not defined PACKAGE set "PACKAGE=%%F"

if not defined PACKAGE (
    echo ERROR: No matching pandasnet package for Python %PY_TAG:~0,1%.%PY_TAG:~1% was found in the current folder.
    echo Expected a file named pandasnet-^<version^>-py%PY_TAG%_^<build^>.conda, as built by build_packages.ps1.
    exit /b 1
)

if not exist "%CD%\%PACKAGE%" (
    echo ERROR: Matching package was not found in the current folder:
    echo        %CD%\%PACKAGE%
    exit /b 1
)

echo Active Conda environment: %CONDA_PREFIX%
echo Python package selected: %PACKAGE%
echo Installing runtime dependencies from conda-forge...
"%CONDA_EXE%" install --yes --prefix "%CONDA_PREFIX%" -c conda-forge "numpy>=2.0" "pandas>=3.0" "pythonnet>=3.2.1"
if errorlevel 1 (
    echo ERROR: Dependency installation failed. pandasnet was not installed.
    exit /b 1
)

echo Installing pandasnet from the local package file...
"%CONDA_EXE%" install --yes --prefix "%CONDA_PREFIX%" "%CD%\%PACKAGE%"
if errorlevel 1 (
    echo ERROR: pandasnet installation failed.
    exit /b 1
)

echo Verifying the pandasnet import...
"%CONDA_EXE%" run --prefix "%CONDA_PREFIX%" python -c "import pandasnet; print('pandasnet import succeeded')"
if errorlevel 1 (
    echo ERROR: Installation completed, but importing pandasnet failed.
    exit /b 1
)

echo pandasnet was installed successfully into:
echo %CONDA_PREFIX%
exit /b 0
