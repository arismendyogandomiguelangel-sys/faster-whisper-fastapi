@echo off
title TEOIGO - Instalador del Cliente de Dictado
echo ============================================================
echo   TEOIGO - Instalador del Cliente de Dictado ALiaNeD
echo ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no esta instalado.
    echo Descargalo de: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] Instalando dependencias...
pip install -r client_requirements.txt
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion.
    pause
    exit /b 1
)

echo.
echo [2/3] Creando acceso directo en el Escritorio...
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([IO.Path]::Combine($ws.SpecialFolders('Desktop'), 'TEOIGO Dictado.lnk')); $s.TargetPath = 'pythonw'; $s.Arguments = '\"%%~dp0teoigo_client.pyw\"'; $s.WorkingDirectory = '%%~dp0'; $s.Description = 'TEOIGO - Dictado por voz ALiaNeD'; $s.Save()"

echo.
echo [3/3] Configurando inicio automatico con Windows...
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $startup = $ws.SpecialFolders('Startup'); $s = $ws.CreateShortcut([IO.Path]::Combine($startup, 'TEOIGO Dictado.lnk')); $s.TargetPath = 'pythonw'; $s.Arguments = '\"%%~dp0teoigo_client.pyw\"'; $s.WorkingDirectory = '%%~dp0'; $s.Description = 'TEOIGO - Dictado por voz ALiaNeD'; $s.WindowStyle = 7; $s.Save()"

echo.
echo ============================================================
echo   INSTALACION COMPLETADA
echo ============================================================
echo.
echo   TEOIGO se iniciara automaticamente con Windows.
echo.
echo   Atajos:
echo     Ctrl + Flecha Derecha  = Dictar
echo     Ctrl + Shift + F12    = Cerrar TEOIGO
echo ============================================================
pause
