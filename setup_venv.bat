@echo off
REM Create virtual environment
python -m venv venv

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install requirements
pip install -r requirements.txt

echo Virtual environment is ready! Use 'venv\Scripts\activate.bat' to activate it again later.
pause 