@echo off
REM Levanta el Automation Launcher en modo demo (Windows).
REM
REM No hace falta red de la empresa, ni el share SMB, ni credenciales reales:
REM lee un share falso de demo\share y acepta cualquier contrasena de 4+
REM caracteres. El codigo que corre es el mismo que va a produccion.
REM
REM   run_local.bat          -^> http://localhost:8866
REM   run_local.bat 9000     -^> otro puerto
setlocal

set PORT=%1
if "%PORT%"=="" set PORT=8866

cd /d "%~dp0"

if not exist ".venv" (
    echo ==^> Creando entorno virtual en .venv
    python -m venv .venv
)
call .venv\Scripts\activate.bat

echo ==^> Instalando dependencias
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

if not exist "launcher_config.py" (
    echo ==^> Copiando launcher_config.py desde demo\
    copy /y demo\launcher_config.demo.py launcher_config.py >nul
)

echo.
echo   +------------------------------------------------------------+
echo   ^|  Automation Launcher - modo demo                           ^|
echo   ^|                                                            ^|
echo   ^|  Entra con cualquier contrasena de 4 o mas caracteres.      ^|
echo   ^|  El selector del login te deja probar distintos roles:      ^|
echo   ^|                                                            ^|
echo   ^|    ana.g         jefa de Treasury (ve Miembros/Metricas)    ^|
echo   ^|    joaquin.benz  miembro de 2 hubs (sin tabs de jefe)       ^|
echo   ^|    carlos.m      jefe de CLO                               ^|
echo   ^|    lucia.r       un solo hub (entra directo)                ^|
echo   ^|    intruso       sin hubs (muestra el rechazo)              ^|
echo   +------------------------------------------------------------+
echo.
echo ==^> Abriendo http://localhost:%PORT%
voila app.ipynb --port=%PORT% --no-browser
