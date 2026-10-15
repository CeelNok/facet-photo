@echo off
rem Facet launcher for Windows. First start: creates .venv, installs dependencies and a "Facet" shortcut with the logo.
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" goto run

echo Setting up Facet for the first time (about 1-2 minutes)...
set "PY="
for %%V in (3.13 3.12 3.11 3.10) do (
  if not defined PY ( py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V" )
)
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo Facet needs Python 3.10 or newer: https://www.python.org/downloads/  ^(tick "Add python.exe to PATH"^)
  pause
  exit /b 1
)
%PY% -m venv .venv || goto fail
".venv\Scripts\python.exe" -m pip install --upgrade pip || goto fail
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto fail
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%~dp0Facet.lnk');" ^
  "$s.TargetPath='%~dp0.venv\Scripts\pythonw.exe';" ^
  "$s.Arguments='\"%~dp0run.py\"';" ^
  "$s.WorkingDirectory='%~dp0';" ^
  "$s.IconLocation='%~dp0facet\assets\facet.ico';" ^
  "$s.Description='Facet - AI photo culling and sorting';" ^
  "$s.Save()" >nul 2>&1
echo A "Facet" shortcut with the logo was created in this folder - you can pin it to Start or the taskbar.

:run
start "" ".venv\Scripts\pythonw.exe" "%~dp0run.py" %*
exit /b 0

:fail
echo Installation failed. Please check your internet connection and try again.
rmdir /s /q .venv >nul 2>&1
pause
exit /b 1
