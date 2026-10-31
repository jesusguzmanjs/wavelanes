@echo off
rem Double-click to remove WaveLanes: the Traktor copy (with its
rem backups), the shortcuts and the log. Asks first; the original Traktor is
rem not touched.
setlocal
rem The code is in src: the .venv and requirements.txt are there.
cd /d "%~dp0src"
if not exist ".venv\Scripts\python.exe" (
    echo WaveLanes was not installed from this folder ^(no .venv^).
    goto end
)
".venv\Scripts\python.exe" -I windows\install_windows.py --uninstall %*

:end
echo.
pause
