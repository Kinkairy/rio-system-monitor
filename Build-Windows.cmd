@echo off
cd /d "%~dp0"
python tools\verify_private_assets.py
if errorlevel 1 exit /b 1
python -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1
python -m PyInstaller --noconfirm --clean RIO-System-Monitor.spec
