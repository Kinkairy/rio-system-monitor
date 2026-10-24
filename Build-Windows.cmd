@echo off
setlocal
cd /d "%~dp0"
python tools\prepare_slim_build.py %*
if errorlevel 1 exit /b 1
python -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File sensors\Build-Sensors.ps1
if errorlevel 1 exit /b 1
rem Avoid collecting unrelated Qt/ICU DLLs from tools inherited through PATH.
for /f "delims=" %%I in ('python -c "import os,sys;print(os.path.dirname(sys.executable))"') do set "RIO_PYTHON_DIR=%%I"
for /f "delims=" %%I in ('python -c "import sys;print(sys.base_prefix)"') do set "RIO_PYTHON_BASE=%%I"
set "PATH=%RIO_PYTHON_DIR%;%RIO_PYTHON_BASE%;%SystemRoot%\System32;%SystemRoot%"
set "PYTHONPATH=%~dp0build\numpy-slim"
"%RIO_PYTHON_DIR%\python.exe" -m PyInstaller --noconfirm --clean RIO-System-Monitor.spec
if errorlevel 1 exit /b 1
"%RIO_PYTHON_DIR%\python.exe" tools\package_license_materials.py
