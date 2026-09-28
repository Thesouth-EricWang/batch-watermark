@echo off
rem Batch watermark launcher (run from source).
rem Keep this file ASCII-only: cmd reads .bat with the system code page.
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw "app\watermark.pyw"
) else (
  echo [!] pythonw not found.
  echo     Install Python 3 first, then:  pip install pillow customtkinter
  pause
)
