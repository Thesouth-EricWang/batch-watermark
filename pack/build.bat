@echo off
rem Build portable exe for the batch watermark tool. Keep this file ASCII-only.
rem
rem   build.bat            -> onedir  (folder with exe + dependencies, no extraction)
rem   build.bat onefile    -> onefile (single exe, extracts to %TEMP% at runtime)
rem
rem Layout expected:
rem   <root>\app\watermark.pyw        source
rem   <root>\app\logo_placeholder.png bundled asset
rem   <root>\pack\build.bat           this script
rem
rem NOTE: paths below are absolute on purpose. With --specpath set, PyInstaller
rem resolves relative --add-data against the spec dir, which is not what we want.
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PY=python"
where python >nul 2>nul
if errorlevel 1 set "PY=C:\Users\ytwbc\AppData\Local\Python\bin\python.exe"
set "MODE=--onedir"
if /i "%~1"=="onefile" set "MODE=--onefile"

"%PY%" -m PyInstaller ^
  --noconfirm --clean --windowed %MODE% ^
  --name "batch-watermark" ^
  --add-data "%ROOT%\app\logo_placeholder.png;." ^
  --collect-all customtkinter ^
  --exclude-module numpy --exclude-module pandas --exclude-module matplotlib ^
  --exclude-module scipy --exclude-module PyQt5 --exclude-module PySide2 ^
  --exclude-module IPython --exclude-module pytest ^
  --distpath "%ROOT%\pack\dist" --workpath "%ROOT%\pack\build" --specpath "%ROOT%\pack" ^
  "%ROOT%\app\watermark.pyw"

echo.
echo Build finished. Output is under pack\dist\
pause
