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

echo [1/5] Instalando dependencias...
pip install -r client_requirements.txt
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion.
    pause
    exit /b 1
)

echo.
echo [2/5] Preparando lanzador...
set SCRIPT_DIR=%~dp0
set VBS_PATH=%SCRIPT_DIR%launch_teoigo.vbs

if not exist "%VBS_PATH%" (
    echo [ERROR] No se encontro launch_teoigo.vbs
    pause
    exit /b 1
)
echo   [OK] Lanzador VBS listo (evita bloqueo de antivirus)

echo.
echo [3/5] Convirtiendo icono PNG a ICO (Windows lo requiere)...
set ICON_PNG=%SCRIPT_DIR%Icono-Teoigo.png
set ICON_ICO=%SCRIPT_DIR%Icono-Teoigo.ico
python -c "from PIL import Image; img=Image.open(r'%ICON_PNG%'); img.save(r'%ICON_ICO%', format='ICO', sizes=[(256,256),(64,64),(48,48),(32,32),(16,16)])" 2>nul
if exist "%ICON_ICO%" (
    echo   [OK] Icono convertido a ICO
    set ICON_PATH=%ICON_ICO%
) else (
    echo   [WARN] No se pudo convertir icono. Se usara icono por defecto.
    set ICON_PATH=
)

echo.
echo [4/5] Creando acceso directo en el Escritorio...
REM El acceso directo apunta a wscript.exe + launch_teoigo.vbs
REM Esto usa python.exe (no pythonw) con consola oculta,
REM evitando que 360 Total Security lo bloquee.

if "%ICON_PATH%"=="" (
    powershell -Command "$ws = New-Object -ComObject WScript.Shell; $desktop = $ws.SpecialFolders('Desktop'); $s = $ws.CreateShortcut([IO.Path]::Combine($desktop, 'TEOIGO Dictado.lnk')); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%VBS_PATH%\"'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.Description = 'TEOIGO - Dictado por voz ALiaNeD'; $s.Save()"
) else (
    powershell -Command "$ws = New-Object -ComObject WScript.Shell; $desktop = $ws.SpecialFolders('Desktop'); $s = $ws.CreateShortcut([IO.Path]::Combine($desktop, 'TEOIGO Dictado.lnk')); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%VBS_PATH%\"'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.Description = 'TEOIGO - Dictado por voz ALiaNeD'; $s.IconLocation = '%ICON_PATH%'; $s.Save()"
)

echo.
echo [5/5] Configurando inicio automatico con Windows...
if "%ICON_PATH%"=="" (
    powershell -Command "$ws = New-Object -ComObject WScript.Shell; $startup = $ws.SpecialFolders('Startup'); $s = $ws.CreateShortcut([IO.Path]::Combine($startup, 'TEOIGO Dictado.lnk')); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%VBS_PATH%\"'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.Description = 'TEOIGO - Dictado por voz ALiaNeD'; $s.Save()"
) else (
    powershell -Command "$ws = New-Object -ComObject WScript.Shell; $startup = $ws.SpecialFolders('Startup'); $s = $ws.CreateShortcut([IO.Path]::Combine($startup, 'TEOIGO Dictado.lnk')); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%VBS_PATH%\"'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.Description = 'TEOIGO - Dictado por voz ALiaNeD'; $s.Save()"
)

echo.
echo ============================================================
echo   INSTALACION COMPLETADA
echo ============================================================
echo.
echo   TEOIGO se iniciara automaticamente con Windows.
echo.
echo   Atajos:
echo     Ctrl + Flecha Derecha  = Encender microfono
echo     Ctrl + Flecha Izquierda = Apagar microfono
echo     Ctrl + Shift + F12     = Cerrar TEOIGO
echo.
echo   Doble-click en el icono de la bandeja = Mostrar/Ocultar pildora
echo.
echo   NOTA: Se usa python.exe con ventana oculta (no pythonw.exe)
echo   para evitar que 360 Total Security bloquee la aplicacion.
echo ============================================================
pause
