@echo off
"%PYTHON%" -m pip install --no-deps --no-build-isolation --no-index --prefix "%PREFIX%" "%SRC_DIR%\pandasnet-%PKG_VERSION%-py3-none-win_amd64.whl"
if errorlevel 1 exit /b 1
