@echo off
REM Start script for backend (Windows)

echo Starting Smart Pharmacy Inventory Backend...

REM Activate virtual environment if it exists
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

REM Initialize database
echo Initializing database...
python init_db.py

REM Start server
echo Starting FastAPI server...
uvicorn main:app --reload --host 0.0.0.0 --port 8000


