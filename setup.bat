@echo off
title Python Proje Kurulumu
color 0A

echo ==========================================
echo        PYTHON PROJESI KURULUMU
echo ==========================================
echo.

:: Python kontrolu
python --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] Python bulunamadi!
    echo Lutfen Python'u kur ve PATH'e ekle.
    pause
    exit /b 1
)

echo [OK] Python bulundu:
python --version
echo.

:: pip kontrolu
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] pip bulunamadi!
    pause
    exit /b 1
)

echo [OK] pip bulundu.
echo.

:: pip guncelle
echo [1/2] pip guncelleniyor...
python -m pip install --upgrade pip

echo.
echo [2/2] Gerekli paketler kuruluyor...
echo.

python -m pip install "PyQt5>=5.15.0" ^
    "huggingface_hub>=0.20.0" ^
    "SpeechRecognition>=3.10.0" ^
    "PyAudio>=0.2.13" ^
    "Pillow>=10.0.0"

if errorlevel 1 (
    echo.
    echo ==========================================
    echo [HATA] Kurulum sirasinda bir sorun olustu.
    echo ==========================================
    pause
    exit /b 1
)

echo.
echo ==========================================
echo       KURULUM BASARIYLA TAMAMLANDI!
echo ==========================================
echo.
echo Kurulu paketler:
python -m pip list
echo.
pause