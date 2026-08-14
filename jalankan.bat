@echo off
setlocal
title IDX Screener
cd /d "%~dp0"

echo.
echo   ==================================================
echo     IDX SCREENER - Bursa Efek Indonesia
echo   ==================================================
echo.

REM --- 1. Pastikan Python ada ---
python --version >nul 2>&1
if errorlevel 1 (
    echo   [X] Python tidak ditemukan.
    echo.
    echo   Pasang Python 3.10 atau lebih baru dari:
    echo     https://www.python.org/downloads/
    echo   PENTING: centang "Add Python to PATH" saat memasang.
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo   [OK] Python %%v

REM --- 2. Periksa dependensi (termasuk scipy dan scikit-learn) ---
echo   Memeriksa dependensi...
python -c "import fastapi,uvicorn,pandas,numpy,requests,scipy,sklearn" >nul 2>&1
if errorlevel 1 (
    echo   Memasang paket yang kurang, mohon tunggu...
    python -m pip install --quiet -r requirements.txt
    python -c "import fastapi,uvicorn,pandas,numpy,requests,scipy,sklearn" >nul 2>&1
    if errorlevel 1 (
        echo   [X] Pemasangan gagal. Coba jalankan manual:
        echo       python -m pip install -r requirements.txt
        pause
        exit /b 1
    )
)
echo   [OK] Semua paket siap

REM --- 3. Jalankan server di jendela terpisah ---
echo.
echo   Menyalakan server dan mengunduh data ~280 emiten.
echo   Proses ini butuh 30-60 detik pada koneksi normal.
echo.
start "IDX Screener Server" /min cmd /c "python -m app.server 8848 > server.log 2>&1"

REM --- 4. Tunggu sampai server benar-benar siap, BARU buka browser ---
REM     Versi sebelumnya membuka browser seketika, sehingga pengguna melihat
REM     halaman error karena data belum selesai dimuat.
echo   Menunggu server siap...
set /a n=0
:tunggu
set /a n+=1
powershell -NoProfile -Command "try{$r=Invoke-WebRequest 'http://127.0.0.1:8848/api/status' -UseBasicParsing -TimeoutSec 3; if(($r.Content|ConvertFrom-Json).siap){exit 0}else{exit 1}}catch{exit 1}" >nul 2>&1
if not errorlevel 1 goto siap
if %n% GEQ 60 goto gagal
timeout /t 2 /nobreak >nul
echo    ... %n%0 detik
goto tunggu

:gagal
echo.
echo   [X] Server tidak siap setelah 2 menit. Lihat isi server.log
echo.
type server.log 2>nul
pause
exit /b 1

:siap
echo.
echo   [OK] Server siap. Membuka browser...
start "" http://127.0.0.1:8848
echo.
echo   ==================================================
echo     Alamat : http://127.0.0.1:8848
echo     Berhenti: tutup jendela "IDX Screener Server"
echo   ==================================================
echo.
pause
