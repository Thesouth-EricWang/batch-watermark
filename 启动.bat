@echo off
rem Batch watermark launcher. Keep this file ASCII-only:
rem cmd reads .bat with the system code page (GBK on Chinese Windows),
rem so UTF-8 Chinese here would break command parsing.
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw "watermark.pyw"
) else (
  echo [!] pythonw not found.
  echo     Install Python 3 first, then:  pip install pillow customtkinter
  pause
)
