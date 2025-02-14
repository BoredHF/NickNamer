@echo off
REM Check if Tesseract is installed
where tesseract >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Installing Tesseract OCR...
    winget install UB-Mannheim.TesseractOCR
    echo Please restart your terminal after installation
    pause
    exit
)

REM Create virtual environment
python -m venv venv

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install requirements
pip install -r requirements.txt

echo Virtual environment is ready! Use 'venv\Scripts\activate.bat' to activate it again later.
pause 