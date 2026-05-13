@echo off
title TEOIGO - Instalador del Cliente de Dictado
echo ============================================================
echo   TEOIGO - Instalador del Cliente de Dictado ALiaNeD
echo ============================================================
echo.

:: Verificar que Python este instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no esta instalado en tu sistema.
    echo Descargalo de: https://www.python.org/downloads/
    echo Marca la opcion "Add Python to PATH" al instalar.
    pause
    exit /b 1
)

echo [1/2] Instalando dependencias...
pip install -r client_requirements.txt

if errorlevel 1 (
    echo.
    echo [ERROR] Fallo la instalacion de dependencias.
    echo Intenta ejecutar este script como Administrador.
    pause
    exit /b 1
)

echo.
echo [2/2] Creando acceso directo en el Escritorio...
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([IO.Path]::Combine($ws.SpecialFolders('Desktop'), 'TEOIGO Dictado.lnk')); $s.TargetPath = 'pythonw'; $s.Arguments = '\"%%~dp0teoigo_client.pyw\"'; $s.WorkingDirectory = '%%~dp0'; $s.Description = 'TEOIGO - Dictado por voz ALiaNeD'; $s.Save()"

echo.
echo ============================================================
echo   INSTALACION COMPLETADA
echo ============================================================
echo.
echo   Para usar TEOIGO:
echo     1. Doble clic en "TEOIGO Dictado" en tu Escritorio
echo        (o ejecuta: pythonw teoigo_client.pyw)
echo.
echo     2. En cualquier aplicacion:
echo        Ctrl + Flecha Derecha  = Iniciar/Detener dictado
echo        Ctrl + Shift + F12    = Cerrar TEOIGO
echo.
echo   Tu API KEY ya esta configurada en el script.
echo   Servidor: https://teoigo.alianed.com
echo ============================================================
pause
