@echo off
rem Double-click to install WaveLanes (or open it again to repair or
rem update the install). Makes the Python environment, then runs
rem windows\install_windows.py: the Traktor copy and the shortcuts.
setlocal
rem The code is in src: the .venv and requirements.txt are there.
cd /d "%~dp0src"

if exist ".venv\Scripts\python.exe" goto packages

rem A Python 3 to make the environment with: the py launcher, else python
rem (if it is a real one, not the Microsoft Store placeholder).
set "PY="
py -3 -c "" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>nul && set "PY=python"
if defined PY goto venv

echo Python 3 is needed and was not found.
choice /M "Install it now with winget (Windows' own installer)"
if errorlevel 2 (
    echo Install Python 3 from https://www.python.org/downloads/ and open this file again.
    goto end
)
winget install -e --id Python.Python.3.13 --scope user --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo winget could not install Python. Install it from https://www.python.org/downloads/
    echo and open this file again.
    goto end
)
echo.
echo Python is installed. Close this window and open this file again.
goto end

:venv
echo Making the Python environment...
%PY% -m venv .venv
if errorlevel 1 goto end

:packages
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto end
".venv\Scripts\python.exe" -I windows\install_windows.py %*

:end
echo.
pause
