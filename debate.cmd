@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
if not exist ".venv\Scripts\debate.exe" (
  echo Virtual environment not found. Run: py -3.11 -m venv .venv
  echo Then install the project: .venv\Scripts\python.exe -m pip install -e .
  exit /b 1
)
".venv\Scripts\debate.exe" %*
