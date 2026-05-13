@echo off
title TEOIGO - Reinicio Limpio
REM Uso interno para debugging. El usuario final NO necesita ejecutar esto.
REM El icono del escritorio creado por INSTALL_TEOIGO.bat es suficiente.
echo ============================================================
echo   TEOIGO - Reinicio Limpio (DEBUG)
echo ============================================================
echo.

echo [1/4] Cerrando TODAS las instancias previas de TEOIGO...
taskkill /F /FI "WINDOWTITLE eq TEOIGO*" >nul 2>&1

REM Matar cualquier python/pythonw ejecutando teoigo_client
for /f "tokens=2" %%a in ('wmic process where "commandline like '%%teoigo_client%%'" get processid /format:list 2^>nul ^| findstr ProcessId') do (
    echo   Cerrando PID: %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo   [OK] Instancias previas cerradas.
echo.

echo [2/4] Instalando/actualizando dependencias...
pip install -r client_requirements.txt -q
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion de dependencias.
    pause
    exit /b 1
)
echo   [OK] Dependencias listas.
echo.

echo [3/4] Verificando imports...
python -c "import keyboard, sounddevice, numpy, requests, pyperclip, pyautogui, pystray, PIL; print('  [OK] Todos los imports correctos')"
if errorlevel 1 (
    echo [WARN] Algunos imports fallaron. Intenta: pip install pystray Pillow
)
echo.

echo [4/4] Lanzando TEOIGO v2.0...
echo ============================================================
echo.
python teoigo_client.pyw
