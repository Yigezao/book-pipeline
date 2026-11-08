@echo off
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
    py -3 "%~dp0tools\new_book.py" %*
) else (
    python "%~dp0tools\new_book.py" %*
)
pause
