@echo off
cd /d "%~dp0"
python -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1
python -m PyInstaller --noconfirm --clean RIO-System-Monitor.spec
