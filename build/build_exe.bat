@echo off
REM =====================================================================
REM  TextLens Windows build script
REM  - Creates a venv if missing
REM  - Installs requirements + PyInstaller
REM  - Builds dist\TextLens\TextLens.exe
REM =====================================================================
setlocal

echo.
echo === TextLens build script ===
echo.

REM --- cd to project root (parent of build\) ---
cd /d "%~dp0\.."

REM --- Check Python ---
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found on PATH. Install Python 3.10+ first.
    pause
    exit /b 1
)

REM --- Create venv ---
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

REM --- Activate venv ---
call ".venv\Scripts\activate.bat"

REM --- Install deps ---
echo Installing dependencies...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
pip install pyinstaller==6.10.0

REM --- Clean previous build ---
if exist "build\__pycache__" rmdir /s /q "build\__pycache__"
if exist "dist" rmdir /s /q dist

REM --- Build ---
echo.
echo Building TextLens.exe...
cd build
pyinstaller textlens.spec --clean --noconfirm
cd ..

echo.
echo === Build complete ===
echo Output: dist\TextLens\TextLens.exe
echo.
pause
