@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -m venv .venv
  ) else (
    where python >nul 2>nul
    if errorlevel 1 (
      echo Python 3 was not found. Install Python 3 and enable "Add Python to PATH", then run this file again.
      pause
      exit /b 1
    )
    python -m venv .venv
  )
  if errorlevel 1 (
    echo Could not create the local virtual environment.
    pause
    exit /b 1
  )
)

set "PYTHON=.venv\Scripts\python.exe"
"%PYTHON%" -c "import fastapi, uvicorn, sqlalchemy, pydantic_settings, jwt, qrcode, PIL, multipart, dotenv, itsdangerous, aiosqlite, email_validator, passlib, bcrypt" >nul 2>nul
if errorlevel 1 (
  echo Installing TURA Python dependencies...
  "%PYTHON%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Dependency installation failed. Check your internet connection and Python installation.
    pause
    exit /b 1
  )
)

echo Starting TURA at http://127.0.0.1:8000/
echo Keep this window open while using the app. Press Ctrl+C to stop the server.
"%PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
if errorlevel 1 (
  echo TURA stopped with an error. Read the messages above; port 8000 may already be in use.
  pause
)
endlocal
