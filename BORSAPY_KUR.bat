@echo off
setlocal
cd /d "%~dp0"
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info>=(3,8) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info>=(3,8) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY goto kurulum
title borsapy kurulumu
echo borsapy (Borsa MCP'nin kullandigi BIST veri kutuphanesi) kuruluyor...
%PY% -m pip install --upgrade borsapy
goto son

:kurulum
echo Python 3.8 veya ustu bulunamadi.
echo Python'u https://www.python.org/downloads/ adresinden kurabilirsiniz.
echo Kurulumda "Add python.exe to PATH" kutusunu isaretlemeyi unutmayin.
echo.
choice /C EH /M "Python 3.12 simdi winget ile otomatik kurulsun mu? (E=Evet, H=Hayir)"
if errorlevel 2 goto son
winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements
echo.
echo Kurulum bittiyse bu pencereyi kapatip dosyayi yeniden calistirin.
:son
echo.
pause
