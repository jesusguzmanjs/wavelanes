@echo off
rem WaveLanes with a console: what the "WaveLanes" shortcut does
rem (install_windows.py makes it; it runs without a console and writes to
rem %LOCALAPPDATA%\WaveLanes\WaveLanes.log), but showing the
rem script's messages live. Applies the layout settings chosen in the
rem settings window inside Traktor (settings.json) if they changed,
rem then opens Traktor through wave_height.py. Closes itself when Traktor
rem exits; stays open with the error if something fails.
rem
rem Install first with "Install on Windows.bat", at the top of the repo.
rem Another Traktor copy: add --copy "C:\path\to\the copy" after --launch.
cd /d "%~dp0"
"..\.venv\Scripts\python.exe" -I traktor_config.py --launch
if errorlevel 1 pause
