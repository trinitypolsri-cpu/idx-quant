@echo off
title IDX Screener
cd /d "%~dp0"

echo.
echo   ============================================
echo     IDX SCREENER - Bursa Efek Indonesia
echo   ============================================
echo.
echo   Memeriksa dependensi...

python -c "import fastapi, uvicorn, pandas, numpy, requests" 2>nul
if errorlevel 1 (
    echo   Memasang paket yang kurang...
    python -m pip install --quiet fastapi uvicorn pandas numpy requests
)

echo   Menjalankan server di http://127.0.0.1:8848
echo   Tekan Ctrl+C untuk berhenti.
echo.

start "" http://127.0.0.1:8848
python -m app.server 8848

pause
