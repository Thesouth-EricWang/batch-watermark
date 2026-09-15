@echo off
rem Build portable exe for the batch watermark tool. Keep this file ASCII-only
rem (cmd reads .bat with the system code page, UTF-8 Chinese would break parsing).
rem
rem   build.bat            -> onedir  (a folder with exe + dependencies, no extraction)
rem   build.bat onefile    -> onefile (a single exe, extracts to %TEMP% at runtime)
cd /d "%~dp0"

set "PY=python"
where python >nul 2>nul
if errorlevel 1 set "PY=C:\Users\ytwbc\AppData\Local\Python\bin\python.exe"

set "MODE=--onedir"
if /i "%~1"=="onefile" set "MODE=--onefile"

"%PY%" -m PyInstaller ^
  --noconfirm --clean --windowed %MODE% ^
  --name "batch-watermark" ^
  --add-data "logo_placeholder.png;." ^
  --collect-all customtkinter ^
  --exclude-module numpy --exclude-module pandas --exclude-module matplotlib ^
  --exclude-module scipy --exclude-module PyQt5 --exclude-module PySide2 ^
  --exclude-module IPython --exclude-module pytest --exclude-module PIL.ImageQt ^
  --distpath "dist" --workpath "build" --specpath "." ^
  "watermark.pyw"

echo.
echo Build finished. Output is under dist\
pause
