@echo off
rem Builds a standalone Facet.exe into dist\Facet.
cd /d "%~dp0"
.venv\Scripts\python -m pip install pyinstaller || exit /b 1
.venv\Scripts\pyinstaller --noconfirm --windowed --name Facet --icon facet\assets\facet.ico --add-data "facet\assets;facet\assets" --collect-all rawpy --collect-all pillow_heif run.py || exit /b 1
echo Done: dist\Facet\Facet.exe
